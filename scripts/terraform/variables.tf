variable "org_id" {
  description = "Numeric organization ID for abcd.org (gcloud organizations list)."
  type        = string
}

variable "admin_project_id" {
  description = "Project where the PAM API is enabled and billed."
  type        = string
}

variable "entitlements" {
  description = "PAM entitlements keyed by entitlement ID (4-63 chars: lowercase letters, digits, hyphens; starts with a letter)."
  type = map(object({
    parent = string # organizations/NUMBER, folders/NUMBER, or projects/PROJECT_ID
    roles = list(object({
      role      = string
      condition = optional(string)
    }))
    eligible_principals            = list(string)
    approver_principals            = optional(list(string), []) # empty = no approval step, grant activates immediately
    max_request_duration           = optional(string, "3600s")  # PAM allows 1800s to 604800s
    require_approver_justification = optional(bool, true)
    approver_email_recipients      = optional(list(string), [])
    admin_email_recipients         = optional(list(string), [])
  }))
  default = {}

  validation {
    condition = alltrue([
      for e in values(var.entitlements) :
      can(regex("^(organizations|folders|projects)/[^/]+$", e.parent))
    ])
    error_message = "Each entitlement parent must be organizations/NUMBER, folders/NUMBER, or projects/PROJECT_ID."
  }
}
