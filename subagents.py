"""Multi-Agent Subagent Hierarchy for Cloud FinOps & Incident Remediation Copilot.

Implements specialized subagents that coordinate under the central supervisor:
- TelemetryIngestionSubagent: Handles cloud billing/latency ingestion and schema retry recovery.
- DataQualityAssuranceSubagent: Manages anomaly quarantine, deduplication, and confidence scoring.
- FinOpsRemediationSubagent: Handles deployment-to-cost correlation, remediation synthesis, and ROI forecasting.
"""

from typing import Any, Dict, List, Optional

from observability.tracer import AgentTracer, Span, global_tracer
from tools.finops_tools import (
    MONITORED_CLOUD_WORKLOADS,
    correlate_cost_and_incident_spikes_tool,
    fetch_cloud_telemetry_and_billing_tool,
    generate_finops_remediation_plan_tool,
    simulate_cost_savings_forecast_tool,
    validate_telemetry_data_ai_tool,
)
from .router import global_model_router


class BaseSubagent:
    """Base class for specialized autonomous FinOps/SRE subagent workers."""

    def __init__(
        self, name: str, role: str, tracer: Optional[AgentTracer] = None
    ) -> None:
        self.name = name
        self.role = role
        self.tracer = tracer or global_tracer
        self.router = global_model_router

    def log_subagent_span(
        self,
        action: str,
        input_data: Any,
        parent_span_id: Optional[str] = None,
    ) -> Span:
        return self.tracer.start_span(
            name=f"{self.name}.{action}",
            span_type="subagent",
            parent_span_id=parent_span_id,
            input_data=input_data,
            metadata={"role": self.role},
        )


class TelemetryIngestionSubagent(BaseSubagent):
    """Responsible for retrieving GCP billing exports, latency metrics, and managing ingestion recovery."""

    def __init__(self, tracer: Optional[AgentTracer] = None) -> None:
        super().__init__(
            name="TelemetryIngestionSubagent",
            role="Cloud Billing & Telemetry Ingestor with Auto-Recovery",
            tracer=tracer,
        )

    def execute_ingestion(
        self, days: int = 30, parent_span_id: Optional[str] = None
    ) -> Dict[str, Any]:
        span = self.log_subagent_span(
            "execute_ingestion", {"days": days}, parent_span_id
        )
        route_config = self.router.route_task("INGEST")

        result = fetch_cloud_telemetry_and_billing_tool(days=days)
        if result.get("status") == "ERROR":
            # Self-correction recovery attempt guided by tool's recovery_instruction
            fallback_days = max(1, min(30, int(days) if isinstance(days, int) else 30))
            result = fetch_cloud_telemetry_and_billing_tool(days=fallback_days)
            result["recovered_from_error"] = True

        result["llm_route_used"] = route_config["model_name"]
        result["subagent"] = self.name
        span.finish(
            status="SUCCESS" if result.get("status") == "SUCCESS" else "ERROR",
            output_data={
                "status": result.get("status"),
                "total_raw_records": result.get("total_raw_records", 0),
                "llm_route_used": route_config["model_name"],
            },
        )
        return result


class DataQualityAssuranceSubagent(BaseSubagent):
    """Responsible for AI billing anomaly detection, deduplication, and QA quarantine."""

    def __init__(self, tracer: Optional[AgentTracer] = None) -> None:
        super().__init__(
            name="DataQualityAssuranceSubagent",
            role="AI Billing & Telemetry QA Quarantine Specialist",
            tracer=tracer,
        )

    def execute_qa_inspection(
        self,
        raw_records: List[Dict[str, Any]],
        parent_span_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        span = self.log_subagent_span(
            "execute_qa_inspection",
            {"record_count": len(raw_records)},
            parent_span_id,
        )
        route_config = self.router.route_task(
            "VALIDAT", payload_size=len(raw_records) * 100
        )

        result = validate_telemetry_data_ai_tool(raw_records)
        result["llm_route_used"] = route_config["model_name"]
        result["subagent"] = self.name

        span.finish(
            status="SUCCESS" if result.get("status") == "SUCCESS" else "ERROR",
            output_data={
                "status": result.get("status"),
                "valid_records_count": result.get("valid_records_count", 0),
                "quarantined_count": result.get("quarantined_count", 0),
                "average_ai_confidence_score": result.get(
                    "average_ai_confidence_score", 0.0
                ),
            },
        )
        return result


class FinOpsRemediationSubagent(BaseSubagent):
    """Responsible for deployment-to-cost correlation, SRE remediation runbooks, and 90-day savings forecasts."""

    def __init__(self, tracer: Optional[AgentTracer] = None) -> None:
        super().__init__(
            name="FinOpsRemediationSubagent",
            role="Principal Cloud FinOps & SRE Remediation Architect",
            tracer=tracer,
        )

    def execute_remediation_analysis(
        self,
        validated_records: List[Dict[str, Any]],
        days: int = 30,
        parent_span_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        span = self.log_subagent_span(
            "execute_remediation_analysis",
            {"valid_count": len(validated_records), "days": days},
            parent_span_id,
        )
        route_config = self.router.route_task(
            "REMEDIAT", payload_size=len(validated_records) * 200
        )

        correlation = correlate_cost_and_incident_spikes_tool(
            validated_records=validated_records,
            workloads=MONITORED_CLOUD_WORKLOADS,
            days_analyzed=days,
        )
        remediation_plan = generate_finops_remediation_plan_tool(correlation)
        savings_forecast = simulate_cost_savings_forecast_tool(
            remediation_plan, horizon_days=90
        )

        combined_result = {
            "status": (
                "SUCCESS"
                if correlation.get("status") == "SUCCESS"
                and remediation_plan.get("status") == "SUCCESS"
                else "ERROR"
            ),
            "correlation_analysis": correlation,
            "remediation_plan": remediation_plan,
            "savings_forecast": savings_forecast,
            "llm_route_used": route_config["model_name"],
            "subagent": self.name,
        }

        span.finish(
            status=combined_result["status"],
            output_data={
                "net_cloud_spend_overrun_pct": correlation.get(
                    "net_cloud_spend_overrun_pct", 0.0
                ),
                "recommendation_count": remediation_plan.get(
                    "recommendation_count", 0
                ),
                "projected_90d_savings_usd": savings_forecast.get(
                    "projected_savings_usd", 0.0
                ),
            },
        )
        return combined_result
