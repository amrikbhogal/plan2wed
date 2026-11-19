from django.conf import settings
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView, PasswordResetConfirmView


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
