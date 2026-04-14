"""Activation code manager — links web widget onboarding to app login.

When a user completes onboarding via the web widget, the backend generates
a 6-digit activation code. The user enters this code in the app to:
  1. Load their account profile (name, account_id)
  2. Import chat history from the widget session
  3. Start with the agent greeting them back
"""

import random
import string
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Code format: HLP-XXXXXX (6 alphanumeric uppercase)
_CODE_PREFIX = "HLP"
_CODE_LENGTH = 6
_CODE_TTL = 3600 * 24  # 24 hours


@dataclass
class ActivationRecord:
    code: str
    session_id: str
    account_id: str
    display_name: str
    created_at: float = field(default_factory=time.time)
    used: bool = False


class ActivationCodeStore:
    """In-memory store for activation codes. Production would use DynamoDB."""

    def __init__(self):
        self._by_code: dict[str, ActivationRecord] = {}
        self._by_session: dict[str, ActivationRecord] = {}

    def generate(self, session_id: str, account_id: str, display_name: str) -> str:
        """Generate a new activation code for a completed onboarding session."""
        # If session already has a code, return it
        existing = self._by_session.get(session_id)
        if existing and not existing.used:
            return existing.code

        code = self._make_code()
        record = ActivationRecord(
            code=code,
            session_id=session_id,
            account_id=account_id,
            display_name=display_name,
        )
        self._by_code[code] = record
        self._by_session[session_id] = record
        logger.info("[ACTIVATION] Generated code=%s for session=%s account=%s", code, session_id, account_id)
        return code

    def validate(self, code: str) -> ActivationRecord | None:
        """Validate an activation code. Returns the record or None."""
        code = code.strip().upper()
        record = self._by_code.get(code)
        if record is None:
            logger.warning("[ACTIVATION] Invalid code: %s", code)
            return None
        if record.used:
            logger.warning("[ACTIVATION] Code already used: %s", code)
            return None
        if time.time() - record.created_at > _CODE_TTL:
            logger.warning("[ACTIVATION] Code expired: %s", code)
            del self._by_code[code]
            return None
        return record

    def mark_used(self, code: str) -> None:
        """Mark a code as used after successful app activation."""
        code = code.strip().upper()
        record = self._by_code.get(code)
        if record:
            record.used = True
            logger.info("[ACTIVATION] Code used: %s", code)

    def _make_code(self) -> str:
        """Generate a unique HLP-XXXXXX code."""
        for _ in range(100):
            chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=_CODE_LENGTH))
            code = f"{_CODE_PREFIX}-{chars}"
            if code not in self._by_code:
                return code
        raise RuntimeError("Could not generate unique code")


# Module-level singleton
_store: ActivationCodeStore | None = None


def get_activation_store() -> ActivationCodeStore:
    global _store
    if _store is None:
        _store = ActivationCodeStore()
    return _store
