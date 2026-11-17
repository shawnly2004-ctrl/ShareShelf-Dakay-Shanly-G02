from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.datastructures import MultiValueDict
from PIL import Image

from .forms import AvailabilityWindowForm, ItemForm, WindowFormSet
from .models import AvailabilityWindow, Category, Item, ItemPhoto


def png_upload(name='photo.png', padding_bytes=0):
    image = Image.new('RGB', (1, 1), color='blue')
    content = BytesIO()
    image.save(content, format='PNG')
    return SimpleUploadedFile(
        name,
        content.getvalue() + (b'\0' * padding_bytes),
        content_type='image/png',
    )


class ItemPhotoFormTests(SimpleTestCase):
    def test_requires_at_least_one_photo(self):
        form = ItemForm(data={}, files=MultiValueDict())

        self.assertIn('photos', form.errors)
        self.assertIn('Upload at least 1 photo.', str(form.errors['photos']))

    def test_rejects_more_than_five_photos(self):
        uploads = MultiValueDict({'photos': [png_upload(f'{index}.png') for index in range(6)]})
        form = ItemForm(data={}, files=uploads)

        self.assertIn('at most 5 photos', str(form.errors['photos']))

    def test_rejects_non_jpeg_or_png_extension(self):
        uploads = MultiValueDict({'photos': [png_upload('photo.gif')]})
        form = ItemForm(data={}, files=uploads)

        self.assertIn('must be a JPG or PNG file', str(form.errors['photos']))

    def test_rejects_photo_larger_than_five_megabytes(self):
        uploads = MultiValueDict({
            'photos': [png_upload(padding_bytes=5 * 1024 * 1024 + 1)],
        })
        form = ItemForm(data={}, files=uploads)

        self.assertIn('is larger than 5 MB', str(form.errors['photos']))


class AvailabilityWindowFormTests(SimpleTestCase):
    def test_rejects_end_before_start(self):
        today = timezone.localdate()
        form = AvailabilityWindowForm(data={
            'start_date': (today + timedelta(days=2)).isoformat(),
            'end_date': (today + timedelta(days=1)).isoformat(),
        })

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors.as_data()['end_date'][0].message,
            "End date can't be before the start date.",
        )

    def test_formset_requires_at_least_one_window(self):
        formset = WindowFormSet(data={
            'windows-TOTAL_FORMS': '1',
            'windows-INITIAL_FORMS': '0',
            'windows-MIN_NUM_FORMS': '0',
            'windows-MAX_NUM_FORMS': '1000',
            'windows-0-start_date': '',
            'windows-0-end_date': '',
        }, prefix='windows')

        self.assertFalse(formset.is_valid())
        self.assertIn('Add at least one availability window.', str(formset.non_form_errors()))


class ItemWorkflowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_directory = TemporaryDirectory()
        cls.media_settings = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.media_settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_settings.disable()
        cls.media_directory.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.community = self.create_community('Community One')
        self.owner = self.create_user('owner@example.com', self.community)
        self.category = Category.objects.create(name='Test tools')
        self.client.force_login(self.owner)

    def create_community(self, name):
        from accounts.models import Community

        return Community.objects.create(name=name, barangay=name, city='Test City')

    def create_user(self, email, community):
        return get_user_model().objects.create_user(
            email=email,
            password='test-password',
            community=community,
            user_type='lender',
        )

    def create_item(self, name, owner, category, start_date, end_date):
        item = Item.objects.create(
            owner=owner,
            category=category,
            name=name,
            description='Test item',
        )
        ItemPhoto.objects.create(item=item, image=png_upload(), is_primary=True)
        AvailabilityWindow.objects.create(
            item=item,
            start_date=start_date,
            end_date=end_date,
        )
        return item

    def test_create_filter_and_toggle_items(self):
        today = timezone.localdate()
        window_start = today + timedelta(days=1)
        window_end = today + timedelta(days=5)
        response = self.client.post(reverse('item_create'), {
            'name': 'My listing',
            'category': str(self.category.pk),
            'description': 'A test listing',
            'item_condition': 'Good',
            'pickup_note': '',
            'photos': [png_upload(f'photo-{index}.png') for index in range(3)],
            'windows-TOTAL_FORMS': '2',
            'windows-INITIAL_FORMS': '0',
            'windows-MIN_NUM_FORMS': '0',
            'windows-MAX_NUM_FORMS': '1000',
            'windows-0-start_date': window_start.isoformat(),
            'windows-0-end_date': window_end.isoformat(),
            'windows-1-start_date': (window_start + timedelta(days=7)).isoformat(),
            'windows-1-end_date': (window_end + timedelta(days=7)).isoformat(),
        })

        self.assertEqual(response.status_code, 302)
        item = Item.objects.get(name='My listing')
        self.assertEqual(item.photos.count(), 3)
        self.assertEqual(item.photos.filter(is_primary=True).count(), 1)
        self.assertEqual(item.windows.count(), 2)

        photos = list(item.photos.order_by('uploaded_at'))
        primary_photo = next(photo for photo in photos if photo.is_primary)
        next_primary = next(photo for photo in photos if photo.pk != primary_photo.pk)
        windows = WindowFormSet(instance=item, prefix='windows')
        edit_data = {
            'name': item.name,
            'category': str(item.category_id),
            'description': item.description,
            'item_condition': item.item_condition,
            'pickup_note': item.pickup_note,
            'delete_photos': [str(primary_photo.pk)],
            'primary_photo': str(next_primary.pk),
            'windows-TOTAL_FORMS': '3',
            'windows-INITIAL_FORMS': '2',
            'windows-MIN_NUM_FORMS': '0',
            'windows-MAX_NUM_FORMS': '1000',
        }
        for index, window_form in enumerate(windows.initial_forms):
            for hidden in window_form.hidden_fields():
                edit_data[hidden.html_name] = hidden.value()
            edit_data[f'windows-{index}-start_date'] = window_form.instance.start_date.isoformat()
            edit_data[f'windows-{index}-end_date'] = window_form.instance.end_date.isoformat()
        for hidden in windows.empty_form.hidden_fields():
            edit_data[hidden.html_name.replace('__prefix__', '2')] = hidden.value() or ''
        edit_data['windows-2-start_date'] = (window_end + timedelta(days=14)).isoformat()
        edit_data['windows-2-end_date'] = (window_end + timedelta(days=18)).isoformat()

        response = self.client.post(reverse('item_edit', args=[item.pk]), edit_data)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.photos.count(), 2)
        self.assertEqual(
            item.photos.filter(is_primary=True).values_list('pk', flat=True).get(),
            next_primary.pk,
        )
        self.assertEqual(item.windows.count(), 3)

        neighbor = self.create_user('neighbor@example.com', self.community)
        neighbor_item = self.create_item(
            'Neighbor listing', neighbor, self.category, window_start, window_end,
        )
        other_community = self.create_community('Community Two')
        distant_owner = self.create_user('distant@example.com', other_community)
        distant_item = self.create_item(
            'Distant listing', distant_owner, self.category, window_start, window_end,
        )

        response = self.client.get(reverse('browse_items'), {
            'category': str(self.category.pk),
            'date': (today + timedelta(days=2)).isoformat(),
        })
        self.assertContains(response, neighbor_item.name)
        self.assertNotContains(
            response,
            f'href="{reverse("item_detail", args=[item.pk])}"',
        )
        self.assertNotContains(response, distant_item.name)
        self.assertEqual(
            self.client.get(reverse('item_detail', args=[distant_item.pk])).status_code,
            404,
        )

        self.client.post(reverse('item_toggle', args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.status, 'unlisted')
        self.client.post(reverse('item_toggle', args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.status, 'available')
