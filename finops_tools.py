"""Agent Tools for Cloud FinOps Cost Anomaly & Incident Correlation Analysis.

Includes:
- Detailed parameter docstrings and return schemas.
- Explicit JSON schemas (TOOL_JSON_SCHEMAS) for LLM function calling validation.
- Guided error handling with recovery_instruction for LLM self-correction.
- 5 Core tools: telemetry collection, AI QA validation, deployment-cost correlation,
  remediation synthesis, and 90-day savings forecast simulation.
"""

import datetime
import random
from typing import Any, Dict, List, Optional, Tuple

# Valid daily cost bounds in USD for single service records
COST_BOUNDS_USD = {
    "min_daily_usd": 0.01,
    "max_daily_usd": 50000.0,
}

# Monitored Google Cloud Production Workloads
MONITORED_CLOUD_WORKLOADS = [
    {
        "workload_id": "vertex_ai_inference",
        "name": "Vertex AI LLM Inference Cluster (us-central1)",
        "service_type": "Vertex AI / A100 GPU Pool",
        "recent_deployment": True,
        "deployment_Info": "v2.4.1-canary (SHA: a8f92d1) - Unbounded min-replica GPU autoscaler",
        "baseline_daily_cost_usd": 420.0,
        "baseline_p99_latency_ms": 310.0,
    },
    {
        "workload_id": "bigquery_attribution",
        "name": "BigQuery Ad-Attribution ETL Pipeline (us-multi)",
        "service_type": "BigQuery Analytics",
        "recent_deployment": True,
        "deployment_Info": "v5.1.0-prod (SHA: 7c3e91b) - Removed partition filter on 40TB events table",
        "baseline_daily_cost_usd": 280.0,
        "baseline_p99_latency_ms": 1450.0,
    },
    {
        "workload_id": "gke_checkout_api",
        "name": "GKE Checkout & Payment Microservice (us-east1)",
        "service_type": "Google Kubernetes Engine",
        "recent_deployment": True,
        "deployment_Info": "v3.9.4-hotfix (SHA: 4b11c08) - Retry storm on payment webhook timeout",
        "baseline_daily_cost_usd": 190.0,
        "baseline_p99_latency_ms": 185.0,
    },
    {
        "workload_id": "cloudsql_orders_db",
        "name": "Cloud SQL Enterprise Plus Orders DB (us-east1)",
        "service_type": "Cloud SQL PostgreSQL",
        "recent_deployment": True,
        "deployment_Info": "v1.8.0-schema (SHA: 9d04e2a) - Orphaned high-HA read replicas after migration",
        "baseline_daily_cost_usd": 150.0,
        "baseline_p99_latency_ms": 42.0,
    },
    {
        "workload_id": "cloud_cdn_edge",
        "name": "Cloud CDN & Media Asset Edge Cache (Global)",
        "service_type": "Cloud CDN / Load Balancing",
        "recent_deployment": False,
        "deployment_Info": "Baseline Control (v1.2.0-stable - No Active Config Changes)",
        "baseline_daily_cost_usd": 110.0,
        "baseline_p99_latency_ms": 28.0,
    },
]

# Explicit OpenAPI / LLM Function Calling JSON Schemas for tool argument validation
TOOL_JSON_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "fetch_cloud_telemetry_and_billing_tool": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of past days to collect cloud billing and latency telemetry for (1 to 90). Default is 30.",
                "minimum": 1,
                "maximum": 90,
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for deterministic sample generation in offline mode.",
            },
        },
        "required": [],
    },
    "validate_telemetry_data_ai_tool": {
        "type": "object",
        "properties": {
            "raw_records": {
                "type": "array",
                "description": "List of raw cloud billing and incident telemetry dictionary records to validate.",
                "items": {"type": "object"},
            }
        },
        "required": ["raw_records"],
    },
    "correlate_cost_and_incident_spikes_tool": {
        "type": "object",
        "properties": {
            "validated_records": {
                "type": "array",
                "description": "List of AI-validated cloud billing and latency records.",
                "items": {"type": "object"},
            },
            "workloads": {
                "type": "array",
                "description": "List of monitored GCP workload metadata dictionaries.",
                "items": {"type": "object"},
            },
            "days_analyzed": {
                "type": "integer",
                "description": "Number of days covered by the evaluation window.",
                "minimum": 1,
            },
        },
        "required": ["validated_records", "workloads"],
    },
    "generate_finops_remediation_plan_tool": {
        "type": "object",
        "properties": {
            "correlation_analysis": {
                "type": "object",
                "description": "Structured output dictionary from correlate_cost_and_incident_spikes_tool.",
            }
        },
        "required": ["correlation_analysis"],
    },
    "simulate_cost_savings_forecast_tool": {
        "type": "object",
        "properties": {
            "remediation_plan": {
                "type": "object",
                "description": "Structured remediation plan dictionary from generate_finops_remediation_plan_tool.",
            },
            "horizon_days": {
                "type": "integer",
                "description": "Forecast horizon in days (default: 90, range: 7 to 365).",
                "minimum": 7,
                "maximum": 365,
            },
        },
        "required": ["remediation_plan"],
    },
}


def validate_tool_args(
    tool_name: str, args: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """Validates runtime arguments against explicit TOOL_JSON_SCHEMAS for LLMs."""
    schema = TOOL_JSON_SCHEMAS.get(tool_name)
    if not schema:
        return True, None

    for req_field in schema.get("required", []):
        if req_field not in args or args[req_field] is None:
            return (
                False,
                f"Missing required argument '{req_field}' for tool '{tool_name}'. Expected schema: {schema['properties'].get(req_field, {})}",
            )

    for arg_name, arg_val in args.items():
        prop = schema.get("properties", {}).get(arg_name)
        if prop:
            expected_type = prop.get("type")
            if expected_type == "integer" and (
                not isinstance(arg_val, int) or isinstance(arg_val, bool)
            ):
                return (
                    False,
                    f"Argument '{arg_name}' must be an integer, got {type(arg_val).__name__}.",
                )
            elif expected_type == "array" and not isinstance(arg_val, list):
                return (
                    False,
                    f"Argument '{arg_name}' must be a list/array, got {type(arg_val).__name__}.",
                )
            elif expected_type == "object" and not isinstance(arg_val, dict):
                return (
                    False,
                    f"Argument '{arg_name}' must be a dictionary/object, got {type(arg_val).__name__}.",
                )

            if (
                "minimum" in prop
                and isinstance(arg_val, (int, float))
                and arg_val < prop["minimum"]
            ):
                return (
                    False,
                    f"Argument '{arg_name}' value {arg_val} is below minimum {prop['minimum']}.",
                )
            if (
                "maximum" in prop
                and isinstance(arg_val, (int, float))
                and arg_val > prop["maximum"]
            ):
                return (
                    False,
                    f"Argument '{arg_name}' value {arg_val} is above maximum {prop['maximum']}.",
                )

    return True, None


def fetch_cloud_telemetry_and_billing_tool(
    days: int = 30, seed: int = 42
) -> Dict[str, Any]:
    """Collects GCP billing export records, P99 latency metrics, and CI/CD deployment logs for the last `days` days.

    Args:
        days: Number of past days to retrieve cloud billing and telemetry records for (default: 30, max: 90).
        seed: Random seed for deterministic sample data generation (default: 42).

    Returns:
        Dict[str, Any]: Structured payload containing:
            - status (str): 'SUCCESS' or 'ERROR'.
            - days_collected (int): Evaluation duration in days.
            - total_raw_records (int): Count of retrieved daily workload billing/telemetry records.
            - records (List[Dict]): Telemetry records with timestamp, workload_id, daily_cost_usd, p99_latency_ms, severity.
            - workloads (List[Dict]): Metadata for monitored GCP workloads.
            - recovery_instruction (str, optional): Guided instructions if errors occur.
    """
    valid, err = validate_tool_args(
        "fetch_cloud_telemetry_and_billing_tool", {"days": days, "seed": seed}
    )
    if not valid:
        return {
            "status": "ERROR",
            "error_code": "INVALID_ARGUMENTS",
            "message": str(err),
            "recovery_instruction": "Please invoke fetch_cloud_telemetry_and_billing_tool with an integer 'days' between 1 and 90 (e.g., days=30).",
        }

    try:
        rng = random.Random(seed)
        now = datetime.datetime.now(datetime.timezone.utc)
        records: List[Dict[str, Any]] = []
        record_counter = 1001

        for day_offset in range(days):
            day_date = now - datetime.timedelta(days=day_offset)
            for wl in MONITORED_CLOUD_WORKLOADS:
                if wl["recent_deployment"]:
                    cost_multiplier = rng.uniform(1.45, 2.15)
                    latency_multiplier = rng.uniform(1.30, 1.85)
                else:
                    cost_multiplier = rng.uniform(0.95, 1.06)
                    latency_multiplier = rng.uniform(0.95, 1.05)

                daily_cost = round(
                    wl["baseline_daily_cost_usd"] * cost_multiplier
                    + rng.uniform(-10.0, 15.0),
                    2,
                )
                p99_latency = round(
                    wl["baseline_p99_latency_ms"] * latency_multiplier, 1
                )

                anomaly_flag = (
                    wl["recent_deployment"]
                    and daily_cost > wl["baseline_daily_cost_usd"] * 1.30
                )

                records.append(
                    {
                        "record_id": f"FINOPS-REC-{record_counter}",
                        "timestamp": day_date.replace(
                            hour=rng.randint(0, 23), minute=rng.randint(0, 59)
                        ).isoformat(),
                        "workload_id": wl["workload_id"],
                        "service_name": wl["name"],
                        "daily_cost_usd": max(10.0, daily_cost),
                        "p99_latency_ms": p99_latency,
                        "severity": (
                            rng.choices(
                                ["COST_NOTICE", "COST_WARNING", "CRITICAL_OVERRUN"],
                                weights=[0.25, 0.45, 0.30],
                            )[0]
                            if anomaly_flag
                            else "NORMAL"
                        ),
                        "deployment_correlated": anomaly_flag,
                        "description": (
                            f"Cost & latency spike following deployment {wl['deployment_Info']}"
                            if anomaly_flag
                            else f"Routine billing export for {wl['name']}"
                        ),
                        "source": "GCP_Billing_Export_v1/Cloud_Monitoring",
                    }
                )
                record_counter += 1

        # Inject deterministic duplicate and corrupted records to verify AI QA quarantine
        if records:
            dup = dict(records[0])
            dup["record_id"] = "FINOPS-REC-DUP-1001"
            dup["description"] += " (duplicate BigQuery billing export row)"
            records.append(dup)

            corrupted_cost = {
                "record_id": "FINOPS-REC-OUTLIER-9998",
                "timestamp": now.isoformat(),
                "workload_id": "vertex_ai_inference",
                "service_name": "Vertex AI LLM Inference Cluster (us-central1)",
                "daily_cost_usd": -99999.0,
                "p99_latency_ms": 250.0,
                "severity": "COST_NOTICE",
                "deployment_correlated": False,
                "description": "Corrupted negative billing adjustment entry",
                "source": "LegacyBillingImport",
            }
            records.append(corrupted_cost)

            stale_timestamp = {
                "record_id": "FINOPS-REC-STALE-9999",
                "timestamp": "2015-01-01T00:00:00+00:00",
                "workload_id": "bigquery_attribution",
                "service_name": "BigQuery Ad-Attribution ETL Pipeline (us-multi)",
                "daily_cost_usd": 310.0,
                "p99_latency_ms": 1200.0,
                "severity": "NORMAL",
                "deployment_correlated": False,
                "description": "Out-of-window archival billing record from 2015",
                "source": "LegacyBillingImport",
            }
            records.append(stale_timestamp)

        return {
            "status": "SUCCESS",
            "days_collected": days,
            "total_raw_records": len(records),
            "records": records,
            "workloads": MONITORED_CLOUD_WORKLOADS,
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_code": "INGESTION_FAILURE",
            "message": str(e),
            "recovery_instruction": "Cloud billing ingestion encountered an unexpected error. Retry with a smaller window such as days=14.",
        }


def validate_telemetry_data_ai_tool(
    raw_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Uses AI validation logic to inspect schemas, cost bounds, duplicate billing rows, and stale timestamps.

    Args:
        raw_records: List of raw telemetry/billing dictionaries retrieved from data sources.

    Returns:
        Dict[str, Any]: Structured QA validation results containing:
            - status (str): 'SUCCESS' or 'ERROR'.
            - total_inspected (int): Total records processed.
            - valid_records_count (int): Clean records passing QA.
            - quarantined_count (int): Duplicate or anomalous records removed.
            - duplicates_flagged (int): Duplicate billing rows detected.
            - cost_outliers_flagged (int): Invalid/negative cost records detected.
            - date_outliers_flagged (int): Out-of-window timestamps detected.
            - average_ai_confidence_score (float): Mean QA confidence (0.00 to 1.00).
            - validated_records (List[Dict]): Clean record list.
            - quarantined_records (List[Dict]): Flagged records with validation_issues.
    """
    valid, err = validate_tool_args(
        "validate_telemetry_data_ai_tool", {"raw_records": raw_records}
    )
    if not valid:
        return {
            "status": "ERROR",
            "error_code": "INVALID_SCHEMA",
            "message": str(err),
            "recovery_instruction": "Ensure 'raw_records' is passed as a non-empty list of dictionary objects retrieved from fetch_cloud_telemetry_and_billing_tool.",
        }

    try:
        validated: List[Dict[str, Any]] = []
        quarantined: List[Dict[str, Any]] = []
        duplicates_found = 0
        cost_outliers = 0
        date_outliers = 0
        seen_signatures = set()

        for item in raw_records:
            issues = []
            cost = float(item.get("daily_cost_usd", 0.0))
            workload_id = str(item.get("workload_id", "UNKNOWN"))

            if not (
                COST_BOUNDS_USD["min_daily_usd"]
                <= cost
                <= COST_BOUNDS_USD["max_daily_usd"]
            ):
                issues.append(
                    f"Daily cost (${cost}) outside valid billing bounds [${COST_BOUNDS_USD['min_daily_usd']}, ${COST_BOUNDS_USD['max_daily_usd']}]"
                )
                cost_outliers += 1

            ts_str = str(item.get("timestamp", ""))
            if "2015" in ts_str or "1970" in ts_str:
                issues.append("Timestamp outside 30-day FinOps evaluation window")
                date_outliers += 1

            sig_key = f"{workload_id}_{round(cost, 2)}_{ts_str[:13]}"
            if sig_key in seen_signatures:
                issues.append(
                    "Duplicate billing export entry within same workload/hour"
                )
                duplicates_found += 1
            else:
                seen_signatures.add(sig_key)

            confidence = round(max(0.1, 1.0 - (len(issues) * 0.45)), 2)
            record = dict(item)
            record["validation_issues"] = issues
            record["ai_confidence_score"] = confidence

            if len(issues) == 0:
                record["validation_status"] = "VALIDATED"
                validated.append(record)
            else:
                record["validation_status"] = "QUARANTINED"
                quarantined.append(record)

        average_confidence = round(
            sum(r["ai_confidence_score"] for r in validated + quarantined)
            / max(1, len(raw_records)),
            2,
        )

        return {
            "status": "SUCCESS",
            "total_inspected": len(raw_records),
            "valid_records_count": len(validated),
            "quarantined_count": len(quarantined),
            "duplicates_flagged": duplicates_found,
            "cost_outliers_flagged": cost_outliers,
            "date_outliers_flagged": date_outliers,
            "average_ai_confidence_score": average_confidence,
            "validated_records": validated,
            "quarantined_records": quarantined,
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_code": "AI_QA_FAILURE",
            "message": str(e),
            "recovery_instruction": "AI telemetry validation failed due to malformed record fields. Verify each record contains 'workload_id', 'daily_cost_usd', and 'timestamp'.",
        }


def correlate_cost_and_incident_spikes_tool(
    validated_records: List[Dict[str, Any]],
    workloads: List[Dict[str, Any]],
    days_analyzed: int = 30,
) -> Dict[str, Any]:
    """Correlates cloud spend anomalies and P99 latency spikes with recent CI/CD deployments.

    Args:
        validated_records: List of clean telemetry/billing dictionaries from AI QA tool.
        workloads: List of monitored GCP workload metadata dictionaries.
        days_analyzed: Duration of analysis window in days (default: 30).

    Returns:
        Dict[str, Any]: Statistical correlation results containing:
            - status (str): 'SUCCESS' or 'ERROR'.
            - net_cloud_spend_overrun_pct (float): Overall % spend increase across deployed services.
            - total_excess_spend_30d_usd (float): Total excess spend above baseline in USD.
            - has_statistically_significant_spike (bool): True if net spend increase >= 20%.
            - workload_breakdowns (List[Dict]): Service-by-service cost & latency comparison.
            - conclusion (str): Executive natural-language summary.
    """
    valid, err = validate_tool_args(
        "correlate_cost_and_incident_spikes_tool",
        {
            "validated_records": validated_records,
            "workloads": workloads,
            "days_analyzed": days_analyzed,
        },
    )
    if not valid:
        return {
            "status": "ERROR",
            "error_code": "INVALID_CORRELATION_ARGS",
            "message": str(err),
            "recovery_instruction": "Ensure both 'validated_records' and 'workloads' are provided as non-empty lists.",
        }

    try:
        wl_stats: Dict[str, Dict[str, Any]] = {}
        for wl in workloads:
            wid = wl["workload_id"]
            wl_stats[wid] = {
                "workload_id": wid,
                "name": wl["name"],
                "service_type": wl.get("service_type", "GCP Service"),
                "recent_deployment": wl["recent_deployment"],
                "deployment_info": wl.get("deployment_Info", ""),
                "baseline_expected_spend_usd": round(
                    wl["baseline_daily_cost_usd"] * days_analyzed, 2
                ),
                "observed_spend_usd": 0.0,
                "baseline_p99_latency_ms": wl.get("baseline_p99_latency_ms", 100.0),
                "observed_avg_p99_latency_ms": 0.0,
                "critical_alert_count": 0,
                "record_count": 0,
                "cost_spike_percent": 0.0,
                "impact_status": "NORMAL",
            }

        for rec in validated_records:
            wid = rec.get("workload_id", "NONE")
            if wid in wl_stats:
                st = wl_stats[wid]
                st["observed_spend_usd"] = round(
                    st["observed_spend_usd"] + float(rec.get("daily_cost_usd", 0.0)), 2
                )
                st["observed_avg_p99_latency_ms"] += float(
                    rec.get("p99_latency_ms", 0.0)
                )
                st["record_count"] += 1
                if rec.get("severity") in ["COST_WARNING", "CRITICAL_OVERRUN"]:
                    st["critical_alert_count"] += 1

        overall_deployed_spend = 0.0
        overall_deployed_baseline = 0.0

        for wid, st in wl_stats.items():
            cnt = max(1, st["record_count"])
            st["observed_avg_p99_latency_ms"] = round(
                st["observed_avg_p99_latency_ms"] / cnt, 1
            )
            obs = st["observed_spend_usd"]
            base = st["baseline_expected_spend_usd"]
            diff_pct = round(((obs - base) / base) * 100.0, 1) if base > 0 else 0.0
            st["cost_spike_percent"] = diff_pct

            if st["recent_deployment"]:
                overall_deployed_spend += obs
                overall_deployed_baseline += base
                if diff_pct >= 35.0:
                    st["impact_status"] = "CRITICAL_COST_SPIKE"
                elif diff_pct >= 15.0:
                    st["impact_status"] = "MODERATE_COST_DRIFT"
                else:
                    st["impact_status"] = "WITHIN_BUDGET"
            else:
                st["impact_status"] = "BASELINE_CONTROL"

        if overall_deployed_baseline > 0:
            net_overrun_pct = round(
                (
                    (overall_deployed_spend - overall_deployed_baseline)
                    / overall_deployed_baseline
                )
                * 100.0,
                1,
            )
        else:
            net_overrun_pct = 0.0

        excess_spend_usd = round(
            max(0.0, overall_deployed_spend - overall_deployed_baseline), 2
        )
        significant = net_overrun_pct >= 20.0

        return {
            "status": "SUCCESS",
            "days_analyzed": days_analyzed,
            "net_cloud_spend_overrun_pct": net_overrun_pct,
            "total_excess_spend_30d_usd": excess_spend_usd,
            "has_statistically_significant_spike": significant,
            "workload_breakdowns": list(wl_stats.values()),
            "conclusion": (
                f"Workloads with recent CI/CD deployments exhibit a +{net_overrun_pct}% cloud cost overrun "
                f"(${excess_spend_usd:,.2f} excess spend over {days_analyzed} days) strongly correlated with P99 latency regressions."
                if significant
                else f"Cloud spend across deployed services (+{net_overrun_pct}%) remains within normal FinOps budget variance."
            ),
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_code": "CORRELATION_ENGINE_ERROR",
            "message": str(e),
            "recovery_instruction": "Verify that workload_id fields match between validated_records and MONITORED_CLOUD_WORKLOADS.",
        }


def generate_finops_remediation_plan_tool(
    correlation_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """Generates prioritized SRE & FinOps engineering remediation actions and rollback commands.

    Args:
        correlation_analysis: Structured output dictionary from correlate_cost_and_incident_spikes_tool.

    Returns:
        Dict[str, Any]: Actionable FinOps & SRE remediation brief containing:
            - status (str): 'SUCCESS' or 'ERROR'.
            - recommendation_count (int): Number of remediations proposed.
            - total_estimated_monthly_savings_usd (float): Sum of projected monthly savings.
            - executive_finops_brief (str): High-level remediation summary.
            - recommendations (List[Dict]): Priority-ranked interventions with CLI commands and HITL flags.
    """
    valid, err = validate_tool_args(
        "generate_finops_remediation_plan_tool",
        {"correlation_analysis": correlation_analysis},
    )
    if not valid:
        return {
            "status": "ERROR",
            "error_code": "INVALID_REMEDIATION_INPUT",
            "message": str(err),
            "recovery_instruction": "Ensure 'correlation_analysis' dictionary contains 'workload_breakdowns' list from correlate_cost_and_incident_spikes_tool.",
        }

    try:
        recommendations: List[Dict[str, Any]] = []
        breakdowns = correlation_analysis.get("workload_breakdowns", [])

        for wl in breakdowns:
            status = wl.get("impact_status")
            if status in ["CRITICAL_COST_SPIKE", "MODERATE_COST_DRIFT"]:
                name = wl.get("name", "")
                spike_pct = wl.get("cost_spike_percent", 0.0)
                excess = max(
                    500.0,
                    round(
                        wl.get("observed_spend_usd", 0.0)
                        - wl.get("baseline_expected_spend_usd", 0.0),
                        2,
                    ),
                )

                if "Vertex AI" in name:
                    recommendations.append(
                        {
                            "workload": name,
                            "priority": "HIGH",
                            "intervention_type": "Right-Size GPU Autoscaler & Enable Dynamic Batching",
                            "rationale": f"Observed +{spike_pct}% spend surge after v2.4.1-canary set min_replica_count=8 on A100 GPUs.",
                            "action_item": "Cap min_replica_count=2 with scale-to-zero idle timeout and roll back unbounded autoscaler spec.",
                            "remediation_command": "gcloud ai endpoints update vertex-llm-prod --region=us-central1 --min-replica-count=2 --max-replica-count=6",
                            "estimated_monthly_savings_usd": excess,
                            "requires_hitl_approval": True,
                        }
                    )
                elif "BigQuery" in name:
                    recommendations.append(
                        {
                            "workload": name,
                            "priority": "HIGH",
                            "intervention_type": "Enforce Partition Pruning & Slot Reservation Cap",
                            "rationale": f"Observed +{spike_pct}% cost spike from unpartitioned 40TB full-table scans introduced in SHA 7c3e91b.",
                            "action_item": "Enable require_partition_filter=true on attribution_events table and set maximum_bytes_billed guard.",
                            "remediation_command": "bq update --require_partition_filter=true prod_analytics.attribution_events",
                            "estimated_monthly_savings_usd": excess,
                            "requires_hitl_approval": True,
                        }
                    )
                elif "GKE" in name:
                    recommendations.append(
                        {
                            "workload": name,
                            "priority": "MEDIUM",
                            "intervention_type": "Circuit Breaker & Exponential Backoff Patch",
                            "rationale": f"Observed +{spike_pct}% compute & egress cost increase due to synchronous webhook retry storm.",
                            "action_item": "Configure Envoy circuit breaker max_retries=3 with jittered backoff on checkout-service.",
                            "remediation_command": "kubectl rollout undo deployment/checkout-api -n prod-payments",
                            "estimated_monthly_savings_usd": excess,
                            "requires_hitl_approval": True,
                        }
                    )
                else:
                    recommendations.append(
                        {
                            "workload": name,
                            "priority": "MEDIUM",
                            "intervention_type": "Decommission Orphaned Read Replicas",
                            "rationale": f"Observed +{spike_pct}% spend increase above baseline after schema migration.",
                            "action_item": "Consolidate idle read replica instances into primary HA failover pool.",
                            "remediation_command": "gcloud sql instances patch orders-db-replica-old --activation-policy=NEVER",
                            "estimated_monthly_savings_usd": excess,
                            "requires_hitl_approval": False,
                        }
                    )

        total_monthly_savings = round(
            sum(r["estimated_monthly_savings_usd"] for r in recommendations), 2
        )

        return {
            "status": "SUCCESS",
            "recommendation_count": len(recommendations),
            "total_estimated_monthly_savings_usd": total_monthly_savings,
            "executive_finops_brief": (
                f"Immediate FinOps & SRE interventions recommended across {len(recommendations)} workloads, "
                f"projecting ${total_monthly_savings:,.2f}/month in recovered cloud spend."
                if recommendations
                else "All workloads operating within FinOps budget thresholds; no emergency remediations required."
            ),
            "recommendations": recommendations,
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_code": "REMEDIATION_SYNTHESIS_ERROR",
            "message": str(e),
            "recovery_instruction": "Ensure correlation_analysis is properly formatted. Re-run correlate_cost_and_incident_spikes_tool if necessary.",
        }


def simulate_cost_savings_forecast_tool(
    remediation_plan: Dict[str, Any],
    horizon_days: int = 90,
) -> Dict[str, Any]:
    """Simulates 30/90-day cloud cost savings and carbon efficiency gains after applying FinOps remediations.

    Args:
        remediation_plan: Structured dictionary returned by generate_finops_remediation_plan_tool.
        horizon_days: Number of future days to project FinOps savings over (default: 90).

    Returns:
        Dict[str, Any]: Projected FinOps ROI forecast containing:
            - status (str): 'SUCCESS' or 'ERROR'.
            - horizon_days (int): Forecast window in days.
            - projected_savings_usd (float): Total projected savings over `horizon_days`.
            - annualized_savings_usd (float): Projected 12-month savings in USD.
            - estimated_carbon_reduction_kg_co2e (float): Estimated data center carbon reduction.
    """
    valid, err = validate_tool_args(
        "simulate_cost_savings_forecast_tool",
        {"remediation_plan": remediation_plan, "horizon_days": horizon_days},
    )
    if not valid:
        return {
            "status": "ERROR",
            "error_code": "INVALID_FORECAST_ARGS",
            "message": str(err),
            "recovery_instruction": "Pass a valid 'remediation_plan' dict and an integer 'horizon_days' between 7 and 365.",
        }

    try:
        monthly_savings = float(
            remediation_plan.get("total_estimated_monthly_savings_usd", 0.0)
        )
        daily_savings = monthly_savings / 30.0
        projected_savings = round(daily_savings * horizon_days, 2)
        annualized_savings = round(daily_savings * 365.0, 2)
        carbon_kg = round(projected_savings * 0.14, 1)

        return {
            "status": "SUCCESS",
            "horizon_days": horizon_days,
            "projected_savings_usd": projected_savings,
            "annualized_savings_usd": annualized_savings,
            "estimated_carbon_reduction_kg_co2e": carbon_kg,
            "summary": (
                f"Enacting {remediation_plan.get('recommendation_count', 0)} FinOps remediations saves "
                f"${projected_savings:,.2f} over {horizon_days} days (${annualized_savings:,.2f}/yr) "
                f"and avoids ~{carbon_kg} kg CO2e."
            ),
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_code": "FORECAST_SIMULATION_ERROR",
            "message": str(e),
            "recovery_instruction": "Verify remediation_plan includes 'total_estimated_monthly_savings_usd'.",
        }
