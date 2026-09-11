import pytest

from people_agent_mesh.security.tokenizer import PIITokenVault, ZeroRetentionPrivacyGateway


def test_pii_tokenization_and_detokenization() -> None:
    vault = PIITokenVault()
    gateway = ZeroRetentionPrivacyGateway(vault)

    raw_text = (
        "Employee Ana Silva with CPF 123.456.789-10 and SSN 123-45-6789 "
        "earns R$ 180.000,00 and email ana.silva@company.com"
    )

    tokenized = gateway.tokenize(raw_text)

    # Assert raw PII no longer appears in tokenized text
    assert "123.456.789-10" not in tokenized
    assert "123-45-6789" not in tokenized
    assert "ana.silva@company.com" not in tokenized
    assert "[TOKEN_CPF_" in tokenized
    assert "[TOKEN_SSN_" in tokenized
    assert "[TOKEN_COMP_" in tokenized
    assert "[TOKEN_EMAIL_" in tokenized

    # Assert zero PII invariant check passes
    assert gateway.assert_zero_pii_leakage(tokenized) is True

    # Detokenize inside secure perimeter
    restored = gateway.detokenize(tokenized)
    assert "123.456.789-10" in restored
    assert "123-45-6789" in restored
    assert "ana.silva@company.com" in restored


def test_canadian_sin_tokenization() -> None:
    gateway = ZeroRetentionPrivacyGateway()
    raw = "Canadian engineer with SIN 123-456-789 has offer CAD 160,000"
    tok = gateway.tokenize(raw)

    assert "123-456-789" not in tok
    assert "[TOKEN_SIN_" in tok
    gateway.assert_zero_pii_leakage(tok)


def test_pii_leakage_exception() -> None:
    gateway = ZeroRetentionPrivacyGateway()
    leaked_text = "Here is unmasked CPF: 987.654.321-99"

    with pytest.raises(ValueError, match="PII Leak Detected"):
        gateway.assert_zero_pii_leakage(leaked_text)


def test_cryptographic_vault_shredding() -> None:
    vault = PIITokenVault()
    gateway = ZeroRetentionPrivacyGateway(vault)

    text = "CPF 111.222.333-44 with salary R$ 50.000"
    tok = gateway.tokenize(text)
    assert "[TOKEN_CPF_" in tok

    shredded_count = vault.shred()
    assert shredded_count >= 2

    # After shredding, resolution returns token itself
    restored = gateway.detokenize(tok)
    assert "[TOKEN_CPF_" in restored
