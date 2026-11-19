from django.conf import settings
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView, PasswordResetConfirmView
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .email_verification import matches_verification, pending_verifications, request_email_verification, verification_payload
from .forms import VerificationResendForm
from .models import Member


@never_cache
@require_http_methods(['GET', 'POST'])
def verify_email(request, token):
    payload = verification_payload(token)
    valid_link = False
    if payload:
        with transaction.atomic():
            member = pending_verifications().select_for_update(of=('self',)).select_related('user').filter(pk=payload['member_id']).first()
            if member is not None:
                member.user = get_user_model().objects.select_for_update().get(pk=member.user_id)
                valid_link = not (member.user.is_active or member.user.is_staff or member.user.is_superuser) and matches_verification(member, payload)
                if valid_link and request.method == 'POST':
                    member.status = Member.Status.ACTIVE
                    member.email_verified_at = timezone.now()
                    member.save(update_fields=['status', 'email_verified_at'])
                    member.user.is_active = True
                    member.user.save(update_fields=['is_active'])
                    messages.success(request, 'Your email is verified and your membership is active. You can now sign in.')
                    return redirect('login')
    context = {'valid_link': valid_link}
    if not valid_link:
        context['notification_errors'] = ['This verification link has expired, has already been used, or is invalid. Request a new link, or sign in if you have already verified your email.']
    response = render(request, 'planner/verify_email.html', context)
    # HTTPS CSRF checks need a same-site Referer when an email webview omits
    # Origin. Keep the verification token out of cross-site referrers.
    response['Referrer-Policy'] = 'same-origin'
    return response


@never_cache
@require_http_methods(['GET', 'POST'])
def resend_verification(request):
    form = VerificationResendForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        member_id = pending_verifications().filter(email__iexact=form.cleaned_data['email']).values_list('pk', flat=True).first()
        if member_id is not None:
            request_email_verification(member_id)
        messages.info(request, 'If that email belongs to an unverified registration, we’ve sent a verification link. Check your spam folder too. Please allow a minute before requesting another.')
        return redirect('resend_verification')
    return render(request, 'planner/resend_verification.html', {'form': form})


class MemberAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Your email or password is incorrect, or your membership is not active yet.',
        'inactive': 'Your email or password is incorrect, or your membership is not active yet.',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Email address'


class MemberLoginView(LoginView):
    authentication_form = MemberAuthenticationForm

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'You’re signed in. Welcome back to Plan2Wed.')
        return response


class MemberLogoutView(LogoutView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.success(request, 'You’ve been signed out.')
        return response


class MemberPasswordResetView(PasswordResetView):
    def form_valid(self, form):
        # Use the configured public origin rather than a submitted Host header.
        self.extra_email_context = {'reset_base_url': settings.PLAN2WED_SITE_URL}
        response = super().form_valid(form)
        messages.info(self.request, 'If an active account matches that address, we’ve sent a password reset link. Check your spam folder too.')
        return response


class MemberPasswordResetConfirmView(PasswordResetConfirmView):
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Your password has been updated. You can now sign in.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not context.get('validlink'):
            context['notification_errors'] = ['The reset link has expired, has already been used, or is invalid. Request a new link.']
        return context
