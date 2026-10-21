"""LLM Model Routing module for Cloud FinOps & Incident Remediation Copilot.

Dynamically routes agent inference tasks to appropriate Gemini model tiers
based on task complexity, telemetry payload volume, and reasoning depth requirements.
"""

from typing import Any, Dict


class ModelRouter:
    """Routes agent steps and subagent prompts to the optimal Gemini LLM tier."""

    TIERS: Dict[str, Dict[str, Any]] = {
        "FAST_VALIDATION": {
            "model_name": "gemini-2.5-flash",
            "temperature": 0.1,
            "max_output_tokens": 1024,
            "description": "High-speed, cost-efficient tier for billing schema validation, PII inspection, and deduplication.",
        },
        "LIGHT_QUERY": {
            "model_name": "gemini-2.5-flash-lite",
            "temperature": 0.2,
            "max_output_tokens": 512,
            "description": "Ultra-low-latency tier for conversational FinOps Q&A and HITL queue status checks.",
        },
        "COMPLEX_REASONING": {
            "model_name": "gemini-2.5-pro",
            "temperature": 0.2,
            "max_output_tokens": 4096,
            "description": "Deep reasoning tier for multi-workload deployment-to-cost correlation and latency anomaly attribution.",
        },
        "EXECUTIVE_SYNTHESIS": {
            "model_name": "gemini-2.5-pro",
            "temperature": 0.3,
            "max_output_tokens": 2048,
            "description": "High-fidelity tier for synthesizing SRE rollback runbooks and executive FinOps savings briefs.",
        },
    }

    @classmethod
    def route_task(cls, task_type: str, payload_size: int = 0) -> Dict[str, Any]:
        """Selects the optimal Gemini model tier and configuration for a given task type."""
        task_upper = str(task_type).upper()

        if "VALIDAT" in task_upper or "INGEST" in task_upper or "CLEAN" in task_upper:
            return cls.TIERS["FAST_VALIDATION"]
        elif (
            "REMEDIAT" in task_upper
            or "RECOMMEND" in task_upper
            or "POLICY" in task_upper
            or "SYNTHES" in task_upper
        ):
            return cls.TIERS["EXECUTIVE_SYNTHESIS"]
        elif (
            "ANALY" in task_upper
            or "CORRELAT" in task_upper
            or "IMPACT" in task_upper
            or "FORECAST" in task_upper
        ):
            return cls.TIERS["COMPLEX_REASONING"]
        else:
            if payload_size > 5000:
                return cls.TIERS["COMPLEX_REASONING"]
            return cls.TIERS["LIGHT_QUERY"]


# Global default model router
global_model_router = ModelRouter()
