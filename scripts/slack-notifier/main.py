"""Posts Privileged Access Manager grant changes to a Slack channel.

Triggered by Pub/Sub messages from a Cloud Asset Inventory feed on
privilegedaccessmanager.googleapis.com/Grant assets. Each message carries the
grant as it is now (asset) and as it was before the change (priorAsset).
"""

import base64
import json
import os
import urllib.request

import functions_framework

SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

CONSOLE_URL = "https://console.cloud.google.com/iam-admin/pam/entitlements/"

# States worth a message. Transitional states (SCHEDULED, ACTIVATING, REVOKING,
# WITHDRAWING) are skipped: the state that follows them is the news.
STATE_TEXT = {
    "APPROVAL_AWAITED": "is waiting for approval",
    "ACTIVE": "is now active",
    "DENIED": "was denied",
    "EXPIRED": "expired without a decision",
    "ACTIVATION_FAILED": "failed to activate",
    "REVOKED": "was revoked",
    "WITHDRAWN": "was withdrawn by the requester",
    "ENDED": "has ended",
}

# Which timeline event names the person behind each state.
STATE_ACTOR = {
    "ACTIVE": ("approved", "Approved by"),
    "DENIED": ("denied", "Denied by"),
    "REVOKED": ("revoked", "Revoked by"),
}

CONSOLE_SCOPE_PARAM = {
    "organizations": "organizationId",
    "folders": "folder",
    "projects": "project",
}


@functions_framework.cloud_event
def notify(cloud_event):
    message = json.loads(base64.b64decode(cloud_event.data["message"]["data"]))
    grant = message.get("asset", {}).get("resource", {}).get("data", {})
    prior = (message.get("priorAsset") or {}).get("resource", {}).get("data", {})
    state = grant.get("state")

    # The feed fires on every change to a grant; only announce a new state.
    if message.get("deleted") or state not in STATE_TEXT or state == prior.get("state"):
        return

    post_to_slack(format_message(grant, state))


def format_message(grant, state):
    # organizations/123/locations/global/entitlements/org-admin/grants/abc
    parts = grant.get("name", "").split("/")
    scope_type, scope_id = (parts[0], parts[1]) if len(parts) > 1 else ("", "")
    entitlement = parts[5] if len(parts) > 5 else "unknown entitlement"

    requester = grant.get("requester", "someone")
    duration = human_duration(grant.get("requestedDuration", ""))
    reason = (grant.get("justification") or {}).get("unstructuredJustification") or "none given"
    bindings = grant.get("privilegedAccess", {}).get("gcpIamAccess", {}).get("roleBindings", [])
    roles = ", ".join(b["role"] for b in bindings if b.get("role"))

    lines = [
        f"*{escape(requester)}*'s request for *{escape(entitlement)}* "
        f"({duration}) {STATE_TEXT[state]}"
    ]
    if state in STATE_ACTOR:
        event_name, label = STATE_ACTOR[state]
        event = latest_event(grant, event_name)
        if event.get("actor"):
            lines.append(f"{label}: {escape(event['actor'])}")
        if event.get("reason"):
            lines.append(f"Their reason: {escape(event['reason'])}")
    lines.append(f"Requester's reason: {escape(reason)}")
    if roles:
        lines.append(f"Roles: {escape(roles)}")
    if state == "APPROVAL_AWAITED":
        lines.append(
            f"<{console_link(scope_type, scope_id)}|Review in the console> "
            "(Approve grants tab)"
        )
    return "\n".join(lines)


def latest_event(grant, event_name):
    for event in reversed(grant.get("timeline", {}).get("events", [])):
        if event_name in event:
            return event[event_name] or {}
    return {}


def human_duration(value):
    try:
        seconds = int(float(value.rstrip("s")))
    except ValueError:
        return "unknown duration"
    hours, minutes = divmod(seconds // 60, 60)
    if hours and minutes:
        return f"{hours} h {minutes} min"
    return f"{hours} h" if hours else f"{minutes} min"


def console_link(scope_type, scope_id):
    param = CONSOLE_SCOPE_PARAM.get(scope_type)
    return f"{CONSOLE_URL}?{param}={scope_id}" if param else CONSOLE_URL


def escape(text):
    # Slack treats &, < and > as control characters in message text.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def post_to_slack(text):
    request = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
