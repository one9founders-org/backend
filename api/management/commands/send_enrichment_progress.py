"""
Management command to send enrichment progress email notifications.
Can be run via cron job to send hourly updates.
"""

from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.conf import settings

from api.models import Tool


class Command(BaseCommand):
    help = "Send email notification with current enrichment progress"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default="one9founders@gmail.com",
            help="Email address to send progress report to",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print email content without sending",
        )

    def handle(self, *args, **options):
        # Get progress stats
        total_tools = Tool.objects.count()
        tools_with_categories = (
            Tool.objects.filter(categories__isnull=False).distinct().count()
        )
        tools_with_pricing = Tool.objects.exclude(pricing_type="freemium").count()

        remaining = total_tools - tools_with_categories
        percentage = (
            (tools_with_categories / total_tools) * 100 if total_tools > 0 else 0
        )

        # Estimate time remaining (assuming ~3 seconds per tool)
        estimated_hours = (remaining * 3) / 3600

        subject = f"[One9] Enrichment Progress: {percentage:.1f}% Complete"

        message = f"""
One9 Founders - Tool Enrichment Progress Report
================================================

Current Status:
- Total tools: {total_tools:,}
- Tools with categories: {tools_with_categories:,} ({percentage:.2f}%)
- Tools with pricing updated: {tools_with_pricing:,}
- Remaining tools: {remaining:,}

Estimated time to completion: ~{estimated_hours:.1f} hours

---
This is an automated progress report.
"""

        self.stdout.write(
            f"Progress: {tools_with_categories}/{total_tools} ({percentage:.2f}%)"
        )

        if options["dry_run"]:
            self.stdout.write("\n--- DRY RUN - Email would be sent: ---")
            self.stdout.write(f"To: {options['email']}")
            self.stdout.write(f"Subject: {subject}")
            self.stdout.write(message)
            return

        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[options["email"]],
                fail_silently=False,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Progress email sent to {options['email']}")
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to send email: {e}"))
