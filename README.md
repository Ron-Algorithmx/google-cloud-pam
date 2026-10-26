# Google Cloud Privileged Access Manager (PAM) for abcd.org

Terraform for just-in-time (JIT) admin access. Nobody holds admin roles all the
time. People are *eligible* for them through PAM **entitlements** and request a
time-limited **grant** when they need one, with approval where it matters.

New to PAM? Start with [HOW-PAM-WORKS.md](HOW-PAM-WORKS.md), a beginner's guide with diagrams.
To try it hands-on in a throwaway project, follow [TRY-PAM.md](TRY-PAM.md).
To post requests and approvals to Slack, see [SLACK-NOTIFICATIONS.md](SLACK-NOTIFICATIONS.md).

- **Entitlements** (who can get which roles, for how long, who approves) are managed here in Terraform.
- **Grants** (individual requests) are runtime events. Request and approve them with `gcloud` or the console, never in Terraform.

## How it works

When a grant activates, PAM's org-level service agent
(`service-org-ORG_NUMBER@gcp-sa-pam.iam.gserviceaccount.com`) adds a role
binding with a time-based IAM condition to the resource's allow policy, and
removes it when the grant ends. Every request, approval and revocation is
written to Cloud Audit Logs.

## Files

All Terraform lives in `scripts/terraform/`.

| File | Purpose |
|---|---|
| `versions.tf` | Provider setup. Bills org-level PAM API calls to the admin project. |
| `main.tf` | Enables the PAM API and grants the service agent its role (non-authoritative). |
| `entitlements.tf` | One entitlement per entry in `var.entitlements`. Adds an approval step only when approvers are listed. |
| `variables.tf` | Inputs, including the `entitlements` map schema. |
| `outputs.tf` | Full entitlement names, for use with `gcloud pam grants create`. |
| `terraform.tfvars.example` | Example entitlements. Copy to `terraform.tfvars`. |

## Prerequisites

- Terraform >= 1.5 and Google provider >= 6.0
- An admin project to enable the PAM API in
- The identity running Terraform needs, on the organization:
  - `roles/privilegedaccessmanager.admin`
  - `roles/iam.securityAdmin` (use `roles/resourcemanager.folderAdmin` or `roles/resourcemanager.projectIamAdmin` instead for folder- or project-level entitlements)

This identity can grant itself anything, so treat it as one of the most
sensitive identities in the org. Run it from CI with protected branches.

## Usage

```bash
cd scripts/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in real IDs and emails
terraform init
terraform plan
terraform apply
```

Add a remote backend (a GCS bucket) before using this for real. State is
local by default.

If applying `google_organization_iam_member.pam_service_agent` fails because
the service agent doesn't exist yet, open **IAM & Admin → Privileged Access
Manager** in the console, run **Set up PAM** once for the organization, then
apply again.

Check onboarding:

```bash
gcloud pam check-onboarding-status --organization=ORG_ID --location=global
```

## Adding an entitlement

Add an entry to `entitlements` in `scripts/terraform/terraform.tfvars`. The map key becomes the
entitlement ID (4-63 characters: lowercase letters, digits, hyphens; must
start with a letter).

```hcl
"prod-gke-admin" = {
  parent               = "folders/987654321098"   # organizations/N, folders/N or projects/ID
  roles                = [{ role = "roles/container.admin" }]
  eligible_principals  = ["group:gcp-platform@abcd.org"]
  approver_principals  = ["group:gcp-pam-approvers@abcd.org"]   # omit for no approval
  max_request_duration = "3600s"                                 # 1800s to 604800s
}
```

Optional fields: `require_approver_justification` (default `true`),
`approver_email_recipients`, `admin_email_recipients`, and a `condition` on
each role to narrow it with an IAM condition.

To bring an entitlement created in the console under Terraform, add it to
`terraform.tfvars` and use an `import` block:

```hcl
import {
  to = google_privileged_access_manager_entitlement.this["prod-gke-admin"]
  id = "folders/987654321098/locations/global/entitlements/prod-gke-admin"
}
```

## Requesting and approving access

The examples use bash line breaks (`\`). In PowerShell, use a backtick instead.
For project-level entitlements, use `--project` instead of `--organization`.

```bash
# Requester: list what you can request, then request it
gcloud pam entitlements search --caller-access-type=grant-requester \
  --location=global --organization=ORG_ID
gcloud pam grants create --entitlement=org-admin --requested-duration=3600s \
  --justification="INC-1234: fix IAM on prod folder" \
  --location=global --organization=ORG_ID

# Approver: list pending grants, then approve or deny
gcloud pam grants search --entitlement=org-admin --caller-relationship=can-approve \
  --location=global --organization=ORG_ID
gcloud pam grants approve GRANT_ID --entitlement=org-admin --reason="OK for INC-1234" \
  --location=global --organization=ORG_ID
gcloud pam grants deny GRANT_ID --entitlement=org-admin --reason="No ticket" \
  --location=global --organization=ORG_ID

# PAM admin: end a grant early
gcloud pam grants revoke GRANT_ID --entitlement=org-admin --reason="Work finished" \
  --location=global --organization=ORG_ID
```

Requests that nobody approves or denies expire after 24 hours. Access takes a
minute or two to work after approval because of normal IAM propagation.

## Rollout order

Do these in order, or you can lock yourself out:

1. Create 1-2 **break-glass** accounts that keep org admin permanently, use
   hardware security keys, have credentials stored offline, and alert on
   every login. They are the way in if PAM or the approvers are unavailable.
2. Apply this config and test a full cycle: request, approve, use, expire.
3. Only then remove standing admin roles and `roles/iam.serviceAccountTokenCreator`
   from everyday accounts (for example `jdoe` and `jdoe-adm`).

## Rules and gotchas

- **Never use authoritative IAM resources** (`google_organization_iam_policy`,
  `google_folder_iam_policy`, `google_project_iam_policy`) anywhere in the org.
  An apply while a grant is active wipes PAM's binding. Use `_iam_member`.
- **Don't edit PAM-managed role bindings by hand.** It can break PAM.
- **Nobody can approve their own grant.** Each approval group needs at least
  one person other than the requester.
- **PAM can be bypassed** by anyone with standing `setIamPolicy` on the org or
  with PAM Admin (they can add themselves to an entitlement). Keep that list to
  the break-glass accounts and the Terraform pipeline.
- **Admin grants can leave permanent access behind.** Someone holding
  `organizationAdmin` for an hour can add themselves permanently during that
  hour. Alert on IAM policy changes.
- **Limits:**
  - a grant lasts 30 minutes to 7 days
  - each requester or approver list holds at most 20 entries (use groups to cover more people)
  - at most 30 roles per entitlement
  - legacy Owner/Editor/Viewer roles are not allowed
  - at most 10 open grants per entitlement
- **Preview features** (multi-level approvals, requesting a narrower scope)
  need Security Command Center Premium or Enterprise and aren't used here.

## Monitoring

Cloud Logging filter for all PAM activity:

```
protoPayload.serviceName="privilegedaccessmanager.googleapis.com"
```

For real-time alerts (for example to chat), create a Cloud Asset Inventory
feed for asset type `privilegedaccessmanager.googleapis.com/Grant` that
publishes to Pub/Sub.

## References

- [PAM overview](https://docs.cloud.google.com/iam/docs/pam-overview)
- [Permissions and setup](https://docs.cloud.google.com/iam/docs/pam-permissions-and-setup)
- [Create entitlements](https://docs.cloud.google.com/iam/docs/pam-create-entitlements)
- [gcloud pam reference](https://docs.cloud.google.com/sdk/gcloud/reference/pam)
- [Terraform: google_privileged_access_manager_entitlement](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/privileged_access_manager_entitlement)
