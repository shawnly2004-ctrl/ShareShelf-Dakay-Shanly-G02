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