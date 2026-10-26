terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0"
    }
  }
}

provider "google" {
  # Org- and folder-level PAM calls have no project of their own, so quota
  # is billed to the admin project where the API is enabled.
  billing_project       = var.admin_project_id
  user_project_override = true
}
