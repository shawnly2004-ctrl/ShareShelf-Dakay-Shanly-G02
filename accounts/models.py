from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)   # hashes the password
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        extra.setdefault('role', 'admin')
        return self.create_user(email, password, **extra)

class Community(models.Model):
    name = models.CharField(max_length=100, unique=True)
    barangay = models.CharField(max_length=100)
    city = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = 'communities'
        ordering = ['name']

    def __str__(self):
        return self.name
    
class User(AbstractUser):
    ROLE_CHOICES = [('admin', 'Admin'), ('member', 'Member')]
    USER_TYPE_CHOICES = [('lender', 'Lender'), ('borrower', 'Borrower'), ('both', 'Both')]

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='both')
    contact_number = models.CharField(
        max_length=20,
        validators=[RegexValidator(
            regex=r'^[0-9]+$',
            message='Enter a valid contact number using digits only.',
        )],
    )
    community = models.ForeignKey(Community, on_delete=models.PROTECT, related_name='residents')
    profile_photo = models.ImageField(upload_to='profiles/', blank=True, null=True)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    rating_count = models.PositiveIntegerField(default=0)
    account_status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('flagged', 'Flagged')],
        default='active',
    )
    address_detail = models.CharField(max_length=200, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    language_pref = models.CharField(
        max_length=3,
        choices=[('en', 'English'), ('fil', 'Filipino')],
        default='en',
    )
    failed_login_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.email
    @property
    def barangay(self):
        """Keeps existing templates ({{ user.barangay }}) working."""
        return self.community.barangay if self.community else ''