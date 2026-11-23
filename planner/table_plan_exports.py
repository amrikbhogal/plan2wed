"""Private seating-plan previews, PDF downloads and explicitly requested emails."""
import io
import logging
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from .models import WeddingEvent, WeddingGuest

logger = logging.getLogger(__name__)
for name, filename in [('PlanRegular', 'Vera.ttf'), ('PlanBold', 'VeraBd.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(Path(reportlab.__file__).parent / 'fonts' / filename)))


class TablePlanEmailForm(forms.Form):
    recipient = forms.EmailField(label='Email PDF to', max_length=254,
                                 widget=forms.EmailInput(attrs={'placeholder': 'recipient@example.com'}))


def plan_sections(event):
    eligible = event.guests.filter(budget_id=event.budget_id).exclude(rsvp_status=WeddingGuest.RSVPStatus.DECLINED)
    eligible_ids = set(eligible.values_list('pk', flat=True))
    sections, seated = [], set()
    for table in event.seating_tables.prefetch_related('assignments__guest'):
        guests = [a.guest for a in table.assignments.all() if a.guest_id in eligible_ids]
        sections.append({'name': table.name, 'guests': guests})
        seated.update(g.pk for g in guests)
    unseated = [g for g in eligible if g.pk not in seated]
    if unseated:
        sections.append({'name': 'Unseated guests', 'guests': unseated})
    return sections


def table_plan_pdf(event, sections):
    output = io.BytesIO()
    width, height = landscape(A4)
    document = SimpleDocTemplate(output, pagesize=(width, height), rightMargin=14*mm,
                                 leftMargin=14*mm, topMargin=30*mm, bottomMargin=16*mm,
                                 title=f'{event.name} table plan', author='Plan2Wed')
    heading = ParagraphStyle('TableName', fontName='PlanBold', fontSize=13, leading=17, spaceAfter=8)
    guest_style = ParagraphStyle('Guest', fontName='PlanRegular', fontSize=10, leading=15, spaceAfter=3)
    cells = []
    for section in sections:
        cells.append([Paragraph(escape(section['name']), heading)] + [
            Paragraph(escape(str(guest)), guest_style) for guest in section['guests']
        ])
        if not section['guests']:
            cells[-1].append(Paragraph('No guests seated yet.', guest_style))
    if not cells:
        cells = [[Paragraph('No tables or guests to export yet.', guest_style)]]
    rows = [cells[i:i+3] + [''] * (3-len(cells[i:i+3])) for i in range(0, len(cells), 3)]
    table_style = TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16), ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 18),
    ])
    grids = []
    for row in rows:
        grid = Table([row], colWidths=[document.width/3]*3, style=table_style)
        _, row_height = grid.wrap(document.width, document.height)
        # Keep normal tables together; exceptionally large tables may span pages.
        if row_height > document.height - 12:
            grid = Table([row], colWidths=[document.width/3]*3,
                         style=table_style, splitInRow=1)
        grids.append(grid)

    def page_header(canvas, doc):
        title = Paragraph(escape(event.name) + ' — Table plan', heading)
        _, title_height = title.wrap(document.width, 50)
        title.drawOn(canvas, 14*mm, height-10*mm-title_height)
        canvas.setFont('PlanRegular', 9)
        if event.event_date:
            canvas.drawString(14*mm, height-26*mm, event.event_date.strftime('%d %B %Y'))
        canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawRightString(width-14*mm, 9*mm, f'Plan2Wed · Page {doc.page}')
    document.build(grids, onFirstPage=page_header, onLaterPages=page_header)
    return output.getvalue()


@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def table_plan_export(request, event_id, pdf=False):
    member = getattr(request.user, 'member_profile', None)
    if member is None:
        return redirect('member_portal')
    event = get_object_or_404(WeddingEvent, pk=event_id, budget__member=member)
    if not event.requires_table_plan:
        return redirect('event_detail', event_id=event.pk)
    sections = plan_sections(event)
    filename = f'{slugify(event.name) or "event"}-table-plan.pdf'
    if pdf:
        response = HttpResponse(table_plan_pdf(event, sections), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    form = TablePlanEmailForm(request.POST if request.method == 'POST' else None,
                              initial={'recipient': member.email})
    if request.method == 'POST' and form.is_valid():
        email = EmailMessage(subject=f'{event.name} table plan',
                             body=f'Please find the table plan for {event.name} attached.\n\nSent from Plan2Wed.',
                             from_email=settings.DEFAULT_FROM_EMAIL, to=[form.cleaned_data['recipient']])
        email.attach(filename, table_plan_pdf(event, sections), 'application/pdf')
        try:
            if email.send() != 1:
                raise RuntimeError('Email backend did not accept the message')
        except Exception:
            logger.exception('Table plan email failed; event id=%s', event.pk)
            form.add_error(None, 'The email could not be sent. Please try again or download the PDF.')
        else:
            messages.success(request, 'Table plan PDF sent by email.')
            return redirect('table_plan_export', event_id=event.pk)
    return render(request, 'planner/table_plan_export.html', {
        'event': event, 'sections': sections, 'email_form': form,
    })
