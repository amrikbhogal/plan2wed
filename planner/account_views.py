from django.conf import settings
from django.contrib.auth.views import PasswordResetView


class MemberPasswordResetView(PasswordResetView):
    def form_valid(self, form):
        # Use the configured public origin rather than a submitted Host header.
        self.extra_email_context = {'reset_base_url': settings.PLAN2WED_SITE_URL}
        return super().form_valid(form)
