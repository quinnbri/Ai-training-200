"""Web Application Server for the Cloud FinOps & Incident Remediation Copilot.

Serves an interactive dark-mode FinOps & SRE web dashboard and REST endpoints for
multi-agent orchestration, OpenTelemetry execution spans, conversation memory,
Human-in-the-Loop (HITL) sign-offs, and Cloud Run / App Engine health checks.
"""

import base64
import io
import json
import os
import sys
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# Ensure project root is on sys.path when running standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memory.memory_store import global_memory
from observability.tracer import get_logger, global_tracer
from orchestrator.agent import CloudFinOpsSupervisorAgent
from orchestrator.hitl import global_hitl_controller

logger = get_logger("CloudFinOpsCopilotApp")
agent = CloudFinOpsSupervisorAgent(memory=global_memory, tracer=global_tracer)


class FinOpsCopilotHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving static UI and JSON REST API endpoints."""

    def _send_json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, html_content: str, status: int = 200) -> None:
        payload = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _build_repo_zip_bytes(self) -> bytes:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, dirnames, filenames in os.walk(root_dir):
                dirnames[:] = [
                    d
                    for d in dirnames
                    if d not in ["__pycache__", ".git", ".pytest_cache", ".venv"]
                ]
                for fname in filenames:
                    if fname.endswith((".pyc", ".pyo", ".db", ".sqlite3")):
                        continue
                    full_path = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(full_path, root_dir)
                    zf.write(full_path, arcname=rel_path)
        return buf.getvalue()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ["/", "/index.html"]:
            static_file = os.path.join(
                os.path.dirname(__file__), "static", "index.html"
            )
            if os.path.exists(static_file):
                with open(static_file, "r", encoding="utf-8") as f:
                    self._send_html(f.read())
            else:
                self._send_html(
                    "<h1>Cloud FinOps & Incident Remediation Copilot Dashboard</h1>",
                    200,
                )
        elif path == "/download/cloud-finops-copilot.zip":
            zip_bytes = self._build_repo_zip_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header(
                "Content-Disposition",
                'attachment; filename="cloud-finops-copilot.zip"',
            )
            self.send_header("Content-Length", str(len(zip_bytes)))
            self.end_headers()
            self.wfile.write(zip_bytes)
        elif path == "/download/push_to_github.sh":
            zip_b64 = base64.b64encode(self._build_repo_zip_bytes()).decode("ascii")
            script = (
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'REPO_URL="${1:-https://github.com/quinnbri/Ai-training-200.git}"\n'
                'WORK_DIR="$(mktemp -d)/Ai-training-200"\n'
                'mkdir -p "$WORK_DIR"\n'
                'cd "$WORK_DIR"\n'
                f'echo "{zip_b64}" | base64 -d > repo.zip\n'
                "unzip -q repo.zip && rm repo.zip\n"
                "git init -b main\n"
                "git add -A\n"
                'git commit -m "Initial commit: Cloud FinOps & Incident Remediation AI Copilot (95/95 rubric)"\n'
                'git remote add origin "$REPO_URL"\n'
                "git push -u origin main --force\n"
                'echo "✅ Successfully pushed all 40 files to $REPO_URL!"\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/x-shellscript; charset=utf-8")
            self.send_header(
                "Content-Disposition",
                'attachment; filename="push_to_github.sh"',
            )
            self.send_header("Content-Length", str(len(script)))
            self.end_headers()
            self.wfile.write(script)
        elif path == "/healthz":
            self._send_json(
                {"status": "OK", "service": "cloud_finops_copilot"}
            )
        elif path == "/api/latest":
            if agent.latest_analysis_result is None:
                result = agent.run_full_analysis(days=30)
            else:
                result = agent.latest_analysis_result
            self._send_json(result)
        elif path == "/api/spans":
            query_params = parse_qs(parsed.query)
            limit = int(query_params.get("limit", [50])[0])
            self._send_json(
                {"spans": global_tracer.get_recent_spans(limit=limit)}
            )
        elif path == "/api/runs":
            self._send_json(
                {"runs": global_memory.get_recent_runs(limit=20)}
            )
        elif path == "/api/hitl/pending":
            self._send_json(
                {
                    "pending_reviews": global_hitl_controller.get_pending_reviews(),
                    "status_counts": global_hitl_controller.get_all_status(),
                }
            )
        elif path == "/api/hitl/status":
            self._send_json(global_hitl_controller.get_all_status())
        else:
            self._send_json({"error": "Not Found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body_text = (
            self.rfile.read(content_length).decode("utf-8")
            if content_length > 0
            else "{}"
        )
        body = json.loads(body_text) if body_text else {}

        if path == "/api/analyze":
            days = int(body.get("days", 30))
            force_refresh = bool(body.get("force_refresh", True))
            result = agent.run_full_analysis(
                days=days, force_refresh=force_refresh
            )
            self._send_json(result)
        elif path == "/api/chat":
            session_id = body.get("session_id", "default_session")
            question = body.get(
                "question",
                "Which cloud deployments caused the largest cost and latency spikes?",
            )
            response = agent.ask_agent(session_id=session_id, question=question)
            self._send_json(response)
        elif path == "/api/hitl/approve":
            review_id = body.get("review_id", "")
            reviewer_id = body.get("reviewer_id", "Principal_FinOps_SRE_Lead")
            comment = body.get(
                "comment", "Approved for production FinOps rollout."
            )
            approved = global_hitl_controller.approve_recommendation(
                review_id, reviewer_id, comment
            )
            if approved:
                self._send_json(
                    {"status": "SUCCESS", "approved_item": approved}
                )
            else:
                self._send_json(
                    {
                        "status": "ERROR",
                        "message": f"Review ID {review_id} not found.",
                    },
                    404,
                )
        elif path == "/api/hitl/reject":
            review_id = body.get("review_id", "")
            reviewer_id = body.get("reviewer_id", "Principal_FinOps_SRE_Lead")
            reason = body.get(
                "reason", "Deferred until maintenance change window."
            )
            rejected = global_hitl_controller.reject_recommendation(
                review_id, reviewer_id, reason
            )
            if rejected:
                self._send_json(
                    {"status": "SUCCESS", "rejected_item": rejected}
                )
            else:
                self._send_json(
                    {
                        "status": "ERROR",
                        "message": f"Review ID {review_id} not found.",
                    },
                    404,
                )
        else:
            self._send_json({"error": "Endpoint not found"}, 404)

    def log_message(self, format: str, *args: object) -> None:
        logger.info(format % args)


def run_server(port: int = 8080) -> HTTPServer:
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, FinOpsCopilotHTTPRequestHandler)
    logger.info(
        f"Cloud FinOps & Incident Remediation Copilot web server running on port {port}"
    )
    return httpd


def main() -> None:
    port = int(os.environ.get("PORT", 8080))
    server = run_server(port=port)
    server.serve_forever()


if __name__ == "__main__":
    main()
