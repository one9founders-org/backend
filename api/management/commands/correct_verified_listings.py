from django.core.management.base import BaseCommand

from api.verified_listings import persist_verified_listings


class Command(BaseCommand):
    help = (
        "Write hand-verified public facts for featured listings (currently Claude). "
        "Dry-run by default; pass --apply to persist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist verified fields. Default is dry-run.",
        )

    def handle(self, *args, **options):
        apply_mode = bool(options["apply"])
        reports = persist_verified_listings(apply=apply_mode)
        mode = "APPLY" if apply_mode else "DRY-RUN"
        self.stdout.write(f"correct_verified_listings ({mode})")
        for report in reports:
            slug = report["slug"]
            status = report["status"]
            before = report.get("before") or {}
            self.stdout.write(
                f"  {slug}: {status} "
                f"(trial={before.get('free_trial_days')}, "
                f"from={before.get('pricing_from')}, "
                f"models={before.get('pricing_models')})"
            )
        if not apply_mode:
            self.stdout.write("No rows written. Re-run with --apply to persist.")
