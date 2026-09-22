#!/bin/bash
set -euo pipefail
cd /var/www/one9founders

echo "===== DB listed_email_sent_at ====="
docker compose exec -T web python manage.py shell -c '
from django.db.models import Min, Max
from api.submission_mail import pending_listed_email_queryset, community_submission_queryset
base = community_submission_queryset()
sent = base.filter(listed_email_sent_at__isnull=False)
print("approved_community", base.count())
print("pending_unsent", pending_listed_email_queryset().count())
print("already_sent", sent.count())
print("sent_min", sent.aggregate(m=Min("listed_email_sent_at"))["m"])
print("sent_max", sent.aggregate(m=Max("listed_email_sent_at"))["m"])
print("unique_emails", sent.values("submitter_email").distinct().count())
'

echo "===== SES GetSendStatistics ====="
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
    points = sorted(resp.get("SendDataPoints", []), key=lambda p: p.get("Timestamp") or datetime.min.replace(tzinfo=timezone.utc))
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    recent = [p for p in points if p.get("Timestamp") and p["Timestamp"] >= cutoff]
    print("datapoints_total", len(points), "recent_48h", len(recent))
    for p in recent[-25:]:
        print(
            p["Timestamp"].isoformat(),
            "delivery=", p.get("DeliveryAttempts"),
            "bounces=", p.get("Bounces"),
            "complaints=", p.get("Complaints"),
            "rejects=", p.get("Rejects"),
        )
'
