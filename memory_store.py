"""Context and Memory Store for the Cloud FinOps & Incident Remediation Copilot.

Stores multi-turn conversation context, rolling session summaries, cached 30-day
cloud billing & incident telemetry, and historical FinOps remediation runs using
SQLite (with in-memory or file-backed persistence).
Features automatic history compaction (summarization/token truncation) and
asynchronous background thread-pool processing for non-blocking disk I/O.
"""

import concurrent.futures
import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

from observability.pii_scrubber import global_pii_scrubber
from .system_prompt import AGENT_SYSTEM_PROMPT


class AgentMemoryStore:
    """Manages persistent context, telemetry cache, and FinOps analysis history with compaction & async I/O."""

    def __init__(self, db_path: str = ":memory:", max_async_workers: int = 2) -> None:
        self.db_path = db_path
        self._memory_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_async_workers, thread_name_prefix="FinOpsMemoryWorker"
        )
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp REAL,
                    tokens_estimated INTEGER
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS session_summaries (
                    session_id TEXT PRIMARY KEY,
                    summary TEXT,
                    updated_at REAL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT,
                    created_at REAL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    run_id TEXT PRIMARY KEY,
                    title TEXT,
                    summary TEXT,
                    details TEXT,
                    created_at REAL
                )
                """
            )
            conn.commit()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Approximates LLM token count (roughly 4 characters per token in English)."""
        if not text:
            return 0
        return max(1, len(str(text)) // 4)

    def save_message(self, session_id: str, role: str, content: str) -> None:
        """Synchronously saves a chat message with PII scrubbing and token estimation."""
        scrubbed_content = global_pii_scrubber.scrub_text(content)
        tokens = self.estimate_tokens(scrubbed_content)
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO conversation_history (session_id, role, content, timestamp, tokens_estimated) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, scrubbed_content, time.time(), tokens),
            )
        # Trigger compaction check in background if needed
        self.async_compact_session_history(session_id)

    def async_save_message(
        self, session_id: str, role: str, content: str
    ) -> concurrent.futures.Future:
        """Asynchronously saves a chat message in a background worker thread."""
        return self._executor.submit(self.save_message, session_id, role, content)

    def get_conversation_history(
        self, session_id: str, limit: int = 20, include_system_prompt: bool = True
    ) -> List[Dict[str, Any]]:
        """Retrieves session conversation history with optional summary prefix and system prompt."""
        history: List[Dict[str, Any]] = []
        if include_system_prompt:
            history.append(
                {"role": "system", "content": AGENT_SYSTEM_PROMPT, "timestamp": 0.0}
            )

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT summary, updated_at FROM session_summaries WHERE session_id = ?",
                (session_id,),
            )
            summary_row = cursor.fetchone()
            if summary_row and summary_row["summary"]:
                history.append(
                    {
                        "role": "system",
                        "content": f"[Previous Session Summary]: {summary_row['summary']}",
                        "timestamp": summary_row["updated_at"],
                    }
                )

            cursor = conn.execute(
                "SELECT role, content, timestamp FROM conversation_history WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                (session_id, limit),
            )
            for row in cursor.fetchall():
                history.append(dict(row))
        return history

    def compact_session_history(
        self, session_id: str, max_tokens: int = 1200, preserve_recent: int = 6
    ) -> bool:
        """Compacts older messages into a rolling summary when session token count exceeds threshold."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, role, content, tokens_estimated FROM conversation_history WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            )
            rows = [dict(row) for row in cursor.fetchall()]

        if len(rows) <= preserve_recent:
            return False

        total_tokens = sum(r.get("tokens_estimated", 0) for r in rows)
        if total_tokens <= max_tokens:
            return False

        older_turns = rows[:-preserve_recent]
        older_ids = [r["id"] for r in older_turns]

        summary_lines = []
        for t in older_turns:
            role_label = "User" if t["role"] == "user" else "Agent"
            content_snippet = t["content"][:100] + (
                "..." if len(t["content"]) > 100 else ""
            )
            summary_lines.append(f"- {role_label} discussed: {content_snippet}")

        new_summary_text = " ".join(summary_lines)

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT summary FROM session_summaries WHERE session_id = ?",
                (session_id,),
            )
            ex_row = cursor.fetchone()
            if ex_row and ex_row["summary"]:
                combined_summary = ex_row["summary"] + " " + new_summary_text
            else:
                combined_summary = new_summary_text

            conn.execute(
                "INSERT OR REPLACE INTO session_summaries (session_id, summary, updated_at) VALUES (?, ?, ?)",
                (session_id, combined_summary, time.time()),
            )
            placeholders = ",".join("?" * len(older_ids))
            conn.execute(
                f"DELETE FROM conversation_history WHERE id IN ({placeholders})",
                older_ids,
            )
            conn.commit()
        return True

    def async_compact_session_history(
        self, session_id: str
    ) -> concurrent.futures.Future:
        """Asynchronously triggers conversation history compaction."""
        return self._executor.submit(self.compact_session_history, session_id)

    def cache_telemetry(
        self, cache_key: str, records: List[Dict[str, Any]]
    ) -> None:
        """Synchronously caches validated telemetry records with PII scrubbing."""
        scrubbed = global_pii_scrubber.scrub_data(records)
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO telemetry_cache (cache_key, payload, created_at) VALUES (?, ?, ?)",
                (cache_key, json.dumps(scrubbed), time.time()),
            )

    def async_cache_telemetry(
        self, cache_key: str, records: List[Dict[str, Any]]
    ) -> concurrent.futures.Future:
        """Asynchronously caches telemetry records in background worker thread."""
        return self._executor.submit(self.cache_telemetry, cache_key, records)

    def get_cached_telemetry(
        self, cache_key: str, max_age_seconds: int = 3600
    ) -> Optional[List[Dict[str, Any]]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT payload, created_at FROM telemetry_cache WHERE cache_key = ?",
                (cache_key,),
            )
            row = cursor.fetchone()
            if not row or (time.time() - row["created_at"]) > max_age_seconds:
                return None
            return json.loads(row["payload"])

    def save_analysis_run(
        self, title: str, summary: str, details: Dict[str, Any]
    ) -> str:
        """Synchronously saves a FinOps analysis run report with PII redaction."""
        run_id = uuid.uuid4().hex[:12]
        scrubbed_details = global_pii_scrubber.scrub_data(details)
        scrubbed_summary = global_pii_scrubber.scrub_text(summary)
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO analysis_runs (run_id, title, summary, details, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    title,
                    scrubbed_summary,
                    json.dumps(scrubbed_details),
                    time.time(),
                ),
            )
        return run_id

    def async_save_analysis_run(
        self, title: str, summary: str, details: Dict[str, Any]
    ) -> concurrent.futures.Future:
        """Asynchronously saves analysis report in background thread."""
        return self._executor.submit(self.save_analysis_run, title, summary, details)

    def get_recent_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT run_id, title, summary, details, created_at FROM analysis_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = []
            for row in cursor.fetchall():
                data = dict(row)
                data["details"] = json.loads(data["details"])
                rows.append(data)
            return rows

    def shutdown(self, wait: bool = True) -> None:
        """Shuts down background thread executor."""
        self._executor.shutdown(wait=wait)


# Global default in-memory store
global_memory = AgentMemoryStore()
