from django import forms
from django.utils import timezone
from .models import Item


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ['name', 'category', 'description', 'condition',
                  'photo', 'available_from', 'available_until']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'available_from': forms.DateInput(attrs={'type': 'date'}),
            'available_until': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.Select,)):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'
        self.fields['photo'].widget.attrs['accept'] = 'image/*'

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        # Only check newly uploaded files (they have content_type)
        if photo and hasattr(photo, 'content_type'):
            if photo.size > 2 * 1024 * 1024:
                raise forms.ValidationError("Image must be 2 MB or smaller.")
        return photo

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('available_from')
        end = cleaned.get('available_until')
        if start and end:
            if end < start:
                self.add_error('available_until', "End date can't be before the start date.")
            elif end < timezone.localdate():
                self.add_error('available_until', "End date can't be in the past.")
        return cleaned