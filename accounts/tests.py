from datetime import timedelta

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import get_resolver, include, path, reverse
from django.utils import timezone

from config.views import custom_500_view
from .forms import ProfileForm, RegisterForm
from .validators import LetterAndNumberValidator


def raise_test_server_error(request):
    raise RuntimeError('Test-only server error')


class CustomErrorTestUrlConf:
    urlpatterns = [
        path('', include('accounts.urls')),
        path('trigger-test-server-error/', raise_test_server_error),
    ]
    handler500 = custom_500_view


@override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'])
class Custom404Tests(SimpleTestCase):
    def test_project_urlconf_registers_custom_500_handler(self):
        self.assertIs(
            get_resolver('config.urls').resolve_error_handler('500'),
            custom_500_view,
        )

    def test_unknown_url_uses_custom_404_template(self):
        response = self.client.get('/missing-page-for-404-test/')

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, '404.html')
        self.assertContains(response, 'Page not found', status_code=404)

    @override_settings(ROOT_URLCONF=CustomErrorTestUrlConf)
    def test_server_error_uses_custom_500_template_without_exposing_exception(self):
        self.client.raise_request_exception = False

        response = self.client.get('/trigger-test-server-error/')

        self.assertEqual(response.status_code, 500)
        self.assertTemplateUsed(response, '500.html')
        self.assertContains(response, 'Something went wrong', status_code=500)
        self.assertNotContains(response, 'Test-only server error', status_code=500)


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


class SDDAccountFeatureTests(TestCase):
    def setUp(self):
        from .models import Community

        self.community = Community.objects.create(
            name='Account Test Community',
            barangay='Test Barangay',
            city='Cebu City',
        )

    def register(self, email='member@example.com', password='ShareShelf2026'):
        return self.client.post(reverse('register'), {
            'first_name': 'Test',
            'last_name': 'Member',
            'email': email,
            'contact_number': '09170000000',
            'community': str(self.community.pk),
            'user_type': 'both',
            'address_detail': 'Purok 1',
            'latitude': '10.315699',
            'longitude': '123.885436',
            'language_pref': 'en',
            'password1': password,
            'password2': password,
        })

    def test_f01_register_duplicate_email_and_password_rules(self):
        response = self.register()
        self.assertRedirects(response, reverse('login'))
        user = get_user_model().objects.get(email='member@example.com')
        self.assertEqual(user.role, 'member')
        self.assertEqual(user.community, self.community)
        self.assertNotEqual(user.password, 'abc12345')

        response = self.register(email='member@example.com', password='ShareShelf2027')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'account with this email already exists')

        response = self.register(email='letters@example.com', password='ShareShelfLetters')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'letter')

    def test_f02_login_lockout_and_success_reset(self):
        user = get_user_model().objects.create_user(
            email='lockout@example.com',
            password='abc12345',
            community=self.community,
            user_type='both',
        )
        for attempt in range(5):
            response = self.client.post(reverse('login'), {
                'username': 'lockout@example.com',
                'password': 'wrongpassword',
            })
        user.refresh_from_db()
        self.assertEqual(user.failed_login_count, 0)
        self.assertIsNotNone(user.locked_until)
        self.assertGreater(user.locked_until, timezone.now())

        response = self.client.post(reverse('login'), {
            'username': 'lockout@example.com',
            'password': 'abc12345',
        })
        self.assertContains(response, 'temporarily locked')
        self.assertEqual(self.client.session.get('_auth_user_id'), None)

        get_user_model().objects.filter(pk=user.pk).update(
            locked_until=timezone.now() - timedelta(minutes=1),
            failed_login_count=0,
        )
        response = self.client.post(reverse('login'), {
            'username': 'lockout@example.com',
            'password': 'abc12345',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))
        user.refresh_from_db()
        self.assertEqual(user.failed_login_count, 0)
        self.assertIsNone(user.locked_until)

    def test_f03_f04_profile_language_and_logout(self):
        user = get_user_model().objects.create_user(
            email='profile@example.com',
            password='abc12345',
            community=self.community,
            user_type='both',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('member_dashboard'))

        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('profile_edit'), {
            'first_name': 'Updated',
            'last_name': 'Member',
            'email': 'profile@example.com',
            'contact_number': '09178888888',
            'community': str(self.community.pk),
            'user_type': 'borrower',
            'address_detail': 'Purok 2',
            'latitude': '10.300000',
            'longitude': '123.900000',
            'language_pref': 'fil',
        })
        self.assertRedirects(response, reverse('profile'))
        user.refresh_from_db()
        self.assertEqual(user.language_pref, 'fil')
        self.assertEqual(user.address_detail, 'Purok 2')
        self.assertEqual(user.contact_number, '09178888888')

        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'Filipino')

        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_br06_every_member_has_one_community_and_br30_language_enum(self):
        user = get_user_model().objects.create_user(
            email='community@example.com',
            password='abc12345',
            community=self.community,
            user_type='borrower',
            language_pref='fil',
        )
        self.assertEqual(user.community_id, self.community.pk)
        self.assertIn(user.language_pref, ('en', 'fil'))


    def test_contact_number_required_and_digits_only_in_registration_and_profile(self):
        registration_data = {
            'first_name': 'Test',
            'last_name': 'Member',
            'email': 'new-member@example.com',
            'community': str(self.community.pk),
            'user_type': 'both',
            'contact_number': '',
            'language_pref': 'en',
            'password1': 'ShareShelf2026',
            'password2': 'ShareShelf2026',
        }
        form = RegisterForm(data=registration_data)
        self.assertFalse(form.is_valid())
        self.assertIn('contact_number', form.errors)

        registration_data['contact_number'] = '09AB123'
        form = RegisterForm(data=registration_data)
        self.assertFalse(form.is_valid())
        self.assertIn('digits only', str(form.errors['contact_number']))

        registration_data['contact_number'] = '09171234567'
        form = RegisterForm(data=registration_data)
        self.assertTrue(form.is_valid(), form.errors)

        user = get_user_model().objects.create_user(
            email='profile-contact@example.com',
            password='ShareShelf2026',
            first_name='Contact',
            last_name='Tester',
            community=self.community,
            contact_number='09170000000',
        )
        profile_data = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'community': str(self.community.pk),
            'user_type': user.user_type,
            'contact_number': '',
            'address_detail': '',
            'latitude': '',
            'longitude': '',
            'language_pref': 'en',
        }
        form = ProfileForm(data=profile_data, instance=user)
        self.assertFalse(form.is_valid())
        self.assertIn('contact_number', form.errors)

        profile_data['contact_number'] = 'phone123'
        form = ProfileForm(data=profile_data, instance=user)
        self.assertFalse(form.is_valid())
        self.assertIn('digits only', str(form.errors['contact_number']))

        profile_data['contact_number'] = '09178888888'
        form = ProfileForm(data=profile_data, instance=user)
        self.assertTrue(form.is_valid(), form.errors)


class ManageUsersQueryTests(TestCase):
    def setUp(self):
        from .models import Community

        self.community = Community.objects.create(
            name='Manage Users Community',
            barangay='Manage Users Barangay',
            city='Cebu City',
        )
        admin = get_user_model().objects.create_user(
            email='manage-users-admin@example.com',
            password='test-password',
            role='admin',
            community=self.community,
        )
        for index in range(3):
            get_user_model().objects.create_user(
                email=f'manage-users-{index}@example.com',
                password='test-password',
                community=self.community,
            )
        self.client.force_login(admin)

    def test_manage_users_joins_community_for_barangay_column(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('manage_users'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manage Users Barangay')
        self.assertTrue(any(
            'JOIN' in query['sql'].upper()
            and 'ACCOUNTS_COMMUNITY' in query['sql'].upper()
            for query in queries.captured_queries
        ))
