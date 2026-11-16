from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractUser, BaseUserManager
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


class User(AbstractUser):
    ROLE_CHOICES = [('admin', 'Admin'), ('member', 'Member')]
    USER_TYPE_CHOICES = [('lender', 'Lender'), ('borrower', 'Borrower'), ('both', 'Both')]

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='both')
    contact_number = models.CharField(max_length=20, blank=True)
    barangay = models.CharField(max_length=100, blank=True)
    profile_photo = models.ImageField(upload_to='profiles/', blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.email