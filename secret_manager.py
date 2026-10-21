"""Secure Credential Injection module for Cloud FinOps & Incident Remediation Copilot.

Integrates Google Cloud Secret Manager to retrieve sensitive API keys and tokens
at runtime, falling back to local environment variables during offline testing.
"""

import os
from typing import Optional

from observability.tracer import get_logger

logger = get_logger("SecretManagerClient")


class SecretManagerClient:
    """Retrieves secrets from GCP Secret Manager or local environment fallbacks."""

    def __init__(self, project_id: Optional[str] = None) -> None:
        self.project_id = (
            project_id
            or os.environ.get("GCP_PROJECT_ID")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )
        self._client = None
        if self.project_id:
            try:
                from google.cloud import secretmanager  # type: ignore

                self._client = secretmanager.SecretManagerServiceClient()
            except Exception:
                logger.warning(
                    "SecretManagerServiceClient unavailable. Using environment variable fallback."
                )

    def get_secret(self, secret_id: str, env_fallback_key: str) -> Optional[str]:
        """Retrieves secret payload by ID from Secret Manager or environment variable."""
        # 1. Check if directly injected as container environment variable
        injected_val = os.environ.get(f"{secret_id.upper().replace('-', '_')}_SECRET")
        if injected_val:
            return injected_val

        # 2. Check GCP Secret Manager if client and project are active
        if self._client and self.project_id:
            try:
                name = f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"
                response = self._client.access_secret_version(request={"name": name})
                payload = response.payload.data.decode("utf-8")
                logger.info(
                    f"Successfully injected runtime secret '{secret_id}' from GCP Secret Manager."
                )
                return payload
            except Exception as e:
                logger.warning(
                    f"Could not fetch secret '{secret_id}' from Secret Manager: {e}"
                )

        # 3. Fallback to standard environment variable
        fallback_val = os.environ.get(env_fallback_key)
        if fallback_val:
            logger.info(
                f"Loaded secret '{secret_id}' from local environment fallback '{env_fallback_key}'."
            )
            return fallback_val

        return None


# Global shared secret manager client
global_secret_manager = SecretManagerClient()
