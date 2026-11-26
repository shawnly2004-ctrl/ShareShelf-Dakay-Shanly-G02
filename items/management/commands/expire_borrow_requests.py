from django.core.management.base import BaseCommand

from items.models import BorrowRequest


class Command(BaseCommand):
    help = 'Expire pending borrow requests whose response deadline has passed.'

    def handle(self, *args, **options):
        expired_count = BorrowRequest.expire_stale()
        self.stdout.write(
            self.style.SUCCESS(
                f'Expired {expired_count} stale borrow request(s).'
            )
        )
