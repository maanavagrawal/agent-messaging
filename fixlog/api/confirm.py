from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fixlog.auth.deps import require_session
from fixlog.db.models import Account, AgentSession, Entry, Verification, VerificationResult, VerifierKind
from fixlog.db.session import get_db
from fixlog.schemas.verification import ConfirmRequest, RejectRequest, VerificationRead

logger = logging.getLogger(__name__)
router = APIRouter(tags=["confirm"])


@router.post("/confirm", response_model=VerificationRead, status_code=status.HTTP_201_CREATED)
def confirm_entry(
    payload: ConfirmRequest,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> VerificationRead:
    account, _session = auth
    entry = db.get(Entry, payload.entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    verification = Verification(
        entry_id=entry.id,
        verifier_kind=VerifierKind.HUMAN_CLI,
        verifier_id=str(account.id),
        result=VerificationResult.PASS,
        env_snapshot=entry.env_context,
        notes=None,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)
    logger.info("verification created id=%s entry=%s result=pass", verification.id, entry.id)
    return VerificationRead.model_validate(verification)


@router.post("/reject", response_model=VerificationRead, status_code=status.HTTP_201_CREATED)
def reject_entry(
    payload: RejectRequest,
    auth: tuple[Account, AgentSession] = Depends(require_session),
    db: Session = Depends(get_db),
) -> VerificationRead:
    account, _session = auth
    entry = db.get(Entry, payload.entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    verification = Verification(
        entry_id=entry.id,
        verifier_kind=VerifierKind.HUMAN_CLI,
        verifier_id=str(account.id),
        result=VerificationResult.FAIL,
        env_snapshot=entry.env_context,
        notes=payload.reason,
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)
    logger.info("verification created id=%s entry=%s result=fail", verification.id, entry.id)
    return VerificationRead.model_validate(verification)
