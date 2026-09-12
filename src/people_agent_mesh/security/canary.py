"""
Cryptographic Canary Token Manager & Tripwire Leakage Defense.
Embeds high-entropy canary tokens into sensitive People Operations records and prompt contexts.
Detects model exfiltration or RAG retrieval leakage, triggering immediate security containment.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from typing import Any

from pydantic import BaseModel, Field


class CanaryLeakageException(Exception):
    """Raised when an active canary token is detected in untrusted model output."""

    def __init__(self, token: str, context: str | None = None) -> None:
        super().__init__(
            f"SECURITY TRIPWIRE TRIGGERED: Canary token '{token}' detected in output payload! "
            f"Immediate exfiltration containment required."
        )
        self.token = token
        self.context = context


class CanaryMetadata(BaseModel):
    token: str
    target_record_id: str
    purpose: str
    created_at_epoch: float = Field(default_factory=time.time)
    tripped: bool = False
    tripped_at_epoch: float | None = None


class CanaryManager:
    """
    Manages deterministic and ephemeral canary tripwires.
    Canary format: CANARY_SEC_TRIPWIRE_<8-BYTE-HEX>
    """

    CANARY_PATTERN: re.Pattern[str] = re.compile(r"\bCANARY_SEC_TRIPWIRE_[A-F0-9]{16}\b")

    def __init__(self) -> None:
        self._canaries: dict[str, CanaryMetadata] = {}

    def generate_canary(self, target_record_id: str, purpose: str = "PII_DEFENSE") -> str:
        """
        Generates a unique, high-entropy canary token and registers it in the vault.
        """
        entropy = secrets.token_hex(8).upper()
        token = f"CANARY_SEC_TRIPWIRE_{entropy}"
        meta = CanaryMetadata(
            token=token,
            target_record_id=target_record_id,
            purpose=purpose,
        )
        self._canaries[token] = meta
        return token

    def generate_deterministic_canary(
        self, target_record_id: str, secret_seed: str, purpose: str = "GOLDEN_EVAL"
    ) -> str:
        """
        Generates a reproducible canary token for CI golden eval suites.
        """
        h = hashlib.sha256(f"{target_record_id}:{secret_seed}".encode()).hexdigest()[:16].upper()
        token = f"CANARY_SEC_TRIPWIRE_{h}"
        meta = CanaryMetadata(
            token=token,
            target_record_id=target_record_id,
            purpose=purpose,
        )
        self._canaries[token] = meta
        return token

    def scan_for_leaks(self, text: str) -> list[str]:
        """
        Scans text for any registered or syntactically valid canary tokens.
        Returns a list of matched canary tokens.
        """
        found = self.CANARY_PATTERN.findall(text)
        tripped_tokens: list[str] = []
        for token in found:
            tripped_tokens.append(token)
            if token in self._canaries:
                meta = self._canaries[token]
                meta.tripped = True
                meta.tripped_at_epoch = time.time()
        return tripped_tokens

    def assert_zero_canary_leakage(self, text: str) -> bool:
        """
        Hard security barrier: checks if any canary tokens were leaked into output.
        Raises CanaryLeakageException if any are detected.
        """
        leaks = self.scan_for_leaks(text)
        if leaks:
            raise CanaryLeakageException(token=leaks[0], context=text[:200])
        return True

    def get_tripwire_audit(self) -> list[dict[str, Any]]:
        """Returns metadata for all registered canary tripwires."""
        return [meta.model_dump() for meta in self._canaries.values()]
