from django.conf import settings
from django.db import models
from django.utils import timezone


class Item(models.Model):
    CATEGORY_CHOICES = [
        ('power_tools', 'Power Tools'),
        ('hand_tools', 'Hand Tools'),
        ('ladders', 'Ladders & Climbing'),
        ('garden', 'Garden & Outdoor'),
        ('camping', 'Camping & Sports'),
        ('electronics', 'Electronics & Projectors'),
        ('kitchen', 'Kitchen & Party'),
        ('other', 'Other'),
    ]
    CONDITION_CHOICES = [
        ('new', 'Like new'),
        ('good', 'Good'),
        ('fair', 'Fair (works, has wear)'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name='items')
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    description = models.TextField()
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES, default='good')
    photo = models.ImageField(upload_to='items/')
    available_from = models.DateField()
    available_until = models.DateField()
    is_available = models.BooleanField(default=True)   # owner can pause a listing
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.owner.email})"

    @property
    def is_open_now(self):
        today = timezone.localdate()
        return self.is_available and self.available_from <= today <= self.available_until


class BorrowRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Returned'),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='requests')
    borrower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='borrow_requests')
    start_date = models.DateField()
    end_date = models.DateField()
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    owner_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.borrower.email} -> {self.item.name} ({self.status})"

    def has_conflict(self):
        """True if another approved request overlaps these dates."""
        return BorrowRequest.objects.filter(
            item=self.item, status='approved',
            start_date__lte=self.end_date, end_date__gte=self.start_date,
        ).exclude(pk=self.pk).exists()
    
    