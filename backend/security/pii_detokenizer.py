"""PII Detokenizer — replaces tokens with safe partial values in LLM responses.

Only accessible from the backend service, never from LLM.
Returns partial values for UX: first name only, masked cedula, etc.
"""

import re

from backend.security.pii_vault import PIIVault

# Matches any [TOK_*_*] token in text
_TOKEN_RE = re.compile(r"\[TOK_[A-Z]+_[a-f0-9]+\]")

# Module-level default vault (tests can override)
_default_vault: PIIVault | None = None


def get_vault() -> PIIVault:
    global _default_vault
    if _default_vault is None:
        _default_vault = PIIVault()
    return _default_vault


def set_vault(vault: PIIVault) -> None:
    """Override the default vault (for testing)."""
    global _default_vault
    _default_vault = vault


def detokenize_response(text: str, session_id: str) -> str:
    """Replace PII tokens in agent response with safe partial values.

    Args:
        text: Agent response containing tokens like [TOK_NAME_c3d4].
        session_id: Session ID to look up the token mapping in the vault.

    Returns:
        Text with tokens replaced by safe partial values.
        If the vault has no mapping (expired/missing), tokens are left as-is.
    """
    vault = get_vault()
    mapping = vault.retrieve(session_id)
    if mapping is None:
        return text

    types: dict[str, str] = mapping.get("_types", {})

    def _replace(match: re.Match) -> str:
        token = match.group(0)
        original = mapping.get(token)
        if original is None:
            return token
        pii_type = types.get(token, "")
        return _safe_value(original, pii_type)

    return _TOKEN_RE.sub(_replace, text)


def _safe_value(original: str, pii_type: str) -> str:
    """Produce a safe, partial representation of a PII value.

    - name   → first name only (e.g. "Juan Pérez" → "Juan")
    - cedula → masked (e.g. "1234567890" → "****7890")
    - phone  → masked (e.g. "3101234567" → "****4567")
    - email  → masked (e.g. "juan@mail.com" → "j***@mail.com")
    """
    if pii_type == "name":
        return original.split()[0]

    if pii_type == "cedula":
        if len(original) > 4:
            return "****" + original[-4:]
        return "****"

    if pii_type == "phone":
        if len(original) > 4:
            return "****" + original[-4:]
        return "****"

    if pii_type == "email":
        at = original.find("@")
        if at > 1:
            return original[0] + "***" + original[at:]
        return "***" + original[at:]

    # Unknown type — mask everything
    return "****"
