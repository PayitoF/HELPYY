"""PII Tokenizer — replaces sensitive data with tokens before LLM processing.

Detects: Colombian cedulas (8-10 digits), names (after "me llamo"/"soy"/"mi nombre es"),
phone numbers, email addresses.

Token format: [TOK_{TYPE}_{hash_corto}]
    e.g. [TOK_CC_a1b2c3], [TOK_NAME_d4e5f6], [TOK_PHONE_a1b2c3], [TOK_EMAIL_d4e5f6]
"""

import hashlib
import re

# ---------------------------------------------------------------------------
# Patterns — order matters: emails first (contain digits that look like phone/cc)
# ---------------------------------------------------------------------------

# Email: standard email regex
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Colombian phone: 10-digit starting with 3 (cellphones), optionally with +57 prefix
_PHONE_RE = re.compile(r"(?:\+57\s?)?3\d{9}(?!\d)")

# Colombian cedula: 8-10 standalone digits (not part of a longer number)
_CEDULA_RE = re.compile(r"(?<!\d)\d{8,10}(?!\d)")

# Name after trigger phrases (captures 1-3 capitalized or lowercase words)
_NAME_RE = re.compile(
    r"(?:(?:me llamo|mi nombre es|soy|nombre completo(?:\s+es)?)\s+)"
    r"([A-ZÁÉÍÓÚÑa-záéíóúñ][a-záéíóúñ]+"
    r"(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ][a-záéíóúñ]+){0,2})",
    re.IGNORECASE,
)


def _short_hash(value: str) -> str:
    """Deterministic 6-char hex hash for a given value."""
    return hashlib.sha256(value.encode()).hexdigest()[:6]


def tokenize_pii(text: str) -> tuple[str, dict[str, str]]:
    """Replace PII in text with tokens.

    Args:
        text: Raw user input that may contain PII.

    Returns:
        Tuple of (tokenized_text, mapping) where mapping is {token: original_value}.
        The mapping also stores type metadata under a ``_types`` key:
        {token: pii_type} so the detokenizer knows how to produce safe values.
    """
    mapping: dict[str, str] = {}
    types: dict[str, str] = {}
    result = text

    # 1. Emails (before cedula/phone since emails contain digits)
    for match in _EMAIL_RE.finditer(result):
        raw = match.group(0)
        token = f"[TOK_EMAIL_{_short_hash(raw)}]"
        mapping[token] = raw
        types[token] = "email"
    for token, raw in list(mapping.items()):
        if types.get(token) == "email":
            result = result.replace(raw, token)

    # 2. Names (before phone/cedula so the name phrase isn't mangled)
    for match in _NAME_RE.finditer(result):
        raw = match.group(1)
        token = f"[TOK_NAME_{_short_hash(raw)}]"
        if token not in mapping:
            mapping[token] = raw
            types[token] = "name"
    for token, raw in list(mapping.items()):
        if types.get(token) == "name":
            result = result.replace(raw, token)

    # 3. Phones
    for match in _PHONE_RE.finditer(result):
        raw = match.group(0)
        token = f"[TOK_PHONE_{_short_hash(raw)}]"
        if token not in mapping:
            mapping[token] = raw
            types[token] = "phone"
    for token, raw in list(mapping.items()):
        if types.get(token) == "phone":
            result = result.replace(raw, token)

    # 4. Cedulas (last — digits that weren't already consumed)
    for match in _CEDULA_RE.finditer(result):
        raw = match.group(0)
        token = f"[TOK_CC_{_short_hash(raw)}]"
        if token not in mapping:
            mapping[token] = raw
            types[token] = "cedula"
    for token, raw in list(mapping.items()):
        if types.get(token) == "cedula":
            result = result.replace(raw, token)

    # Store type metadata alongside the mapping
    mapping["_types"] = types  # type: ignore[assignment]

    return result, mapping
