"""Audit logger — logs all PII access events for compliance."""

import json
import logging
import time

logger = logging.getLogger("pii_audit")

# Ensure at least INFO level for audit trail
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log_pii_access(session_id: str, action: str, token: str, reason: str) -> None:
    """Log a PII access event.

    Args:
        session_id: User session.
        action: "tokenize" | "detokenize" | "vault_store" | "vault_retrieve"
        token: The PII token involved (NOT the actual PII value).
        reason: Why the access occurred.
    """
    entry = {
        "timestamp": time.time(),
        "session_id": session_id,
        "action": action,
        "token": token,
        "reason": reason,
    }
    logger.info(json.dumps(entry, ensure_ascii=False))
