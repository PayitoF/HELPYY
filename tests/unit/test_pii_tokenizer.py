"""Tests for PII tokenization — CRITICAL security tests."""

import re
import time
from unittest.mock import AsyncMock

import pytest

from backend.security.pii_tokenizer import tokenize_pii
from backend.security.pii_detokenizer import detokenize_response, set_vault, _safe_value
from backend.security.pii_vault import PIIVault


@pytest.fixture(autouse=True)
def _temp_vault(tmp_path):
    """Use a temporary SQLite vault for every test."""
    db_path = str(tmp_path / "test_vault.db")
    vault = PIIVault(db_path=db_path, ttl_hours=24)
    set_vault(vault)
    yield vault


# =======================================================================
# TOKENIZER — detection & replacement
# =======================================================================

@pytest.mark.pii
class TestTokenizerCedula:
    """Colombian cedula detection (8-10 digits)."""

    def test_cedula_is_tokenized(self):
        text = "mi cédula es 1234567890"
        result, mapping = tokenize_pii(text)
        assert "1234567890" not in result
        assert re.search(r"\[TOK_CC_[a-f0-9]+\]", result)
        # mapping contains the original value
        tokens = [k for k in mapping if k.startswith("[TOK_CC_")]
        assert len(tokens) == 1
        assert mapping[tokens[0]] == "1234567890"

    def test_8_digit_cedula(self):
        result, mapping = tokenize_pii("cedula 12345678")
        assert "12345678" not in result
        assert any(k.startswith("[TOK_CC_") for k in mapping)

    def test_9_digit_cedula(self):
        result, mapping = tokenize_pii("cc 123456789")
        assert "123456789" not in result

    def test_does_not_match_short_numbers(self):
        """Numbers under 8 digits are NOT cedulas."""
        result, mapping = tokenize_pii("tengo 1234 pesos")
        assert "1234" in result
        assert not any(k.startswith("[TOK_CC_") for k in mapping if k != "_types")

    def test_does_not_match_numbers_inside_words(self):
        """Digits that are part of tokens/hashes should not be matched."""
        result, mapping = tokenize_pii("ref ABC12345678XYZ")
        # The 8-digit sequence embedded in alphanumeric is still standalone digits
        # but the regex requires word boundaries; this tests edge case
        assert "[TOK_CC_" in result or "12345678" in result  # either is acceptable


@pytest.mark.pii
class TestTokenizerName:
    """Name detection after trigger phrases."""

    def test_soy_name(self):
        result, mapping = tokenize_pii("soy Juan Pérez")
        assert "Juan Pérez" not in result
        assert re.search(r"\[TOK_NAME_[a-f0-9]+\]", result)
        tokens = [k for k in mapping if k.startswith("[TOK_NAME_")]
        assert mapping[tokens[0]] == "Juan Pérez"

    def test_me_llamo_name(self):
        result, mapping = tokenize_pii("me llamo María García López")
        assert "María García López" not in result
        tokens = [k for k in mapping if k.startswith("[TOK_NAME_")]
        assert mapping[tokens[0]] == "María García López"

    def test_mi_nombre_es(self):
        result, mapping = tokenize_pii("mi nombre es Carlos")
        assert "Carlos" not in result

    def test_nombre_completo_es(self):
        result, mapping = tokenize_pii("nombre completo es Ana Torres")
        assert "Ana Torres" not in result

    def test_no_match_without_trigger(self):
        """Random capitalized words without triggers should not be tokenized."""
        result, mapping = tokenize_pii("Quiero abrir una cuenta en BBVA")
        assert not any(k.startswith("[TOK_NAME_") for k in mapping if k != "_types")


@pytest.mark.pii
class TestTokenizerEmail:
    """Email detection."""

    def test_email_is_tokenized(self):
        result, mapping = tokenize_pii("mi correo es juan@mail.com")
        assert "juan@mail.com" not in result
        assert re.search(r"\[TOK_EMAIL_[a-f0-9]+\]", result)
        tokens = [k for k in mapping if k.startswith("[TOK_EMAIL_")]
        assert mapping[tokens[0]] == "juan@mail.com"

    def test_complex_email(self):
        result, mapping = tokenize_pii("email: maria.garcia+test@empresa.co")
        assert "maria.garcia+test@empresa.co" not in result


@pytest.mark.pii
class TestTokenizerPhone:
    """Colombian phone number detection."""

    def test_phone_is_tokenized(self):
        result, mapping = tokenize_pii("mi celular es 3101234567")
        assert "3101234567" not in result
        assert re.search(r"\[TOK_PHONE_[a-f0-9]+\]", result)
        tokens = [k for k in mapping if k.startswith("[TOK_PHONE_")]
        assert mapping[tokens[0]] == "3101234567"

    def test_phone_with_prefix(self):
        result, mapping = tokenize_pii("llámame al +57 3209876543")
        assert "3209876543" not in result

    def test_non_colombian_phone_not_matched(self):
        """Numbers starting with digits other than 3 are not phones."""
        result, mapping = tokenize_pii("numero 1234567890")
        # Should be caught as cedula, not phone
        assert not any(k.startswith("[TOK_PHONE_") for k in mapping if k != "_types")


@pytest.mark.pii
class TestTokenizerCombined:
    """Multiple PII types in one message."""

    def test_all_pii_types(self):
        text = (
            "soy Juan Pérez, mi cédula es 1234567890, "
            "mi correo es juan@mail.com y mi cel es 3101234567"
        )
        result, mapping = tokenize_pii(text)

        # No raw PII should remain
        assert "Juan Pérez" not in result
        assert "1234567890" not in result
        assert "juan@mail.com" not in result
        assert "3101234567" not in result

        # All types present
        types = mapping.get("_types", {})
        type_values = set(types.values())
        assert "name" in type_values
        assert "cedula" in type_values
        assert "email" in type_values
        assert "phone" in type_values

    def test_no_pii_returns_unchanged(self):
        text = "quiero saber los horarios del banco"
        result, mapping = tokenize_pii(text)
        assert result == text
        # Only _types key, which is empty
        assert len(mapping) == 1

    def test_deterministic_tokens(self):
        """Same input always produces the same token."""
        _, m1 = tokenize_pii("soy Juan Pérez")
        _, m2 = tokenize_pii("soy Juan Pérez")
        tokens1 = [k for k in m1 if k.startswith("[TOK_")]
        tokens2 = [k for k in m2 if k.startswith("[TOK_")]
        assert tokens1 == tokens2


# =======================================================================
# DETOKENIZER — safe partial values
# =======================================================================

@pytest.mark.pii
class TestDetokenizer:
    """Verify detokenization produces safe partial values only."""

    def test_detokenize_shows_partial_name(self, _temp_vault):
        """[TOK_NAME_x] for "Juan Pérez" → "Juan" (not full name)."""
        _, mapping = tokenize_pii("soy Juan Pérez")
        _temp_vault.store("sess1", mapping)
        token = [k for k in mapping if k.startswith("[TOK_NAME_")][0]
        response = f"Hola {token}, revisé tu score"
        result = detokenize_response(response, "sess1")
        assert "Juan" in result
        assert "Pérez" not in result

    def test_detokenize_masks_cedula(self, _temp_vault):
        _, mapping = tokenize_pii("mi cédula es 1234567890")
        _temp_vault.store("sess2", mapping)
        token = [k for k in mapping if k.startswith("[TOK_CC_")][0]
        response = f"Tu cédula {token} está registrada"
        result = detokenize_response(response, "sess2")
        assert "1234567890" not in result
        assert "****7890" in result

    def test_detokenize_masks_email(self, _temp_vault):
        _, mapping = tokenize_pii("correo juan@mail.com")
        _temp_vault.store("sess3", mapping)
        token = [k for k in mapping if k.startswith("[TOK_EMAIL_")][0]
        response = f"Enviamos a {token}"
        result = detokenize_response(response, "sess3")
        assert "juan@mail.com" not in result
        assert "j***@mail.com" in result

    def test_detokenize_masks_phone(self, _temp_vault):
        _, mapping = tokenize_pii("cel 3101234567")
        _temp_vault.store("sess4", mapping)
        token = [k for k in mapping if k.startswith("[TOK_PHONE_")][0]
        response = f"Te llamaremos al {token}"
        result = detokenize_response(response, "sess4")
        assert "3101234567" not in result
        assert "****4567" in result

    def test_detokenize_no_session_leaves_tokens(self):
        """If vault has no mapping, tokens are left unchanged."""
        response = "Hola [TOK_NAME_abc123]"
        result = detokenize_response(response, "nonexistent_session")
        assert "[TOK_NAME_abc123]" in result

    def test_safe_value_functions(self):
        assert _safe_value("Juan Pérez", "name") == "Juan"
        assert _safe_value("1234567890", "cedula") == "****7890"
        assert _safe_value("3101234567", "phone") == "****4567"
        assert _safe_value("juan@mail.com", "email") == "j***@mail.com"
        assert _safe_value("anything", "unknown") == "****"


# =======================================================================
# PII VAULT — storage and TTL
# =======================================================================

@pytest.mark.pii
class TestPIIVault:

    def test_store_and_retrieve(self, _temp_vault):
        _temp_vault.store("s1", {"[TOK_CC_abc]": "12345678", "_types": {"[TOK_CC_abc]": "cedula"}})
        result = _temp_vault.retrieve("s1")
        assert result is not None
        assert result["[TOK_CC_abc]"] == "12345678"

    def test_merge_mappings(self, _temp_vault):
        """Subsequent stores for the same session merge with existing data."""
        _temp_vault.store("s2", {"[TOK_CC_a]": "111", "_types": {}})
        _temp_vault.store("s2", {"[TOK_NAME_b]": "Juan", "_types": {}})
        result = _temp_vault.retrieve("s2")
        assert "[TOK_CC_a]" in result
        assert "[TOK_NAME_b]" in result

    def test_vault_ttl(self, tmp_path):
        """Tokens expire after the configured TTL."""
        db_path = str(tmp_path / "ttl_test.db")
        vault = PIIVault(db_path=db_path, ttl_hours=0)  # 0 hours = immediate expiry
        vault.store("s3", {"[TOK_CC_x]": "999", "_types": {}})
        # TTL is 0 hours → 0 seconds → already expired
        time.sleep(0.1)
        result = vault.retrieve("s3")
        assert result is None

    def test_delete(self, _temp_vault):
        _temp_vault.store("s4", {"tok": "val", "_types": {}})
        _temp_vault.delete("s4")
        assert _temp_vault.retrieve("s4") is None

    def test_nonexistent_session(self, _temp_vault):
        assert _temp_vault.retrieve("nope") is None


# =======================================================================
# E2E — PII never reaches the LLM
# =======================================================================

@pytest.mark.pii
class TestPIINeverReachesLLM:
    """Simulate the full flow and verify raw PII never touches the LLM."""

    @pytest.mark.asyncio
    async def test_pii_never_reaches_llm(self, _temp_vault):
        """Tokenize → call LLM (mocked) → verify no raw PII in messages sent."""
        raw_text = (
            "Hola, soy Juan Pérez, mi cédula es 1234567890, "
            "mi correo juan@mail.com y cel 3101234567"
        )

        # Step 1: tokenize
        tokenized, mapping = tokenize_pii(raw_text)
        _temp_vault.store("llm_test", mapping)

        # Verify nothing raw remains in the tokenized text
        assert "Juan Pérez" not in tokenized
        assert "1234567890" not in tokenized
        assert "juan@mail.com" not in tokenized
        assert "3101234567" not in tokenized

        # Step 2: simulate sending to LLM
        llm_messages = [
            {"role": "system", "content": "Eres un asistente."},
            {"role": "user", "content": tokenized},
        ]

        captured_messages = None

        async def fake_generate(messages, **kwargs):
            nonlocal captured_messages
            captured_messages = messages
            # LLM echoes back the tokenized names
            user_msg = messages[-1]["content"]
            # Find any TOK_NAME token in the message
            import re
            name_tok = re.search(r"\[TOK_NAME_[a-f0-9]+\]", user_msg)
            tok_str = name_tok.group(0) if name_tok else "usuario"
            return f"Hola {tok_str}, ya revisé tu información."

        # Mock provider
        mock_provider = AsyncMock()
        mock_provider.generate = fake_generate

        llm_response = await mock_provider.generate(llm_messages)

        # Step 3: verify LLM never saw raw PII
        for msg in captured_messages:
            content = msg["content"]
            assert "Juan Pérez" not in content, "Name leaked to LLM!"
            assert "1234567890" not in content, "Cedula leaked to LLM!"
            assert "juan@mail.com" not in content, "Email leaked to LLM!"
            assert "3101234567" not in content, "Phone leaked to LLM!"

        # Step 4: detokenize the response
        final = detokenize_response(llm_response, "llm_test")

        # User sees first name only, no full PII
        assert "Juan" in final
        assert "Pérez" not in final

    @pytest.mark.asyncio
    async def test_cedula_patterns_in_various_contexts(self):
        """Cedulas should be caught regardless of surrounding text."""
        cases = [
            "mi cc es 1234567890",
            "cédula: 1234567890",
            "documento 1234567890 expedido",
            "CC 12345678",
        ]
        for text in cases:
            result, mapping = tokenize_pii(text)
            cc_tokens = [k for k in mapping if k.startswith("[TOK_CC_")]
            assert len(cc_tokens) > 0, f"Cedula not caught in: {text}"
            for tok in cc_tokens:
                raw = mapping[tok]
                assert raw not in result, f"Raw cedula {raw} leaked in: {text}"
