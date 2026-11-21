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

from .forms import (
    AvailabilityWindowForm,
    BorrowRequestForm,
    ItemForm,
    WishlistForm,
    WindowFormSet,
)
from .models import (
    AvailabilityWindow,
    BorrowRequest,
    Category,
    HandoffConfirmation,
    Item,
    ItemPhoto,
    Notification,
    Rating,
    Wishlist,
)


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

    def test_owner_cannot_unlist_item_with_approved_request(self):
        approved = self.make_request(status='approved')
        self.assertEqual(approved.status, 'approved')
        self.client.force_login(self.owner)

        response = self.client.post(reverse('item_toggle', args=[self.item.pk]))

        self.assertRedirects(response, reverse('my_items'))
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'available')

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


class HandoffConfirmationTests(TestCase):
    def setUp(self):
        from accounts.models import Community

        today = timezone.localdate()
        self.community = Community.objects.create(
            name='Handoff Community',
            barangay='Handoff Community',
            city='Test City',
        )
        self.owner = get_user_model().objects.create_user(
            email='handoff-owner@example.com',
            password='test-password',
            community=self.community,
            user_type='lender',
        )
        self.borrower = get_user_model().objects.create_user(
            email='handoff-borrower@example.com',
            password='test-password',
            community=self.community,
            user_type='borrower',
        )
        self.category = Category.objects.create(name='Handoff tools')
        self.item = Item.objects.create(
            owner=self.owner,
            category=self.category,
            name='Handoff item',
            description='A test item',
        )
        self.request = BorrowRequest.objects.create(
            item=self.item,
            borrower=self.borrower,
            start_date=today,
            end_date=today + timedelta(days=2),
            status='approved',
        )

    def test_pickup_requires_both_confirmations_then_marks_borrowed(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('handoff_confirm', args=[self.request.pk, 'pickup']))
        self.request.refresh_from_db()
        self.item.refresh_from_db()
        pickup = HandoffConfirmation.objects.get(
            request=self.request,
            handoff_type='pickup',
        )
        self.assertIsNotNone(pickup.lender_confirmed_at)
        self.assertIsNone(pickup.borrower_confirmed_at)
        self.assertEqual(pickup.completed_at, None)
        self.assertEqual(self.request.status, 'approved')
        self.assertEqual(self.item.status, 'available')

        self.client.force_login(self.borrower)
        self.client.post(reverse('handoff_confirm', args=[self.request.pk, 'pickup']))
        self.request.refresh_from_db()
        self.item.refresh_from_db()
        pickup.refresh_from_db()
        self.assertIsNotNone(pickup.completed_at)
        self.assertEqual(self.request.status, 'borrowed')
        self.assertEqual(self.item.status, 'on_loan')

    def test_return_requires_both_confirmations_then_marks_completed(self):
        self.request.status = 'borrowed'
        self.request.save(update_fields=['status'])
        self.item.status = 'on_loan'
        self.item.save(update_fields=['status'])

        self.client.force_login(self.owner)
        self.client.post(reverse('handoff_confirm', args=[self.request.pk, 'return']))
        self.request.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.request.status, 'borrowed')
        self.assertEqual(self.item.status, 'on_loan')

        self.client.force_login(self.borrower)
        self.client.post(reverse('handoff_confirm', args=[self.request.pk, 'return']))
        self.request.refresh_from_db()
        self.item.refresh_from_db()
        return_confirmation = HandoffConfirmation.objects.get(
            request=self.request,
            handoff_type='return',
        )
        self.assertIsNotNone(return_confirmation.completed_at)
        self.assertEqual(self.request.status, 'completed')
        self.assertEqual(self.item.status, 'available')

    def test_only_request_owner_or_borrower_can_confirm(self):
        outsider = get_user_model().objects.create_user(
            email='handoff-outsider@example.com',
            password='test-password',
            community=self.community,
            user_type='both',
        )
        self.client.force_login(outsider)
        response = self.client.post(
            reverse('handoff_confirm', args=[self.request.pk, 'pickup']),
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(HandoffConfirmation.objects.filter(request=self.request).exists())

    def test_borrowed_request_after_end_date_is_marked_overdue(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.request.status = 'borrowed'
        self.request.start_date = yesterday
        self.request.end_date = yesterday
        self.request.save(update_fields=['status', 'start_date', 'end_date'])

        self.client.force_login(self.borrower)
        response = self.client.get(reverse('my_requests'))

        self.assertEqual(response.status_code, 200)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, 'overdue')


class RatingTests(TestCase):
    def setUp(self):
        from accounts.models import Community

        today = timezone.localdate()
        self.community = Community.objects.create(
            name='Rating Community',
            barangay='Rating Community',
            city='Test City',
        )
        self.owner = get_user_model().objects.create_user(
            email='rating-owner@example.com',
            password='test-password',
            community=self.community,
            user_type='lender',
        )
        self.borrower = get_user_model().objects.create_user(
            email='rating-borrower@example.com',
            password='test-password',
            community=self.community,
            user_type='borrower',
        )
        self.category = Category.objects.create(name='Rating tools')
        self.item = Item.objects.create(
            owner=self.owner,
            category=self.category,
            name='Rated item',
            description='A test item',
        )
        self.request = BorrowRequest.objects.create(
            item=self.item,
            borrower=self.borrower,
            start_date=today - timedelta(days=3),
            end_date=today - timedelta(days=1),
            status='completed',
        )

    def test_only_request_participants_can_submit_one_rating(self):
        outsider = get_user_model().objects.create_user(
            email='rating-outsider@example.com',
            password='test-password',
            community=self.community,
            user_type='both',
        )
        self.client.force_login(outsider)
        response = self.client.post(
            reverse('rating_create', args=[self.request.pk]),
            {'score': '5', 'review_text': 'Excellent'},
        )
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.borrower)
        response = self.client.post(
            reverse('rating_create', args=[self.request.pk]),
            {'score': '5', 'review_text': 'Great lender'},
        )
        self.assertRedirects(response, reverse('my_requests'))
        rating = Rating.objects.get(request=self.request, rater=self.borrower)
        self.assertEqual(rating.ratee, self.owner)
        self.owner.refresh_from_db()
        self.assertEqual(str(self.owner.avg_rating), '5.00')
        self.assertEqual(self.owner.rating_count, 1)

        response = self.client.post(
            reverse('rating_create', args=[self.request.pk]),
            {'score': '1', 'review_text': 'Duplicate'},
        )
        self.assertRedirects(response, reverse('my_requests'))
        self.assertEqual(
            Rating.objects.filter(request=self.request, rater=self.borrower).count(),
            1,
        )

    def test_owner_and_borrower_can_each_rate_the_other(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse('rating_create', args=[self.request.pk]),
            {'score': '2', 'review_text': 'Delayed'},
        )
        self.client.force_login(self.borrower)
        self.client.post(
            reverse('rating_create', args=[self.request.pk]),
            {'score': '5', 'review_text': 'Helpful'},
        )

        self.owner.refresh_from_db()
        self.borrower.refresh_from_db()
        self.assertEqual(str(self.owner.avg_rating), '5.00')
        self.assertEqual(str(self.borrower.avg_rating), '2.00')
        self.assertEqual(self.owner.rating_count, 1)
        self.assertEqual(self.borrower.rating_count, 1)
        self.assertEqual(Rating.objects.filter(request=self.request).count(), 2)

    def test_rating_requires_completed_request_and_valid_score(self):
        self.request.status = 'borrowed'
        self.request.save(update_fields=['status'])
        self.client.force_login(self.borrower)
        response = self.client.post(
            reverse('rating_create', args=[self.request.pk]),
            {'score': '5', 'review_text': 'Too early'},
        )
        self.assertRedirects(response, reverse('my_requests'))
        self.assertFalse(Rating.objects.filter(request=self.request).exists())

        self.request.status = 'completed'
        self.request.save(update_fields=['status'])
        response = self.client.post(
            reverse('rating_create', args=[self.request.pk]),
            {'score': '6', 'review_text': 'Invalid'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice.')

    def test_low_average_after_five_ratings_flags_account(self):
        for index in range(5):
            request_record = BorrowRequest.objects.create(
                item=self.item,
                borrower=self.borrower,
                start_date=self.request.start_date - timedelta(days=index + 1),
                end_date=self.request.start_date - timedelta(days=index),
                status='completed',
            )
            Rating.objects.create(
                request=request_record,
                rater=self.borrower,
                ratee=self.owner,
                score=2,
            )

        self.owner.refresh_from_db()
        self.assertEqual(str(self.owner.avg_rating), '2.00')
        self.assertEqual(self.owner.rating_count, 5)
        self.assertEqual(self.owner.account_status, 'flagged')


class NotificationTests(TestCase):
    def setUp(self):
        from accounts.models import Community

        today = timezone.localdate()
        self.community = Community.objects.create(
            name='Notification Community',
            barangay='Notification Community',
            city='Test City',
        )
        self.owner = get_user_model().objects.create_user(
            email='notify-owner@example.com',
            password='test-password',
            community=self.community,
            user_type='lender',
        )
        self.borrower = get_user_model().objects.create_user(
            email='notify-borrower@example.com',
            password='test-password',
            community=self.community,
            user_type='borrower',
        )
        self.category = Category.objects.create(name='Notification tools')
        self.item = Item.objects.create(
            owner=self.owner,
            category=self.category,
            name='Notification item',
            description='A test item',
        )
        AvailabilityWindow.objects.create(
            item=self.item,
            start_date=today,
            end_date=today + timedelta(days=7),
        )
        self.request = BorrowRequest.objects.create(
            item=self.item,
            borrower=self.borrower,
            start_date=today,
            end_date=today + timedelta(days=2),
            status='pending',
        )

    def test_request_submission_creates_owner_notification(self):
        Notification.objects.create(
            user=self.owner,
            request=self.request,
            notif_type='request_received',
            message=f'{self.borrower.email} requested "{self.item.name}".',
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse('notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'requested')

    def test_unread_count_and_mark_read(self):
        notification = Notification.objects.create(
            user=self.owner,
            request=self.request,
            notif_type='request_received',
            message=f'New request for "{self.item.name}".',
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('notification_mark_read', args=[notification.pk]),
        )
        self.assertRedirects(response, reverse('notifications'))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_due_reminder_and_overdue_notifications(self):
        today = timezone.localdate()
        self.request.status = 'borrowed'
        self.request.end_date = today + timedelta(days=1)
        self.request.save(update_fields=['status', 'end_date'])

        count = Notification.send_due_reminders()
        self.assertEqual(count, 1)
        self.assertTrue(Notification.objects.filter(
            user=self.borrower,
            request=self.request,
            notif_type='due_reminder',
        ).exists())

        self.request.end_date = today - timedelta(days=1)
        self.request.start_date = today - timedelta(days=2)
        self.request.save(update_fields=['status', 'end_date', 'start_date'])
        count = BorrowRequest.mark_overdue()
        self.assertEqual(count, 1)
        self.assertTrue(Notification.objects.filter(
            user=self.borrower,
            request=self.request,
            notif_type='overdue',
        ).exists())

    def test_user_cannot_read_another_users_notification(self):
        notification = Notification.objects.create(
            user=self.owner,
            request=self.request,
            notif_type='request_received',
            message='Private notification.',
        )
        self.client.force_login(self.borrower)
        response = self.client.post(
            reverse('notification_mark_read', args=[notification.pk]),
        )
        self.assertEqual(response.status_code, 404)


class WishlistTests(TestCase):
    def setUp(self):
        from accounts.models import Community

        self.community = Community.objects.create(
            name='Wishlist Community',
            barangay='Wishlist Community',
            city='Test City',
        )
        self.owner = get_user_model().objects.create_user(
            email='wishlist-owner@example.com',
            password='test-password',
            community=self.community,
            user_type='lender',
        )
        self.borrower = get_user_model().objects.create_user(
            email='wishlist-borrower@example.com',
            password='test-password',
            community=self.community,
            user_type='borrower',
        )
        self.category = Category.objects.create(name='Wishlist tools')

    def test_category_or_keyword_required_and_active_limit(self):
        form = WishlistForm(data={'category': '', 'keyword': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('Choose a category or enter a keyword.', str(form.errors))

        self.client.force_login(self.borrower)
        for index in range(10):
            Wishlist.objects.create(
                user=self.borrower,
                keyword=f'tool-{index}',
                is_active=True,
            )
        form = WishlistForm(
            data={'category': str(self.category.pk), 'keyword': ''},
            user=self.borrower,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('at most 10 active wishlist entries', str(form.errors))

    def test_new_item_matches_category_or_keyword_and_same_community(self):
        from accounts.models import Community

        wishlist = Wishlist.objects.create(
            user=self.borrower,
            category=self.category,
            keyword='drill',
            is_active=True,
        )
        item = Item.objects.create(
            owner=self.owner,
            category=self.category,
            name='Cordless Drill',
            description='For household projects',
        )
        Notification.match_wishlist(item)

        self.assertTrue(Notification.objects.filter(
            user=self.borrower,
            notif_type='wishlist_match',
            request=None,
        ).exists())

        outsider = get_user_model().objects.create_user(
            email='wishlist-outsider@example.com',
            password='test-password',
            community=Community.objects.create(
                name='Other Wishlist Community',
                barangay='Other',
                city='Test City',
            ),
            user_type='borrower',
        )
        outsider_wishlist = Wishlist.objects.create(
            user=outsider,
            category=self.category,
            keyword='drill',
            is_active=True,
        )
        outsider_count = Notification.objects.count()
        Notification.match_wishlist(item)
        self.assertEqual(Notification.objects.count(), outsider_count)
        self.assertFalse(Notification.objects.filter(
            user=outsider,
            notif_type='wishlist_match',
        ).exists())

    def test_wishlist_toggle_and_delete(self):
        self.client.force_login(self.borrower)
        response = self.client.get(reverse('wishlists'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('wishlists'), {
            'category': self.category.pk,
            'keyword': 'hand saw',
        })
        self.assertRedirects(response, reverse('wishlists'))
        self.assertTrue(Wishlist.objects.filter(
            user=self.borrower,
            category=self.category,
            keyword='hand saw',
        ).exists())

        entry = Wishlist.objects.create(
            user=self.borrower,
            keyword='ladder',
            is_active=True,
        )

        response = self.client.post(reverse('wishlist_toggle', args=[entry.pk]))
        self.assertRedirects(response, reverse('wishlists'))
        entry.refresh_from_db()
        self.assertFalse(entry.is_active)

        response = self.client.post(reverse('wishlist_delete', args=[entry.pk]))
        self.assertRedirects(response, reverse('wishlists'))
        self.assertFalse(Wishlist.objects.filter(pk=entry.pk).exists())
