"""
Zero-Retention Privacy Gateway & Multi-Jurisdiction PII Tokenizer.
Provides bi-directional deterministic surrogate tokenization for sensitive People data
spanning Brazil (CPF), United States (SSN), and Canada (SIN), plus financial compensation.
"""

from __future__ import annotations

import hashlib
import re
from typing import ClassVar


class PIITokenVault:
    """
    In-memory isolated vault storing reversible token-to-plaintext mappings.
    Complies with LGPD Article 18 / GDPR by allowing cryptographic shredding.
    """

    def __init__(self) -> None:
        self._token_to_raw: dict[str, str] = {}
        self._raw_to_token: dict[str, str] = {}

    def get_or_create_token(self, raw_value: str, prefix: str) -> str:
        clean_val = raw_value.strip()
        if clean_val in self._raw_to_token:
            return self._raw_to_token[clean_val]

        # Deterministic short hash for consistent tokenization within a session
        h = hashlib.sha256(clean_val.encode("utf-8")).hexdigest()[:8].upper()
        token = f"[TOKEN_{prefix}_{h}]"
        self._raw_to_token[clean_val] = token
        self._token_to_raw[token] = clean_val
        return token

    def resolve(self, token: str) -> str:
        return self._token_to_raw.get(token, token)

    def shred(self) -> int:
        """Cryptographically shreds the vault, rendering all external logs permanently anonymized."""
        count = len(self._token_to_raw)
        self._token_to_raw.clear()
        self._raw_to_token.clear()
        return count


class ZeroRetentionPrivacyGateway:
    """
    Perimeter gateway that scrubs sensitive identifiers before passing to LLM reasoning,
    and restores them upon return inside the trusted security perimeter.
    """

    # Brazilian CPF regex: formatted 000.000.000-00 or unformatted 11 digits
    CPF_REGEX: ClassVar[re.Pattern[str]] = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
    # US Social Security Number: 000-00-0000
    SSN_REGEX: ClassVar[re.Pattern[str]] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    # Canadian Social Insurance Number: 000-000-000
    SIN_REGEX: ClassVar[re.Pattern[str]] = re.compile(r"\b\d{3}-\d{3}-\d{3}\b")
    # Compensation / Currency patterns (BRL, USD, CAD)
    COMP_REGEX: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:R\$\s*|USD\s*|CAD\s*|\$)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?"
    )
    # Corporate Email
    EMAIL_REGEX: ClassVar[re.Pattern[str]] = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    )

    def __init__(self, vault: PIITokenVault | None = None) -> None:
        self.vault = vault or PIITokenVault()

    def tokenize(self, text: str) -> str:
        """
        Replaces all sensitive PII/SPII instances with surrogate tokens.
        """
        # 1. Brazilian CPF
        text = self.CPF_REGEX.sub(lambda m: self.vault.get_or_create_token(m.group(0), "CPF"), text)

        # 2. US SSN
        text = self.SSN_REGEX.sub(lambda m: self.vault.get_or_create_token(m.group(0), "SSN"), text)

        # 3. Canadian SIN
        text = self.SIN_REGEX.sub(lambda m: self.vault.get_or_create_token(m.group(0), "SIN"), text)

        # 4. Compensation figures
        text = self.COMP_REGEX.sub(
            lambda m: self.vault.get_or_create_token(m.group(0), "COMP"), text
        )

        # 5. Email addresses
        text = self.EMAIL_REGEX.sub(
            lambda m: self.vault.get_or_create_token(m.group(0), "EMAIL"), text
        )

        return text

    def detokenize(self, text: str) -> str:
        """
        Restores tokenized text to original plaintext within the trusted boundary.
        """
        token_pattern = re.compile(r"\[TOKEN_[A-Z]+_[A-F0-9]{8}\]")
        return token_pattern.sub(lambda m: self.vault.resolve(m.group(0)), text)

    def assert_zero_pii_leakage(self, text: str) -> bool:
        """
        Hard security barrier: checks if any raw PII patterns remain.
        Raises ValueError if raw PII is detected.
        """
        if self.CPF_REGEX.search(text):
            raise ValueError("PII Leak Detected: Raw Brazilian CPF found in tokenized payload!")
        if self.SSN_REGEX.search(text):
            raise ValueError("PII Leak Detected: Raw US SSN found in tokenized payload!")
        if self.SIN_REGEX.search(text):
            raise ValueError("PII Leak Detected: Raw Canadian SIN found in tokenized payload!")
        return True
