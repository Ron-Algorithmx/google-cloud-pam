output "entitlement_names" {
  description = "Full entitlement names; pass one to gcloud pam grants create --entitlement=..."
  value       = { for k, e in google_privileged_access_manager_entitlement.this : k => e.id }
}
