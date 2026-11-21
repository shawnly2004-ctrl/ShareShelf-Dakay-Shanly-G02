from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .validators import LetterAndNumberValidator


class LetterAndNumberValidatorTests(SimpleTestCase):
    def setUp(self):
        self.validator = LetterAndNumberValidator()

    def test_accepts_password_with_letter_and_number(self):
        self.validator.validate("abc12345")

    def test_rejects_password_without_number(self):
        with self.assertRaises(ValidationError):
            self.validator.validate("abcdefgh")

    def test_rejects_password_without_letter(self):
        with self.assertRaises(ValidationError):
            self.validator.validate("12345678")
