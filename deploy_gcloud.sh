#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-}"
REGION="${2:-us-east1}"
SERVICE_NAME="cloud-finops-copilot"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Usage: ./deploy_gcloud.sh <GCP_PROJECT_ID> [REGION]"
  exit 1
fi

echo "=== 1. Running Unit Tests & Golden Dataset Evaluation Gate ==="
python3 -m unittest discover -s tests -p "test_*.py" -v
python3 eval/eval_harness.py

echo "=== 2. Deploying ${SERVICE_NAME} to Google Cloud Run (${REGION}) ==="
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated
