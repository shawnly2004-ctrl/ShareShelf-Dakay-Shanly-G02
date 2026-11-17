from django.conf import settings
from django.db import models
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