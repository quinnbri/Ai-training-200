output "cloud_run_service_url" {
  description = "Public URL of the deployed Cloud FinOps Copilot service"
  value       = google_cloud_run_v2_service.agent_service.uri
}

output "service_account_email" {
  description = "Service account email used by the Cloud FinOps Copilot"
  value       = google_service_account.agent_sa.email
}
