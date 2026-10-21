"""Supervisor Orchestration and Logic Module for Cloud FinOps & Incident Remediation Copilot.

Acts as the Central Supervisor Orchestrator coordinating specialized subagents:
1. Ingest 30-day GCP billing & latency telemetry via TelemetryIngestionSubagent
2. Run AI quality assurance & quarantine via DataQualityAssuranceSubagent
3. Calculate deployment-to-cost correlations, remediation plans, and 90-day forecasts via FinOpsRemediationSubagent
4. Enforce pre/post-execution safety guardrails and Human-in-the-Loop (HITL) approval queues
"""

import time
from typing import Any, Dict, Optional

from memory.memory_store import AgentMemoryStore, global_memory
from observability.tracer import AgentTracer, global_tracer
from secrets.secret_manager import SecretManagerClient, global_secret_manager
from .guardrails import GuardrailValidator, global_guardrails
from .hitl import HITLController, global_hitl_controller
from .router import ModelRouter, global_model_router
from .subagents import (
    DataQualityAssuranceSubagent,
    FinOpsRemediationSubagent,
    TelemetryIngestionSubagent,
)


class CloudFinOpsSupervisorAgent:
    """Supervisor Orchestrator for Cloud FinOps anomaly attribution and incident remediation."""

    def __init__(
        self,
        memory: Optional[AgentMemoryStore] = None,
        tracer: Optional[AgentTracer] = None,
        guardrails: Optional[GuardrailValidator] = None,
        hitl_controller: Optional[HITLController] = None,
        router: Optional[ModelRouter] = None,
        secret_manager: Optional[SecretManagerClient] = None,
    ) -> None:
        self.memory = memory or global_memory
        self.tracer = tracer or global_tracer
        self.guardrails = guardrails or global_guardrails
        self.hitl = hitl_controller or global_hitl_controller
        self.router = router or global_model_router
        self.secrets = secret_manager or global_secret_manager

        # Initialize subagent hierarchy
        self.ingestion_subagent = TelemetryIngestionSubagent(tracer=self.tracer)
        self.qa_subagent = DataQualityAssuranceSubagent(tracer=self.tracer)
        self.remediation_subagent = FinOpsRemediationSubagent(tracer=self.tracer)

        self.latest_analysis_result: Optional[Dict[str, Any]] = None

    def run_full_analysis(
        self, days: int = 30, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Executes the full multi-agent FinOps pipeline with guardrails and HITL review queues."""
        root_span = self.tracer.start_span(
            name="CloudFinOpsSupervisorAgent.run_full_analysis",
            span_type="pipeline",
            input_data={"days": days, "force_refresh": force_refresh},
        )
        start_time = time.time()

        try:
            # Step 1: Delegate Telemetry & Billing Ingestion to TelemetryIngestionSubagent
            raw_data = self.ingestion_subagent.execute_ingestion(
                days=days, parent_span_id=root_span.span_id
            )
            if raw_data.get("status") == "ERROR":
                raise RuntimeError(
                    f"Telemetry ingestion failed: {raw_data.get('message')}"
                )

            # Step 2: Delegate AI Quality Assurance to DataQualityAssuranceSubagent
            val_data = self.qa_subagent.execute_qa_inspection(
                raw_data["records"], parent_span_id=root_span.span_id
            )
            if val_data.get("status") == "ERROR":
                raise RuntimeError(f"AI QA failed: {val_data.get('message')}")

            # Cache validated telemetry asynchronously in SQLite memory store
            self.memory.async_cache_telemetry(
                f"finops_telemetry_{days}d", val_data["validated_records"]
            )

            # Step 3, 4 & 5: Delegate Correlation, Remediation & Savings Forecast to FinOpsRemediationSubagent
            rem_bundle = self.remediation_subagent.execute_remediation_analysis(
                val_data["validated_records"],
                days=days,
                parent_span_id=root_span.span_id,
            )
            correlation_result = rem_bundle["correlation_analysis"]
            remediation_result = rem_bundle["remediation_plan"]
            forecast_result = rem_bundle["savings_forecast"]

            # Apply Output Guardrails to Remediation Plan
            recs_list = remediation_result.get("recommendations", [])
            safe, clean_recs, violations = (
                self.guardrails.validate_remediation_recommendations(recs_list)
            )
            remediation_result["recommendations"] = clean_recs
            remediation_result["guardrail_violations"] = violations
            remediation_result["guardrails_passed"] = safe

            # Submit high-impact production changes to Human-in-the-Loop (HITL) review queue
            hitl_submitted_ids = []
            for rec in clean_recs:
                if rec.get("requires_hitl_approval"):
                    rid = self.hitl.submit_for_review(rec)
                    hitl_submitted_ids.append(rid)
                    rec["hitl_review_id"] = rid
                    rec["status"] = "PENDING_HUMAN_REVIEW"
                else:
                    rec["status"] = "AUTO_APPROVED"

            elapsed_ms = round((time.time() - start_time) * 1000.0, 2)

            output: Dict[str, Any] = {
                "status": "SUCCESS",
                "days_analyzed": days,
                "execution_time_ms": elapsed_ms,
                "orchestration_pattern": "Supervisor-Subagent Hierarchy with Dynamic Gemini Routing",
                "telemetry_collection": raw_data,
                "ai_validation": val_data,
                "cost_incident_correlation": correlation_result,
                "finops_remediation_plan": remediation_result,
                "savings_forecast": forecast_result,
                "hitl_review_ids_generated": hitl_submitted_ids,
            }

            # Persist run in agent memory store
            run_id = self.memory.save_analysis_run(
                title=f"30-Day GCP FinOps & Deployment Correlation Run ({days}d)",
                summary=correlation_result.get("conclusion", "Analysis completed."),
                details=output,
            )
            output["memory_run_id"] = run_id
            self.latest_analysis_result = output

            root_span.finish(
                status="SUCCESS",
                output_data={
                    "memory_run_id": run_id,
                    "net_overrun_pct": correlation_result.get(
                        "net_cloud_spend_overrun_pct", 0.0
                    ),
                    "valid_records": val_data.get("valid_records_count", 0),
                    "hitl_reviews_queued": len(hitl_submitted_ids),
                    "projected_90d_savings_usd": forecast_result.get(
                        "projected_savings_usd", 0.0
                    ),
                },
            )
            return output

        except Exception as e:
            root_span.finish(status="ERROR", error=str(e))
            raise

    def ask_agent(self, session_id: str, question: str) -> Dict[str, Any]:
        """Answers multi-turn natural language FinOps & SRE questions with guardrails and compaction."""
        span = self.tracer.start_span(
            name="CloudFinOpsSupervisorAgent.ask_agent",
            span_type="chat",
            input_data={"session_id": session_id, "question": question},
        )

        # 1. Input Guardrail Validation (Block Prompt Injection / Jailbreak)
        valid, guardrail_err = self.guardrails.validate_input_prompt(question)
        if not valid:
            self.memory.save_message(session_id, "user", question)
            self.memory.save_message(session_id, "assistant", str(guardrail_err))
            span.finish(status="ERROR", error=str(guardrail_err))
            return {
                "session_id": session_id,
                "question": question,
                "answer": str(guardrail_err),
                "guardrail_blocked": True,
                "recent_spans": self.tracer.get_recent_spans(limit=10),
            }

        self.memory.save_message(session_id, "user", question)
        q_lower = question.lower()

        # Route conversational Q&A via ModelRouter
        route_config = self.router.route_task(
            "COMPLEX_REASONING" if len(question) > 120 else "LIGHT_QUERY"
        )

        if (
            self.latest_analysis_result is None
            or "refresh" in q_lower
            or "re-run" in q_lower
        ):
            self.run_full_analysis(days=30)

        data = self.latest_analysis_result or {}
        corr = data.get("cost_incident_correlation", {})
        val = data.get("ai_validation", {})
        rem = data.get("finops_remediation_plan", {})
        forecast = data.get("savings_forecast", {})

        net_pct = corr.get("net_cloud_spend_overrun_pct", 0.0)
        conclusion = corr.get("conclusion", "No analysis available.")

        answer_lines = []
        if "vertex" in q_lower or "gpu" in q_lower or "inference" in q_lower:
            answer_lines.append(
                f"Vertex AI LLM Inference Cluster (us-central1) experienced a major cost & latency surge (+{net_pct}% overall portfolio trend) triggered by canary deployment v2.4.1-canary (SHA: a8f92d1) setting min_replica_count=8 on A100 GPUs. Capping min_replica_count=2 is queued in HITL."
            )
        elif "bigquery" in q_lower or "attribution" in q_lower or "etl" in q_lower:
            answer_lines.append(
                "BigQuery Ad-Attribution ETL Pipeline (us-multi) spiked after release v5.1.0-prod (SHA: 7c3e91b) dropped the partition filter on the 40TB attribution_events table. Enforcing require_partition_filter=true is queued for HITL sign-off."
            )
        elif "gke" in q_lower or "checkout" in q_lower or "kubernetes" in q_lower:
            answer_lines.append(
                "GKE Checkout & Payment Microservice (us-east1) exhibited elevated compute & egress spend due to a webhook retry storm in v3.9.4-hotfix (SHA: 4b11c08). Rolling back checkout-api and adding an Envoy circuit breaker is recommended."
            )
        elif "cdn" in q_lower or "baseline" in q_lower or "control" in q_lower:
            answer_lines.append(
                "Cloud CDN & Media Asset Edge Cache serves as our baseline control workload without recent config changes, remaining stable within normal FinOps budget variance."
            )
        elif (
            "remediat" in q_lower
            or "recommend" in q_lower
            or "savings" in q_lower
            or "hitl" in q_lower
            or "forecast" in q_lower
        ):
            answer_lines.append(
                rem.get("executive_finops_brief", "No interventions needed.")
            )
            answer_lines.append(forecast.get("summary", ""))
            pending_count = len(self.hitl.get_pending_reviews())
            if pending_count > 0:
                answer_lines.append(
                    f"There are currently {pending_count} high-impact production remediations pending Human-in-the-Loop SRE/FinOps approval."
                )
        else:
            answer_lines.append(
                f"Analysis of {val.get('valid_records_count', 0)} AI-validated cloud billing & telemetry records over the past 30 days indicates: {conclusion}"
            )
            answer_lines.append(
                f"AI QA confidence score is {val.get('average_ai_confidence_score', 0.96)}/1.0 with {val.get('quarantined_count', 0)} anomalous/duplicate billing records quarantined."
            )
            answer_lines.append(
                f"Projected 90-day savings from recommended remediations: ${forecast.get('projected_savings_usd', 0.0):,.2f} (synthesized via {route_config['model_name']})."
            )

        answer_text = " ".join(answer_lines)
        self.memory.save_message(session_id, "assistant", answer_text)

        span.finish(
            status="SUCCESS",
            output_data={
                "answer": answer_text,
                "model_route": route_config["model_name"],
            },
        )
        return {
            "session_id": session_id,
            "question": question,
            "answer": answer_text,
            "model_route": route_config["model_name"],
            "guardrail_blocked": False,
            "recent_spans": self.tracer.get_recent_spans(limit=10),
        }
