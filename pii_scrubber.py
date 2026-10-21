"""PII and Credential Scrubbing module for Cloud FinOps & Incident Remediation Copilot.

Actively scans and redacts personally identifiable information (PII) and sensitive
cloud credentials such as email addresses, phone numbers, SSNs, API keys/tokens,
and on-call engineer names from memory payloads, structured logs, and trace spans.
"""

import re
from typing import Any


class PIIScrubber:
    """Scrubs PII and sensitive secrets from strings, dictionaries, lists, and log payloads."""

    PATTERNS = [
        # Email addresses
        (
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
            "[REDACTED_EMAIL]",
        ),
        # US Phone numbers (e.g., 415-555-0199, (415) 555-0199, +1-415-555-0199)
        (
            r"\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b",
            "[REDACTED_PHONE]",
        ),
        # Social Security Numbers (SSN)
        (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
        # API keys / Bearer tokens / GCP keys (e.g., AIza..., sk-..., ya29...)
        (
            r"\b(?:AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z]{16,}|ya29\.[0-9A-Za-z_-]{20,})\b",
            "[REDACTED_API_KEY]",
        ),
        # Credit Card / Billing Account Numbers (e.g., Billing-Acct: 01A2B3-45C6D7-89E0F1)
        (
            r"(?i)\b(?:billing[-_ ]?acct|account[-_ ]?id|card[-_ ]?number)\s*[:=]?\s*([A-Z0-9]{4,6}[- ][A-Z0-9]{4,6}[- ][A-Z0-9]{4,6})\b",
            "Billing-Acct [REDACTED_BILLING_ACCT]",
        ),
        # On-call engineer / author names in incident or deployment logs
        (
            r"(?i)\b(?:oncall|engineer|author|deployer|reviewer|contact)\s*[:=]\s*([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b",
            "\\g<0> ([REDACTED_NAME])",
        ),
    ]

    def __init__(self) -> None:
        self.compiled_patterns = [(re.compile(p), r) for p, r in self.PATTERNS]

    def scrub_text(self, text: str) -> str:
        """Redacts PII and secret patterns from a plain text string."""
        if not isinstance(text, str):
            return str(text)
        scrubbed = text
        for pattern, replacement in self.compiled_patterns:
            scrubbed = pattern.sub(replacement, scrubbed)
        return scrubbed

    def scrub_data(self, data: Any) -> Any:
        """Recursively scrubs PII from dictionaries, lists, strings, and tuples."""
        if isinstance(data, str):
            return self.scrub_text(data)
        elif isinstance(data, dict):
            return {str(k): self.scrub_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.scrub_data(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self.scrub_data(item) for item in data)
        elif isinstance(data, (int, float, bool)) or data is None:
            return data
        else:
            try:
                return self.scrub_text(str(data))
            except Exception:
                return "[UNSCRUBBABLE_DATA]"


# Global shared scrubber singleton
global_pii_scrubber = PIIScrubber()
