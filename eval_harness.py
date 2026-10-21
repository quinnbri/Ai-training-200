"""Static AI Evaluation Harness for Cloud FinOps & Incident Remediation Copilot.

Executes automated benchmarking against a golden dataset of cloud cost anomaly
and deployment incident scenarios (eval/golden_dataset.json), computing QA precision,
root-cause correlation accuracy, and FinOps remediation alignment scores.
"""

import json
import os
import sys
from typing import Any, Dict, Optional

# Ensure project root is on sys.path when running standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.finops_tools import (
    MONITORED_CLOUD_WORKLOADS,
    correlate_cost_and_incident_spikes_tool,
    generate_finops_remediation_plan_tool,
    validate_telemetry_data_ai_tool,
)


class AIEvaluationHarness:
    """Evaluates agent tool outputs against ground-truth FinOps golden datasets."""

    def __init__(self, dataset_path: Optional[str] = None) -> None:
        if dataset_path is None:
            self.dataset_path = os.path.join(
                os.path.dirname(__file__), "golden_dataset.json"
            )
        else:
            self.dataset_path = dataset_path

    def load_golden_dataset(self) -> Dict[str, Any]:
        if not os.path.exists(self.dataset_path):
            raise FileNotFoundError(
                f"Golden dataset not found at {self.dataset_path}"
            )
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def run_benchmark(
        self, output_report_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes all golden test scenarios and calculates overall benchmark scorecard."""
        dataset = self.load_golden_dataset()
        scenarios = dataset.get("test_scenarios", [])

        total_scenarios = len(scenarios)
        passed_scenarios = 0
        scenario_results = []

        total_qa_precision = 0.0
        total_correlation_accuracy = 0.0
        total_remediation_alignment = 0.0

        for sc in scenarios:
            sid = sc.get("scenario_id", "UNKNOWN")
            raw_records = sc.get("raw_records", [])
            target_wid = sc.get("target_workload_id", "")
            gt = sc.get("ground_truth", {})

            # 1. Run AI Quality Assurance Tool
            qa_res = validate_telemetry_data_ai_tool(raw_records)
            valid_match = (
                qa_res["valid_records_count"] == gt["expected_valid_count"]
            )
            quar_match = (
                qa_res["quarantined_count"] == gt["expected_quarantined_count"]
            )
            dup_match = (
                qa_res["duplicates_flagged"] == gt["expected_duplicates_flagged"]
            )
            out_match = (
                qa_res["cost_outliers_flagged"] == gt["expected_cost_outliers"]
            )

            qa_score = (
                sum([valid_match, quar_match, dup_match, out_match]) / 4.0
            ) * 100.0
            total_qa_precision += qa_score

            # 2. Run Deployment-to-Cost Correlation Tool
            corr_res = correlate_cost_and_incident_spikes_tool(
                qa_res["validated_records"],
                MONITORED_CLOUD_WORKLOADS,
                days_analyzed=sc.get("days", 1),
            )

            impact_status_match = False
            for wl in corr_res.get("workload_breakdowns", []):
                if (
                    wl["workload_id"] == target_wid
                    and wl["impact_status"] == gt["expected_workload_impact"]
                ):
                    impact_status_match = True
                    break

            corr_score = 100.0 if impact_status_match else 0.0
            total_correlation_accuracy += corr_score

            # 3. Run FinOps Remediation Plan Tool
            rem_res = generate_finops_remediation_plan_tool(corr_res)
            recs_text = " ".join(
                [
                    r.get("intervention_type", "")
                    for r in rem_res.get("recommendations", [])
                ]
            )

            exp_rec = gt["expected_priority_recommendation"]
            if exp_rec == "None":
                rem_match = len(rem_res.get("recommendations", [])) == 0
            else:
                rem_match = exp_rec.lower() in recs_text.lower()

            rem_score = 100.0 if rem_match else 0.0
            total_remediation_alignment += rem_score

            scenario_pass = (
                (qa_score >= 75.0) and impact_status_match and rem_match
            )
            if scenario_pass:
                passed_scenarios += 1

            scenario_results.append(
                {
                    "scenario_id": sid,
                    "name": sc.get("name"),
                    "passed": scenario_pass,
                    "qa_precision_pct": round(qa_score, 1),
                    "correlation_accuracy_pct": round(corr_score, 1),
                    "remediation_alignment_pct": round(rem_score, 1),
                    "details": {
                        "qa_output": qa_res,
                        "correlation_output": corr_res,
                        "remediation_output": rem_res,
                    },
                }
            )

        mean_qa = round(total_qa_precision / max(1, total_scenarios), 1)
        mean_corr = round(total_correlation_accuracy / max(1, total_scenarios), 1)
        mean_rem = round(total_remediation_alignment / max(1, total_scenarios), 1)
        overall_benchmark = round((mean_qa + mean_corr + mean_rem) / 3.0, 1)

        report = {
            "benchmark_status": (
                "PASSED" if overall_benchmark >= 85.0 else "NEEDS_IMPROVEMENT"
            ),
            "overall_score_pct": overall_benchmark,
            "scenarios_passed": f"{passed_scenarios}/{total_scenarios}",
            "metrics": {
                "mean_qa_precision_pct": mean_qa,
                "mean_correlation_accuracy_pct": mean_corr,
                "mean_remediation_alignment_pct": mean_rem,
            },
            "scenario_results": scenario_results,
        }

        if output_report_path:
            with open(output_report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)

        return report


def main() -> None:
    harness = AIEvaluationHarness()
    print(
        "=== Running Static AI Evaluation Harness for Cloud FinOps Copilot ==="
    )
    report = harness.run_benchmark()
    print(f"Benchmark Status:  {report['benchmark_status']}")
    print(f"Overall Score:     {report['overall_score_pct']}%")
    print(f"Scenarios Passed:  {report['scenarios_passed']}")
    print(
        "====================================================================="
    )
    if report["overall_score_pct"] < 85.0:
        sys.exit(1)


if __name__ == "__main__":
    main()
