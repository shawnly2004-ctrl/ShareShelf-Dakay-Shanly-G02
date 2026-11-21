from django.core.exceptions import ValidationError


class LetterAndNumberValidator:
    def validate(self, password, user=None):
        if not any(character.isalpha() for character in password):
            raise ValidationError(
                "Password must contain at least one letter.",
                code="password_no_letter",
            )
        if not any(character.isdigit() for character in password):
            raise ValidationError(
                "Password must contain at least one number.",
                code="password_no_number",
            )

    def get_help_text(self):
        return "Your password must contain at least one letter and at least one number."
