#!/bin/bash
set -euo pipefail
cd /var/www/one9founders
docker compose exec -T web python manage.py shell -c '
from django.db.models import Count, Min, Max
from api.models import ToolSubmission
from api.submission_mail import EXTENSION_SUBMITTER, pending_listed_email_queryset, community_submission_queryset

base = community_submission_queryset()
pending = pending_listed_email_queryset()
sent = base.filter(listed_email_sent_at__isnull=False)
print("approved_community", base.count())
print("pending_unsent", pending.count())
print("already_sent", sent.count())
print("sent_min", sent.aggregate(m=Min("listed_email_sent_at"))["m"])
print("sent_max", sent.aggregate(m=Max("listed_email_sent_at"))["m"])
print("--- recent sent (up to 10) ---")
for row in sent.order_by("-listed_email_sent_at")[:10]:
    print(row.listed_email_sent_at, row.submitter_email, row.name)
'
