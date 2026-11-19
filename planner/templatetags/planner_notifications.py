"""Combine queued feedback and current-page validation in one notification stack."""
from django import template
from django.contrib.messages import ERROR
from django.contrib.messages.storage.base import Message
from django.core.exceptions import NON_FIELD_ERRORS
from django.forms import BaseForm
from django.forms.formsets import BaseFormSet

register = template.Library()


def form_error_lines(form, prefix=''):
    if not form.is_bound:
        return []
    lines = []
    for name, errors in form.errors.items():
        label = '' if name == NON_FIELD_ERRORS else str(form.fields[name].label or name.replace('_', ' ').capitalize())
        heading = f'{prefix}{label}: ' if label else prefix
        lines.extend(f'{heading}{error}' for error in errors)
    return lines


@register.simple_tag(takes_context=True)
def project_notifications(context):
    # Validation errors belong to this response, not the persisted message queue.
    # This prevents stale errors reappearing after the next successful request.
    notices = list(context.get('messages', []))
    seen = set()
    for value in context.flatten().values():
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, BaseForm):
            lines = form_error_lines(value)
        elif isinstance(value, BaseFormSet) and value.is_bound:
            lines = [str(error) for error in value.non_form_errors()]
            for number, form in enumerate(value.forms, start=1):
                lines.extend(form_error_lines(form, f'Item {number} — '))
        else:
            continue
        if lines:
            notices.append(Message(ERROR, '\n'.join(lines)))
    for error in context.get('notification_errors', []):
        notices.append(Message(ERROR, str(error)))
    return notices
