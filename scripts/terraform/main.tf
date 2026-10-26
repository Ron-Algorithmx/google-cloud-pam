resource "google_project_service" "pam" {
  project            = var.admin_project_id
  service            = "privilegedaccessmanager.googleapis.com"
  disable_on_destroy = false
}

# PAM uses one org-level service agent to add and remove the temporary role
# bindings for every grant. This is non-authoritative on purpose: if org IAM is
# ever managed with google_organization_iam_policy, an apply during an active
# grant will strip PAM's binding.
resource "google_organization_iam_member" "pam_service_agent" {
  org_id = var.org_id
  role   = "roles/privilegedaccessmanager.serviceAgent"
  member = "serviceAccount:service-org-${var.org_id}@gcp-sa-pam.iam.gserviceaccount.com"

  depends_on = [google_project_service.pam]
}
