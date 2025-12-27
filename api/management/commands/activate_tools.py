from django.core.management.base import BaseCommand
from api.models import Tool


class Command(BaseCommand):
    help = 'Mark all tools as active'

    def handle(self, *args, **options):
        updated = Tool.objects.update(is_active=True)
        self.stdout.write(
            self.style.SUCCESS(f'Successfully activated {updated} tools')
        )