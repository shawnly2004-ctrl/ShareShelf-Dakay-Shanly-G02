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

from .forms import AvailabilityWindowForm, BorrowRequestForm, ItemForm, WindowFormSet
from .models import AvailabilityWindow, BorrowRequest, Category, Item, ItemPhoto


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


class BorrowRequestTests(TestCase):
    def setUp(self):
        from accounts.models import Community

        today = timezone.localdate()
        self.community = Community.objects.create(
            name='Request Community',
            barangay='Request Community',
            city='Test City',
        )
        self.owner = self.create_user('request-owner@example.com', 'lender')
        self.borrower = self.create_user('request-borrower@example.com', 'both')
        self.category = Category.objects.create(name='Request tools')
        self.item = Item.objects.create(
            owner=self.owner,
            category=self.category,
            name='Requestable item',
            description='A test item',
        )
        self.windows = [
            (today + timedelta(days=1), today + timedelta(days=5)),
            (today + timedelta(days=8), today + timedelta(days=12)),
            (today + timedelta(days=20), today + timedelta(days=30)),
        ]
        for start, end in self.windows:
            AvailabilityWindow.objects.create(item=self.item, start_date=start, end_date=end)

    def create_user(self, email, user_type, community=None):
        return get_user_model().objects.create_user(
            email=email,
            password='test-password',
            user_type=user_type,
            community=community or self.community,
        )

    def make_request(self, item=None, borrower=None, start=None, end=None, status='pending', **kwargs):
        return BorrowRequest.objects.create(
            item=item or self.item,
            borrower=borrower or self.borrower,
            start_date=start or self.windows[0][0],
            end_date=end or self.windows[0][1],
            status=status,
            **kwargs,
        )

    def form_for(self, start, end, borrower=None, item=None):
        return BorrowRequestForm(
            data={
                'start_date': start.isoformat(),
                'end_date': end.isoformat(),
                'message': '',
            },
            item=item or self.item,
            borrower=borrower or self.borrower,
        )

    def assert_non_field_error(self, form, expected):
        self.assertFalse(form.is_valid())
        errors = [error.message for error in form.non_field_errors().as_data()]
        self.assertIn(expected, errors)

    def test_request_dates_must_fit_one_window_and_be_seven_days_or_less(self):
        gap_form = self.form_for(self.windows[0][1] + timedelta(days=1),
                                 self.windows[1][0] - timedelta(days=1))
        self.assert_non_field_error(
            gap_form,
            "Your dates must fall entirely inside one of the item's availability windows.",
        )

        spanning_form = self.form_for(
            self.windows[0][1] - timedelta(days=1),
            self.windows[1][0] + timedelta(days=1),
        )
        self.assert_non_field_error(
            spanning_form,
            "Your dates must fall entirely inside one of the item's availability windows.",
        )

        too_long_form = self.form_for(
            self.windows[2][0],
            self.windows[2][0] + timedelta(days=8),
        )
        self.assert_non_field_error(too_long_form, "A loan can last at most 7 days.")

    def test_request_form_rejects_past_and_reversed_dates(self):
        today = timezone.localdate()
        past_form = self.form_for(today - timedelta(days=1), today)
        self.assertFalse(past_form.is_valid())
        self.assertIn("Start date can't be in the past.",
                      past_form.errors.as_data()['start_date'][0].message)

        reversed_form = self.form_for(self.windows[0][0] + timedelta(days=2),
                                      self.windows[0][0])
        self.assertFalse(reversed_form.is_valid())
        self.assertIn("End date can't be before the start date.",
                      reversed_form.errors.as_data()['end_date'][0].message)

    def test_duplicate_pending_blocking_overlap_and_active_request_limit(self):
        valid_start = self.windows[0][0]
        valid_end = valid_start + timedelta(days=1)
        self.make_request(start=valid_start, end=valid_end)
        duplicate = self.form_for(valid_start, valid_end)
        self.assert_non_field_error(duplicate, "You already have a pending request for this item.")

        BorrowRequest.objects.filter(item=self.item).delete()
        self.make_request(start=valid_start, end=valid_end, status='approved')
        overlap = self.form_for(valid_start + timedelta(days=1), valid_end + timedelta(days=1))
        self.assert_non_field_error(
            overlap,
            "Those dates overlap with an approved loan. Pick other dates.",
        )

        BorrowRequest.objects.filter(item=self.item).delete()
        for index in range(3):
            other_item = Item.objects.create(
                owner=self.owner,
                category=self.category,
                name=f'Other item {index}',
                description='A test item',
            )
            self.make_request(item=other_item, status='pending')
        at_limit = self.form_for(valid_start, valid_end)
        self.assert_non_field_error(
            at_limit,
            "You can have at most 3 active requests at a time.",
        )

    def test_create_approve_and_decline_overlapping_pending_request(self):
        self.client.force_login(self.borrower)
        start = self.windows[0][0]
        end = start + timedelta(days=2)
        response = self.client.post(reverse('request_create', args=[self.item.pk]), {
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'message': 'For a home project',
        })
        self.assertRedirects(response, reverse('my_requests'))
        approved_request = BorrowRequest.objects.get(item=self.item, borrower=self.borrower)
        self.assertEqual(approved_request.status, 'pending')
        self.assertGreater(approved_request.expires_at, timezone.now())
        self.assertLessEqual(approved_request.expires_at, timezone.now() + timedelta(days=3))

        other_borrower = self.create_user('other-borrower@example.com', 'borrower')
        overlapping = self.make_request(
            borrower=other_borrower,
            start=start + timedelta(days=1),
            end=end,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('request_respond', args=[approved_request.pk]),
            {'action': 'approve'},
        )
        self.assertRedirects(response, reverse('incoming_requests'))
        approved_request.refresh_from_db()
        overlapping.refresh_from_db()
        self.assertEqual(approved_request.status, 'approved')
        self.assertIsNotNone(approved_request.decided_at)
        self.assertEqual(overlapping.status, 'declined')
        self.assertIsNotNone(overlapping.decided_at)

    def test_cancellation_expiry_and_delete_blocking(self):
        pending = self.make_request()
        self.client.force_login(self.borrower)
        response = self.client.post(reverse('request_cancel', args=[pending.pk]))
        self.assertRedirects(response, reverse('my_requests'))
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'cancelled')

        approved = self.make_request(status='approved')
        self.client.post(reverse('request_cancel', args=[approved.pk]))
        approved.refresh_from_db()
        self.assertEqual(approved.status, 'cancelled')

        stale = self.make_request()
        BorrowRequest.objects.filter(pk=stale.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.client.get(reverse('my_requests'))
        stale.refresh_from_db()
        self.assertEqual(stale.status, 'expired')

        blocking = self.make_request(status='approved')
        self.client.force_login(self.owner)
        response = self.client.post(reverse('item_delete', args=[self.item.pk]))
        self.assertRedirects(response, reverse('my_items'))
        self.assertTrue(Item.objects.filter(pk=self.item.pk).exists())
        blocking.refresh_from_db()
        self.assertEqual(blocking.status, 'approved')

    def test_request_access_rules_and_owner_only_responses(self):
        self.client.force_login(self.borrower)
        own_item = self.item
        own_item.owner = self.borrower
        own_item.save(update_fields=['owner'])
        response = self.client.get(reverse('request_create', args=[own_item.pk]))
        self.assertRedirects(response, reverse('item_detail', args=[own_item.pk]))

        self.item.owner = self.owner
        self.item.save(update_fields=['owner'])
        lender = self.create_user('lender-only@example.com', 'lender')
        self.client.force_login(lender)
        response = self.client.get(reverse('request_create', args=[self.item.pk]))
        self.assertRedirects(response, reverse('profile_edit'))

        other_community = self._create_community('Other Community')
        outsider = self.create_user('outsider@example.com', 'borrower', other_community)
        self.client.force_login(outsider)
        response = self.client.get(reverse('request_create', args=[self.item.pk]))
        self.assertEqual(response.status_code, 404)

        request_record = self.make_request()
        self.client.force_login(self.borrower)
        response = self.client.get(reverse('request_respond', args=[request_record.pk]))
        self.assertEqual(response.status_code, 405)
        response = self.client.post(
            reverse('request_respond', args=[request_record.pk]),
            {'action': 'approve'},
        )
        self.assertEqual(response.status_code, 404)

    def _create_community(self, name):
        from accounts.models import Community

        return Community.objects.create(name=name, barangay=name, city='Test City')
