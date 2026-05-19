from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fixlog.auth.deps import require_account
from fixlog.db.models import Account, Entry, Verification, VerificationResult, VerifierKind
from fixlog.db.session import get_db
from fixlog.schemas.verification import VerificationCreate, VerificationRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/entries", tags=["verifications"])


@router.post("/{entry_id}/verifications", response_model=VerificationRead, status_code=status.HTTP_201_CREATED)
def create_verification(
    entry_id: UUID,
    payload: VerificationCreate,
    account: Account = Depends(require_account),
    db: Session = Depends(get_db),
) -> VerificationRead:
    if db.get(Entry, entry_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    verification = Verification(
        entry_id=entry_id,
        verifier_kind=VerifierKind(payload.verifier_kind.value),
        verifier_id=str(account.id),
        result=VerificationResult(payload.result.value),
        env_snapshot=payload.env_snapshot.model_dump(),
        notes=payload.notes,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)
    logger.info("verification created id=%s entry=%s result=%s", verification.id, entry_id, verification.result.value)
    return VerificationRead.model_validate(verification)


@router.get("/{entry_id}/verifications", response_model=list[VerificationRead])
def list_verifications(entry_id: UUID, db: Session = Depends(get_db)) -> list[VerificationRead]:
    rows = db.scalars(
        select(Verification)
        .where(Verification.entry_id == entry_id)
        .order_by(desc(Verification.ts))
    ).all()
    return [VerificationRead.model_validate(row) for row in rows]

