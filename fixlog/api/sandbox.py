from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from fixlog.auth.deps import require_account
from fixlog.db.models import Account

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


@router.get("/status")
def sandbox_status(
    request: Request,
    _account: Account = Depends(require_account),
) -> dict[str, object]:
    worker = getattr(request.app.state, "verifier_worker", None)
    if worker is None:
        return {
            "running": False,
            "queue_depth": 0,
            "last_error": None,
            "recent_result_counts": {},
        }
    return worker.status()
