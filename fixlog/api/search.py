from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from fixlog.api.shared import (
    entry_summary,
    verification_counts,
    with_entry_summary_options,
)
from fixlog.db.models import Entry, EntryAlsoMatch, ErrorSignature
from fixlog.db.session import get_db
from fixlog.normalizer.python import normalize_python_error
from fixlog.schemas.search import SearchResponse

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    error: Annotated[str, Query(min_length=1)],
    db: Session = Depends(get_db),
) -> SearchResponse:
    hash_value = normalize_python_error(error).hash
    signature = db.scalar(select(ErrorSignature).where(ErrorSignature.hash == hash_value))
    if signature is None:
        return SearchResponse(entries=[], exact_match=False)

    also_match_entry_ids = select(EntryAlsoMatch.entry_id).where(
        EntryAlsoMatch.error_signature_id == signature.id
    )
    entries = list(
        db.scalars(
            with_entry_summary_options(
                select(Entry).where(
                    or_(
                        Entry.canonical_error_signature_id == signature.id,
                        Entry.id.in_(also_match_entry_ids),
                    )
                )
            )
        )
        .unique()
        .all()
    )
    counts = verification_counts(db, [entry.id for entry in entries])
    return SearchResponse(
        entries=[entry_summary(entry, counts.get(entry.id, 0)) for entry in entries],
        exact_match=True,
    )
