variable "project_id" {
  description = "Google Cloud Project ID for deploying the Cloud FinOps Copilot"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run deployment"
  type        = string
  default     = "us-east1"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "cloud-finops-copilot"
}

variable "container_image" {
  description = "Container image URI for Cloud Run deployment"
  type        = string
  default     = "gcr.io/cloudrun/hello"
}
