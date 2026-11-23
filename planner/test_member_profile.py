from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Member


class MemberProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='profile@example.com', email='profile@example.com')
        self.member = Member.objects.create(user=self.user, first_name='A', last_name='B', email='profile@example.com')
        self.url = reverse('member_profile')
        self.client.force_login(self.user)

    def test_profile_is_linked_and_prefilled(self):
        self.assertContains(self.client.get(reverse('member_portal')), self.url)
        response = self.client.get(self.url)
        self.assertEqual(response.context['form']['first_name'].value(), 'A')
        self.assertTrue(response.context['form'].fields['email'].disabled)
        self.assertContains(response, reverse('password_reset'))
        self.assertContains(response, 'Reset password')

    def test_updates_only_own_name_and_phone_and_syncs_login_name(self):
        other = Member.objects.create(first_name='Other', last_name='Member', email='other@example.com')
        response = self.client.post(self.url, {
            'first_name': 'Updated', 'last_name': 'Name', 'phone': '+441234567890',
            'email': 'attacker@example.com', 'status': 'active', 'id': other.pk,
        })
        self.assertRedirects(response, self.url)
        self.member.refresh_from_db(); self.user.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(self.member.first_name, 'Updated')
        self.assertEqual(self.member.phone, '+441234567890')
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.member.email, 'profile@example.com')
        self.assertEqual(self.user.username, 'profile@example.com')
        self.assertEqual(self.member.status, Member.Status.PENDING)
        self.assertEqual(other.first_name, 'Other')

    def test_invalid_form_keeps_saved_profile(self):
        response = self.client.post(self.url, {'first_name': '', 'last_name': 'B'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('first_name', response.context['form'].errors)
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, 'A')

    def test_address_can_be_saved_reopened_and_cleared(self):
        address = '12 High Street\nLondon\nE1 1AA\nUnited Kingdom'
        data = {'first_name': 'A', 'last_name': 'B', 'address': address}
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.member.refresh_from_db()
        self.assertEqual(self.member.address, address)
        self.assertEqual(self.client.get(self.url).context['form']['address'].value(), address)
        data['address'] = ''
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.member.refresh_from_db()
        self.assertEqual(self.member.address, '')

    def test_login_required_and_staff_without_profile_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        staff = get_user_model().objects.create_user(username='staff-profile', is_staff=True)
        self.client.force_login(staff)
        self.assertRedirects(self.client.get(self.url), reverse('member_portal'))
