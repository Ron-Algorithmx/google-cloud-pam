locals {
  resource_types = {
    organizations = "cloudresourcemanager.googleapis.com/Organization"
    folders       = "cloudresourcemanager.googleapis.com/Folder"
    projects      = "cloudresourcemanager.googleapis.com/Project"
  }
}

resource "google_privileged_access_manager_entitlement" "this" {
  for_each = var.entitlements

  entitlement_id       = each.key
  location             = "global"
  parent               = each.value.parent
  max_request_duration = each.value.max_request_duration

  eligible_users {
    principals = each.value.eligible_principals
  }

  privileged_access {
    gcp_iam_access {
      resource      = "//cloudresourcemanager.googleapis.com/${each.value.parent}"
      resource_type = local.resource_types[split("/", each.value.parent)[0]]

      dynamic "role_bindings" {
        for_each = each.value.roles
        content {
          role                 = role_bindings.value.role
          condition_expression = role_bindings.value.condition
        }
      }
    }
  }

  requester_justification_config {
    unstructured {}
  }

  # No approvers means PAM grants access as soon as it is requested; access is
  # still time-boxed and audit-logged.
  dynamic "approval_workflow" {
    for_each = length(each.value.approver_principals) > 0 ? [1] : []
    content {
      manual_approvals {
        require_approver_justification = each.value.require_approver_justification
        steps {
          approvals_needed          = 1
          approver_email_recipients = each.value.approver_email_recipients
          approvers {
            principals = each.value.approver_principals
          }
        }
      }
    }
  }

  dynamic "additional_notification_targets" {
    for_each = length(each.value.admin_email_recipients) > 0 ? [1] : []
    content {
      admin_email_recipients = each.value.admin_email_recipients
    }
  }

  depends_on = [google_organization_iam_member.pam_service_agent]
}
