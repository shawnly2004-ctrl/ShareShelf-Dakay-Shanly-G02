import os

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from .models import AvailabilityWindow, BorrowRequest, Item

MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_EXT = {'.jpg', '.jpeg', '.png'}
MAX_PHOTOS = 5


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        clean_file = super().clean
        if isinstance(data, (list, tuple)):
            result = [clean_file(file, initial) for file in data]
        else:
            result = [clean_file(data, initial)]
        return [file for file in result if file]


class ItemForm(forms.ModelForm):
    photos = MultipleImageField(
        required=False,
        label="Photos (1 to 5, JPG or PNG, max 5 MB each)",
    )

    class Meta:
        model = Item
        fields = ['name', 'category', 'description', 'item_condition', 'pickup_note']
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs['class'] = css
        self.fields['photos'].widget.attrs['accept'] = 'image/png,image/jpeg'
        self.fields['category'].empty_label = "Select a category"

    def clean_photos(self):
        files = self.cleaned_data.get('photos') or []
        for file in files:
            if os.path.splitext(file.name)[1].lower() not in ALLOWED_EXT:
                raise ValidationError(f'"{file.name}" must be a JPG or PNG file.')
            if file.size > MAX_PHOTO_BYTES:
                raise ValidationError(f'"{file.name}" is larger than 5 MB.')
        return files

    def clean(self):
        cleaned = super().clean()
        new_files = cleaned.get('photos') or []
        existing = 0
        if self.instance.pk:
            removed = set(self.data.getlist('delete_photos'))
            existing = sum(
                1 for photo in self.instance.photos.all()
                if str(photo.pk) not in removed
            )
        total = existing + len(new_files)
        if total < 1:
            self.add_error('photos', "Upload at least 1 photo.")
        elif total > MAX_PHOTOS:
            self.add_error(
                'photos',
                f"An item can have at most {MAX_PHOTOS} photos (you would have {total}).",
            )
        return cleaned


class AvailabilityWindowForm(forms.ModelForm):
    class Meta:
        model = AvailabilityWindow
        fields = ['start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end:
            if end < start:
                self.add_error('end_date', "End date can't be before the start date.")
            elif end < timezone.localdate() and self.has_changed():
                self.add_error('end_date', "End date can't be in the past.")
        return cleaned


class BaseWindowFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active_windows = [
            form for form in self.forms
            if form.cleaned_data
            and not form.cleaned_data.get('DELETE')
            and form.cleaned_data.get('start_date')
            and form.cleaned_data.get('end_date')
        ]
        if not active_windows:
            raise ValidationError("Add at least one availability window.")


WindowFormSet = inlineformset_factory(
    Item,
    AvailabilityWindow,
    form=AvailabilityWindowForm,
    formset=BaseWindowFormSet,
    extra=1,
    can_delete=True,
)

MAX_ACTIVE_REQUESTS = 3
MAX_LOAN_DAYS = 7


class BorrowRequestForm(forms.ModelForm):
    class Meta:
        model = BorrowRequest
        fields = ['start_date', 'end_date', 'message']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'message': forms.Textarea(attrs={
                'rows': 3,
                'maxlength': 255,
                'placeholder': 'Optional: what do you need it for?',
            }),
        }

    def __init__(self, *args, item=None, borrower=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = item
        self.borrower = borrower
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if not (start and end):
            return cleaned

        if start < timezone.localdate():
            self.add_error('start_date', "Start date can't be in the past.")
            return cleaned
        if end < start:
            self.add_error('end_date', "End date can't be before the start date.")
            return cleaned
        if (end - start).days > MAX_LOAN_DAYS:
            raise ValidationError(f"A loan can last at most {MAX_LOAN_DAYS} days.")
        if not any(
            window.start_date <= start and end <= window.end_date
            for window in self.item.windows.all()
        ):
            raise ValidationError(
                "Your dates must fall entirely inside one of the item's availability windows."
            )
        if BorrowRequest.objects.filter(
            item=self.item,
            status__in=BorrowRequest.BLOCKING_STATUSES,
            start_date__lte=end,
            end_date__gte=start,
        ).exists():
            raise ValidationError("Those dates overlap with an approved loan. Pick other dates.")
        if BorrowRequest.objects.filter(
            item=self.item,
            borrower=self.borrower,
            status='pending',
        ).exists():
            raise ValidationError("You already have a pending request for this item.")

        active_requests = BorrowRequest.objects.filter(
            borrower=self.borrower,
            status__in=BorrowRequest.ACTIVE_STATUSES,
        ).count()
        if active_requests >= MAX_ACTIVE_REQUESTS:
            raise ValidationError(
                f"You can have at most {MAX_ACTIVE_REQUESTS} active requests at a time."
            )
        return cleaned
