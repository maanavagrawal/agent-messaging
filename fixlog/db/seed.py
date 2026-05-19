from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from fixlog.config import Settings
from fixlog.db.models import Account
from fixlog.identity.persona import sha256_hex

logger = logging.getLogger(__name__)


def token_hash(raw_token: str) -> str:
    return sha256_hex(raw_token)


def seed_accounts_from_settings(db: Session, settings: Settings) -> list[Account]:
    pairs = [
        (settings.fixlog_account_1_token, settings.fixlog_account_1_name),
        (settings.fixlog_account_2_token, settings.fixlog_account_2_name),
    ]
    missing = [
        name
        for name, value in (
            ("FIXLOG_ACCOUNT_1_TOKEN", settings.fixlog_account_1_token),
            ("FIXLOG_ACCOUNT_1_NAME", settings.fixlog_account_1_name),
            ("FIXLOG_ACCOUNT_2_TOKEN", settings.fixlog_account_2_token),
            ("FIXLOG_ACCOUNT_2_NAME", settings.fixlog_account_2_name),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required fixlog account env vars: {', '.join(missing)}")

    accounts: list[Account] = []
    for raw_token, human_name in pairs:
        hashed = token_hash(raw_token)
        account = db.scalar(select(Account).where(Account.api_token_hash == hashed))
        if account is None:
            account = Account(api_token_hash=hashed, human_name=human_name)
            db.add(account)
            logger.info("seeded account human_name=%s", human_name)
        elif account.human_name != human_name:
            account.human_name = human_name
            logger.info("updated seeded account human_name=%s", human_name)
        accounts.append(account)
    db.commit()
    return accounts
