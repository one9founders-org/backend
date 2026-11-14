#!/bin/bash
# Inspect production email OTP + SES state for tool-submit verification.
# Run on the EC2 host via appleboy/ssh-action (see inspect-tool-submit-email-otp.yml).
set -euo pipefail
cd /var/www/one9founders

echo "===== EmailVerificationCode (last 24h) ====="
docker compose exec -T web python manage.py shell -c '
from datetime import timedelta
from django.utils import timezone
from api.models import EmailVerificationCode

now = timezone.now()
day_ago = now - timedelta(hours=24)
qs = EmailVerificationCode.objects.filter(
    purpose=EmailVerificationCode.PURPOSE_TOOL_SUBMIT,
    created_at__gte=day_ago,
)
total = qs.count()
consumed = qs.filter(consumed_at__isnull=False).count()
active = qs.filter(consumed_at__isnull=True, expires_at__gt=now).count()
expired_unconsumed = qs.filter(consumed_at__isnull=True, expires_at__lte=now).count()
print("count_24h", total)
print("consumed", consumed)
print("active_unexpired", active)
print("expired_unconsumed", expired_unconsumed)
print("--- recent sample (email hashed/redacted) ---")
for row in qs.order_by("-created_at")[:25]:
    local, _, domain = row.email.partition("@")
    if len(local) <= 2:
        redacted_local = (local[:1] + "*") if local else "*"
    else:
        redacted_local = local[:2] + ("*" * min(8, len(local) - 2))
    redacted = f"{redacted_local}@{domain}"
    print(
        row.created_at.isoformat(),
        "id=", row.pk,
        "email=", redacted,
        "attempts=", row.attempts,
        "expires_at=", row.expires_at.isoformat(),
        "consumed_at=", row.consumed_at.isoformat() if row.consumed_at else None,
        "ip=", row.ip_address,
    )
'

echo "===== ToolSubmission (last 7 days) ====="
docker compose exec -T web python manage.py shell -c '
from datetime import timedelta
from django.db.models import Count
from django.utils import timezone
from api.models import ToolSubmission

week_ago = timezone.now() - timedelta(days=7)
qs = ToolSubmission.objects.filter(created_at__gte=week_ago)
print("total_7d", qs.count())
print("--- by status ---")
for row in qs.values("status").annotate(n=Count("id")).order_by("status"):
    print(row["status"], row["n"])
print("--- by enrichment_status ---")
for row in qs.values("enrichment_status").annotate(n=Count("id")).order_by("enrichment_status"):
    print(row["enrichment_status"], row["n"])
print("--- by status + enrichment_status ---")
for row in (
    qs.values("status", "enrichment_status")
    .annotate(n=Count("id"))
    .order_by("status", "enrichment_status")
):
    print(row["status"], row["enrichment_status"], row["n"])
'

echo "===== SES GetSendStatistics (last 48h) ====="
docker compose exec -T web python manage.py shell -c '
from datetime import datetime, timezone, timedelta
from django.conf import settings
import boto3

region = getattr(settings, "AWS_SES_REGION_NAME", None) or getattr(settings, "AWS_S3_REGION_NAME", None)
print("region", region)
client = boto3.client("ses", region_name=region)
try:
    resp = client.get_send_statistics()
except Exception as e:
    print("ses_error", type(e).__name__, str(e)[:500])
else:
    points = sorted(
        resp.get("SendDataPoints", []),
        key=lambda p: p.get("Timestamp") or datetime.min.replace(tzinfo=timezone.utc),
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    recent = [p for p in points if p.get("Timestamp") and p["Timestamp"] >= cutoff]
    print("datapoints_total", len(points), "recent_48h", len(recent))
    totals = {"DeliveryAttempts": 0, "Bounces": 0, "Complaints": 0, "Rejects": 0}
    for p in recent:
        for k in totals:
            totals[k] += int(p.get(k) or 0)
    print(
        "sums_48h",
        "delivery=", totals["DeliveryAttempts"],
        "bounces=", totals["Bounces"],
        "complaints=", totals["Complaints"],
        "rejects=", totals["Rejects"],
    )
    for p in recent[-25:]:
        print(
            p["Timestamp"].isoformat(),
            "delivery=", p.get("DeliveryAttempts"),
            "bounces=", p.get("Bounces"),
            "complaints=", p.get("Complaints"),
            "rejects=", p.get("Rejects"),
        )
'

echo "===== Email settings (DEFAULT_FROM_EMAIL / AWS_SES_REGION_NAME) ====="
docker compose exec -T web python manage.py shell -c '
from django.conf import settings

def show(name):
    raw = getattr(settings, name, None)
    present = raw is not None and str(raw).strip() != ""
    print(f"{name}_set", present)
    print(f"{name}_value", raw)

show("DEFAULT_FROM_EMAIL")
show("AWS_SES_REGION_NAME")
show("EMAIL_BACKEND")
show("AWS_SES_REGION_ENDPOINT")
print("AWS_ACCESS_KEY_ID_set", bool(getattr(settings, "AWS_ACCESS_KEY_ID", None)))
'

echo "===== App logs: tool-submit verification / Failed to send ====="
# Prefer container logs; fall back to compose logs on the host.
docker compose logs --tail=400 web 2>/dev/null | grep -E -i \
  "tool-submit verification|Failed to send tool-submit|Sent tool-submit verification|verification code|EmailVerification|django_ses|SES" \
  || echo "(no matching lines in last 400 web log lines)"

echo "===== done ====="
