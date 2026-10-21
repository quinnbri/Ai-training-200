"""Interactive Terminal CLI for Cloud FinOps & Incident Remediation Copilot."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.agent import CloudFinOpsSupervisorAgent


def main() -> None:
    agent = CloudFinOpsSupervisorAgent()
    print("=" * 72)
    print("  Cloud FinOps & Incident Remediation AI Copilot - Interactive CLI")
    print("=" * 72)
    print("Running initial 30-day GCP billing & deployment correlation analysis...")
    analysis = agent.run_full_analysis(days=30)
    corr = analysis["cost_incident_correlation"]
    forecast = analysis["savings_forecast"]
    print(f"Status:            {analysis['status']}")
    print(f"Net Spend Overrun: +{corr['net_cloud_spend_overrun_pct']}%")
    print(f"90-Day Savings:    ${forecast['projected_savings_usd']:,.2f}")
    print(f"Pending HITL:      {len(analysis['hitl_review_ids_generated'])} items")
    print("-" * 72)
    print("Type a question (e.g., 'What happened to Vertex AI GPU costs?'), or 'exit' to quit.\n")

    session_id = "cli_session"
    while True:
        try:
            user_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting CLI.")
            break
        if not user_input:
            continue
        if user_input.lower() in ["exit", "quit", "q"]:
            print("Goodbye!")
            break
        resp = agent.ask_agent(session_id=session_id, question=user_input)
        print(f"\nCopilot [{resp.get('model_route', 'guardrail')}] > {resp['answer']}\n")


if __name__ == "__main__":
    main()
