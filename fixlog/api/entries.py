from __future__ import annotations

import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fixlog.api.shared import (
    entry_read,
    entry_summary,
    load_entry_or_none,
    upsert_error_signature,
    verification_counts,
    with_entry_summary_options,
)
from fixlog.auth.deps import require_account, require_session
from fixlog.db.models import (
    Account,
    AgentSession,
    Edit,
    Entry,
    EntryAlsoMatch,
    SandboxKind,
    utc_now,
)
from fixlog.db.session import get_db
from fixlog.schemas.edit import EntryPatchRequest, EntrySupersedeRequest
from fixlog.schemas.entry import EntryCreate, EntryListResponse, EntryRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/entries", tags=["entries"])

PATCHABLE_FIELDS = {
    "diagnosis",
    "fix_explanation",
    "reproduction_setup",
    "reproduction_trigger",
    "reproduction_verify",
    "sandbox_spec",
    "tags",
}


@router.get("", response_model=EntryListResponse)
def list_entries(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> EntryListResponse:
    entries = list(
        db.scalars(
            with_entry_summary_options(
                select(Entry).order_by(desc(Entry.created_at)).offset(offset).limit(limit)
            )
        )
        .unique()
        .all()
    )
    counts = verification_counts(db, [entry.id for entry in entries])
    return EntryListResponse(
        items=[entry_summary(entry, counts.get(entry.id, 0)) for entry in entries],
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=EntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(
    payload: EntryCreate,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> EntryRead:
    account, session = auth
    signature = upsert_error_signature(db, payload.error_signature)
    entry = Entry(
        account_id=account.id,
        persona_id=session.persona_id,
        session_id=session.id,
        canonical_error_signature_id=signature.id,
        env_context=payload.env_context.model_dump(),
        diagnosis=payload.diagnosis,
        fix_diff=payload.fix_diff,
        fix_explanation=payload.fix_explanation,
        reproduction_setup=payload.reproduction_setup,
        reproduction_trigger=payload.reproduction_trigger,
        reproduction_verify=payload.reproduction_verify,
        sandbox_kind=SandboxKind(payload.sandbox_kind.value),
        sandbox_spec=payload.sandbox_spec,
        tags=payload.tags,
    )
    db.add(entry)
    db.flush()
    for also_match_input in payload.also_matches:
        also_signature = upsert_error_signature(db, also_match_input)
        if also_signature.id != signature.id:
            db.add(
                EntryAlsoMatch(
                    entry_id=entry.id,
                    error_signature_id=also_signature.id,
                )
            )
    db.commit()
    loaded = load_entry_or_none(db, entry.id)
    if loaded is None:
        raise RuntimeError("Created entry could not be reloaded")
    logger.info("entry created id=%s account=%s persona=%s", loaded.id, account.id, session.persona_id)
    return entry_read(loaded)


@router.patch("/{entry_id}", response_model=EntryRead)
def patch_entry(
    entry_id: UUID,
    payload: EntryPatchRequest,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> EntryRead:
    entry = load_entry_or_none(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    if payload.field_changed not in PATCHABLE_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Field '{payload.field_changed}' is not patchable; "
                "create a superseding entry instead"
            ),
        )

    old_value = getattr(entry, payload.field_changed)
    new_value: object = payload.new_value
    if payload.field_changed == "tags":
        try:
            parsed = json.loads(payload.new_value)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tags new_value must be a JSON array of strings",
            ) from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tags new_value must be a JSON array of strings",
            )
        new_value = parsed

    setattr(entry, payload.field_changed, new_value)
    db.add(
        Edit(
            entry_id=entry.id,
            editor_account_id=account.id,
            field_changed=payload.field_changed,
            old_value=_edit_value(old_value),
            new_value=_edit_value(new_value),
            reason=payload.reason,
        )
    )
    db.commit()
    loaded = load_entry_or_none(db, entry.id)
    if loaded is None:
        raise RuntimeError("Patched entry could not be reloaded")
    logger.info("edit applied entry=%s field=%s account=%s", entry.id, payload.field_changed, account.id)
    return entry_read(loaded)


@router.post("/{entry_id}/supersede", response_model=EntryRead)
def supersede_entry(
    entry_id: UUID,
    payload: EntrySupersedeRequest,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> EntryRead:
    entry = load_entry_or_none(db, entry_id)
    new_entry = load_entry_or_none(db, payload.new_entry_id)
    if entry is None or new_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Both entries must exist to supersede",
        )
    old_value = entry.superseded_by
    entry.superseded_by = new_entry.id
    db.add(
        Edit(
            entry_id=entry.id,
            editor_account_id=account.id,
            field_changed="superseded_by",
            old_value=_edit_value(old_value),
            new_value=str(new_entry.id),
            reason=payload.reason,
        )
    )
    db.commit()
    loaded = load_entry_or_none(db, entry.id)
    if loaded is None:
        raise RuntimeError("Superseded entry could not be reloaded")
    logger.info("supersession entry=%s superseded_by=%s account=%s", entry.id, new_entry.id, account.id)
    return entry_read(loaded)


def _edit_value(value: object) -> str:
    if isinstance(value, list | dict):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return str(value)
