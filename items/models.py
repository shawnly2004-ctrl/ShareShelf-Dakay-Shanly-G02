from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Item(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('on_loan', 'On loan'),
        ('unlisted', 'Unlisted'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='items')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='items')
    name = models.CharField(max_length=100)
    description = models.TextField()
    item_condition = models.CharField(max_length=100, blank=True)
    pickup_note = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='available')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.owner.email})"

    @property
    def primary_photo(self):
        photos = list(self.photos.all())
        for photo in photos:
            if photo.is_primary:
                return photo
        return photos[0] if photos else None

    @property
    def is_open_now(self):
        if self.status != 'available':
            return False
        today = timezone.localdate()
        return any(window.start_date <= today <= window.end_date
                   for window in self.windows.all())

    @property
    def next_window(self):
        today = timezone.localdate()
        upcoming = [window for window in self.windows.all()
                    if window.end_date >= today]
        return upcoming[0] if upcoming else None


class ItemPhoto(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='items/')
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'uploaded_at']

    def __str__(self):
        return f"Photo {self.pk} of {self.item.name}"


class AvailabilityWindow(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='windows')
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ['start_date']
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F('start_date')),
                name='window_end_after_start',
            ),
        ]

    def __str__(self):
        return f"{self.item.name}: {self.start_date} to {self.end_date}"


class BorrowRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('borrowed', 'Borrowed'),
        ('overdue', 'Overdue'),
        ('completed', 'Completed'),
    ]
    ACTIVE_STATUSES = ('pending', 'approved', 'borrowed', 'overdue')
    BLOCKING_STATUSES = ('approved', 'borrowed', 'overdue')

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='requests')
    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='borrow_requests',
    )
    start_date = models.DateField()
    end_date = models.DateField()
    message = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-requested_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F('start_date')),
                name='request_end_after_start',
            ),
        ]

    def __str__(self):
        return f"{self.borrower.email} -> {self.item.name} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=3)
        super().save(*args, **kwargs)

    def overlapping_blocking(self):
        return BorrowRequest.objects.filter(
            item=self.item,
            status__in=self.BLOCKING_STATUSES,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exclude(pk=self.pk)

    @classmethod
    def expire_stale(cls):
        stale_requests = list(cls.objects.filter(
            status='pending',
            expires_at__lt=timezone.now(),
        ).select_related('item', 'borrower', 'item__owner'))
        for borrow_request in stale_requests:
            with transaction.atomic():
                borrow_request.status = 'expired'
                borrow_request.save(update_fields=['status'])
                Notification.create_for_participants(
                    borrow_request,
                    'request_expired',
                    f'The request for "{borrow_request.item.name}" has expired.',
                )
        return len(stale_requests)

    @classmethod
    def mark_overdue(cls):
        today = timezone.localdate()
        overdue_requests = list(cls.objects.filter(
            status='borrowed',
            end_date__lt=today,
        ).select_related('item', 'borrower', 'item__owner'))
        for borrow_request in overdue_requests:
            with transaction.atomic():
                borrow_request.status = 'overdue'
                borrow_request.save(update_fields=['status'])
                Notification.create_for_user(
                    borrow_request.borrower,
                    borrow_request,
                    'overdue',
                    f'The return for "{borrow_request.item.name}" is overdue.',
                )
        return len(overdue_requests)


class HandoffConfirmation(models.Model):
    HANDOFF_TYPE_CHOICES = [
        ('pickup', 'Pickup'),
        ('return', 'Return'),
    ]

    request = models.ForeignKey(
        BorrowRequest,
        on_delete=models.CASCADE,
        related_name='handoffs',
    )
    handoff_type = models.CharField(max_length=10, choices=HANDOFF_TYPE_CHOICES)
    lender_confirmed_at = models.DateTimeField(null=True, blank=True)
    borrower_confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['request', 'handoff_type'],
                name='unique_request_handoff_type',
            ),
        ]

    def __str__(self):
        return f"{self.handoff_type.title()} confirmation for request {self.request_id}"


class Rating(models.Model):
    request = models.ForeignKey(
        BorrowRequest,
        on_delete=models.CASCADE,
        related_name='ratings',
    )
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ratings_given',
    )
    ratee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ratings_received',
    )
    score = models.PositiveSmallIntegerField()
    review_text = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(score__gte=1, score__lte=5),
                name='rating_score_between_1_and_5',
            ),
            models.CheckConstraint(
                condition=~Q(rater=F('ratee')),
                name='rating_rater_not_ratee',
            ),
            models.UniqueConstraint(
                fields=['request', 'rater'],
                name='unique_request_rater',
            ),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rater.email} rated {self.ratee.email}: {self.score}/5"

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.db.models import Avg

        aggregate = Rating.objects.filter(ratee=self.ratee).aggregate(
            average=Avg('score'),
            count=models.Count('pk'),
        )
        average = aggregate['average']
        count = aggregate['count']
        self.ratee.avg_rating = average if average is not None else None
        self.ratee.rating_count = count
        self.ratee.account_status = (
            'flagged'
            if count >= 5 and average is not None and average < 2.5
            else 'active'
        )
        self.ratee.save(update_fields=[
            'avg_rating',
            'rating_count',
            'account_status',
        ])


class Notification(models.Model):
    NOTIF_TYPE_CHOICES = [
        ('request_received', 'Request received'),
        ('request_approved', 'Request approved'),
        ('request_declined', 'Request declined'),
        ('request_expired', 'Request expired'),
        ('pickup_confirmed', 'Pickup confirmed'),
        ('return_confirmed', 'Return confirmed'),
        ('due_reminder', 'Due reminder'),
        ('overdue', 'Overdue'),
        ('rating_received', 'Rating received'),
        ('wishlist_match', 'Wishlist match'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    request = models.ForeignKey(
        BorrowRequest,
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
    )
    notif_type = models.CharField(max_length=30, choices=NOTIF_TYPE_CHOICES)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.notif_type} for {self.user.email}"

    @classmethod
    def create_for_user(cls, user, borrow_request, notif_type, message):
        return cls.objects.create(
            user=user,
            request=borrow_request,
            notif_type=notif_type,
            message=message,
        )

    @classmethod
    def create_for_participants(cls, borrow_request, notif_type, message):
        cls.create_for_user(
            borrow_request.borrower,
            borrow_request,
            notif_type,
            message,
        )
        cls.create_for_user(
            borrow_request.item.owner,
            borrow_request,
            notif_type,
            message,
        )

    @classmethod
    def send_due_reminders(cls):
        from django.utils import timezone

        tomorrow = timezone.localdate() + timedelta(days=1)
        requests = BorrowRequest.objects.filter(
            status='borrowed',
            end_date=tomorrow,
        ).select_related('item', 'borrower')
        count = 0
        for borrow_request in requests:
            if not cls.objects.filter(
                user=borrow_request.borrower,
                request=borrow_request,
                notif_type='due_reminder',
            ).exists():
                cls.create_for_user(
                    borrow_request.borrower,
                    borrow_request,
                    'due_reminder',
                    f'Return "{borrow_request.item.name}" tomorrow.',
                )
                count += 1
        return count

    @classmethod
    def match_wishlist(cls, item):
        if item.status != 'available':
            return 0

        count = 0
        entries = Wishlist.objects.filter(
            is_active=True,
            user__community_id=item.owner.community_id,
        ).exclude(user=item.owner).select_related('user', 'category')

        notified_users = set(
            cls.objects.filter(
                notif_type='wishlist_match',
                message__contains=item.name,
                user__community_id=item.owner.community_id,
            ).values_list('user_id', flat=True)
        )

        for entry in entries:
            if entry.user_id in notified_users:
                continue
            category_matches = entry.category_id == item.category_id
            keyword_matches = bool(
                entry.keyword
                and entry.keyword.lower() in item.name.lower()
            )
            if category_matches or keyword_matches:
                cls.objects.create(
                    user=entry.user,
                    request=None,
                    notif_type='wishlist_match',
                    message=f'A matching item "{item.name}" was listed in your community.',
                )
                notified_users.add(entry.user_id)
                count += 1
        return count


class Wishlist(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='wishlists',
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wishlists',
    )
    keyword = models.CharField(max_length=60, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=~Q(category__isnull=True, keyword=''),
                name='wishlist_category_or_keyword',
            ),
        ]

    def __str__(self):
        return self.keyword or (self.category.name if self.category else 'Wishlist')