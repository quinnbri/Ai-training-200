"""Agentic Guardrails module for Cloud FinOps & Incident Remediation Copilot.

Implements pre-execution input guardrails to prevent prompt injection and
jailbreak attempts, and post-execution output guardrails to verify that
FinOps/SRE recommendations never execute unrecoverable infrastructure deletion.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


class GuardrailValidator:
    """Validates inputs and outputs against strict security and SRE safety rules."""

    INJECTION_PATTERNS = [
        r"(?i)\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions|rules|prompts|commands)\b",
        r"(?i)\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay\s+as)\s+(?:a\s+)?(?:jailbroken|unrestricted|evil|hacker|rogue)\b",
        r"(?i)\b(?:system_prompt|secret_key|api_key|dump_memory|bypass_guardrails)\b",
    ]

    UNSAFE_REMEDIATION_PATTERNS = [
        r"(?i)\b(?:gcloud\s+projects\s+delete|terraform\s+destroy|drop\s+database|rm\s+-rf\s+/|kubectl\s+delete\s+namespace\s+prod)\b",
        r"(?i)\b(?:destroy|wipe|delete|purge|sabotage)\s+(?:all\s+)?(?:production\s+clusters|databases|billing\s+accounts|backups)\b",
    ]

    def __init__(self) -> None:
        self.compiled_injections = [re.compile(p) for p in self.INJECTION_PATTERNS]
        self.compiled_unsafe_remediations = [
            re.compile(p) for p in self.UNSAFE_REMEDIATION_PATTERNS
        ]

    def validate_input_prompt(self, user_prompt: str) -> Tuple[bool, Optional[str]]:
        """Inspects user input for adversarial prompt injection or jailbreak attempts."""
        if not isinstance(user_prompt, str):
            return True, None

        for pattern in self.compiled_injections:
            if pattern.search(user_prompt):
                return (
                    False,
                    "SECURITY_ALERT: Input prompt blocked by Agent Guardrail (Potential Prompt Injection / Jailbreak attempt detected).",
                )
        return True, None

    def validate_remediation_recommendations(
        self, recommendations: List[Dict[str, Any]]
    ) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
        """Inspects generated FinOps remediations to ensure no destructive production commands exist."""
        safe_recs: List[Dict[str, Any]] = []
        violations: List[str] = []

        for rec in recommendations:
            action = str(rec.get("action_item", ""))
            cmd = str(rec.get("remediation_command", ""))
            rationale = str(rec.get("rationale", ""))
            combined_text = f"{action} {cmd} {rationale}"

            is_safe = True
            for pattern in self.compiled_unsafe_remediations:
                if pattern.search(combined_text):
                    is_safe = False
                    violations.append(
                        f"Unsafe remediation blocked for workload '{rec.get('workload')}': Command contains prohibited destructive infrastructure operation."
                    )
                    break

            if is_safe:
                safe_recs.append(rec)

        return len(violations) == 0, safe_recs, violations


# Global default guardrail validator
global_guardrails = GuardrailValidator()
