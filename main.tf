# Enable required GCP APIs
resource "google_project_service" "enabled_apis" {
  for_each = toset([
    "run.googleapis.com",
    "aiplatform.googleapis.com",
    "secretmanager.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}

# Least-privilege Service Account for Cloud Run
resource "google_service_account" "agent_sa" {
  account_id   = "cloud-finops-copilot-sa"
  display_name = "Cloud FinOps & Incident Remediation Copilot Service Account"
  depends_on   = [google_project_service.enabled_apis]
}

# Grant Vertex AI User and Log Writer roles to Service Account
resource "google_project_iam_member" "ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

# Secret Manager Secret for Gemini API Key
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.enabled_apis]
}

resource "google_secret_manager_secret_iam_member" "secret_access" {
  secret_id = google_secret_manager_secret.gemini_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_sa.email}"
}

# Google Cloud Run v2 Service
resource "google_cloud_run_v2_service" "agent_service" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.agent_sa.email
    containers {
      image = var.container_image
      resources {
        limits = {
          memory = "1024Mi"
          cpu    = "1000m"
        }
      }
      env {
        name  = "PORT"
        value = "8080"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name = "GEMINI_API_KEY_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.enabled_apis,
    google_project_iam_member.ai_user,
    google_project_iam_member.log_writer
  ]
}

# Allow public invocation for dashboard demo
resource "google_cloud_run_service_iam_member" "public_invoker" {
  service  = google_cloud_run_v2_service.agent_service.name
  location = google_cloud_run_v2_service.agent_service.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
