import csv
import io
import secrets
from django.core.exceptions import ValidationError
from decimal import Decimal

from django.utils import timezone

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Lower, Trim
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .forms import SeatingTableForm, MemberSignupForm, ShoppingListItemForm, VenueForm, WeddingBudgetForm, WeddingEventForm, WeddingGuestForm
from .forms import ReceiptUploadForm, ReceiptItemFormSet, ShoppingManagementImportForm, ShoppingManagementItemForm
from .shopping_import import read_shopping_csv
from .receipts import scan_receipt, receipt_items
from .email_verification import request_email_verification
from .models import DirectoryVenue, EventTemplate, events_named
from .forms import EventTemplatePlanForm
from .forms import VenueDirectorySearchForm
from .models import SeatingTable, SeatingAssignment, Member, ShoppingListItem, Venue, WeddingBudget, WeddingEvent, WeddingGuest


def signup(request):
    if request.method == "POST":
        form = MemberSignupForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user_model = get_user_model()
                    user = user_model.objects.create_user(
                        username=form.cleaned_data["email"],
                        email=form.cleaned_data["email"],
                        first_name=form.cleaned_data["first_name"],
                        last_name=form.cleaned_data["last_name"],
                        password=form.cleaned_data["password1"],
                        is_active=False,
                    )
                    member = form.save(commit=False)
                    member.user = user
                    member.save()
                    WeddingBudget.objects.create(
                        member=member,
                        bride_name=form.cleaned_data["bride_name"],
                        bride_email=form.cleaned_data["bride_email"],
                        bride_phone=form.cleaned_data["bride_phone"],
                        groom_name=form.cleaned_data["groom_name"],
                        groom_email=form.cleaned_data["groom_email"],
                        groom_phone=form.cleaned_data["groom_phone"],
                    )
                    request.session["signup_role"] = member.signup_role
                    request_email_verification(member.pk)
            except IntegrityError:
                form.add_error("email", "This email already has a login. Please log in or use a different email address.")
            else:
                messages.success(request, 'Your membership is registered. Check your email to verify your address and activate your account.')
                return redirect("signup_complete")
    else:
        form = MemberSignupForm()
    return render(request, "planner/signup.html", {"form": form})


def signup_complete(request):
    signup_role = request.session.pop("signup_role", Member.SignupRole.COUPLE)
    return render(request, "planner/signup_complete.html", {"signup_role": signup_role})


@never_cache
@login_required
def member_portal(request):
    member = getattr(request.user, "member_profile", None)
    budget = getattr(member, "wedding_budget", None) if member else None
    budget_form = WeddingBudgetForm(instance=budget)
    if request.method == "POST" and member:
        action = request.POST.get("action")
        if action == "save_budget":
            budget_form = WeddingBudgetForm(request.POST, instance=budget)
            if budget_form.is_valid():
                budget = budget_form.save(commit=False)
                budget.member = member
                budget.save()
                messages.success(request, 'Your wedding details and budget have been saved.')
                return redirect("member_portal")
        elif action == "delete_event" and budget:
            event = get_object_or_404(WeddingEvent, pk=request.POST.get("event_id"), budget=budget)
            event.delete()
            messages.success(request, 'Event deleted from your wedding plan.')
            return redirect("member_portal")
    events = budget.events.all() if budget else []
    timeline_items = [
        {"date": event.event_date, "event": event, "is_big_day": event.is_wedding_day}
        for event in events if event.event_date
    ]
    timeline_items.sort(key=lambda item: item["date"])
    return render(request, "planner/member_portal.html", {
        "member": member,
        "budget": budget,
        "budget_form": budget_form,
        "events": events,
        "timeline_items": timeline_items,
    })


@never_cache
@login_required
def spending_statement(request):
    member = getattr(request.user, "member_profile", None)
    if member is None:
        return redirect("member_portal")
    budget = getattr(member, "wedding_budget", None)
    sections = []
    spent = Decimal("0.00")
    pending = Decimal("0.00")
    if budget:
        for event in budget.events.prefetch_related("shopping_items"):
            purchased = []
            event_spent = event.other_spent
            event_pending = event.other_pending
            for item in event.shopping_items.all():
                if item.is_purchased:
                    purchased.append(item)
                    event_spent += item.total_cost
                else:
                    event_pending += item.total_cost
            sections.append({
                "event": event, "items": purchased,
                "spent": event_spent, "pending": event_pending,
                "budget_percentage": event_spent / budget.allocated * Decimal("100") if budget.allocated else None,
            })
            spent += event_spent
            pending += event_pending
    return render(request, "planner/spending_statement.html", {
        "member": member, "budget": budget, "sections": sections,
        "spent": spent, "pending": pending,
        "remaining": budget.allocated - spent - pending if budget else Decimal("0.00"),
        "generated_at": timezone.now(),
    })


@never_cache
@login_required
def event_detail(request, event_id):
    member = getattr(request.user, "member_profile", None)
    if member is None:
        return redirect("member_portal")
    event = get_object_or_404(WeddingEvent.objects.select_related("venue"), pk=event_id, budget__member=member)
    if request.method == "POST" and request.POST.get("action") == "delete_event":
        event.delete()
        messages.success(request, 'Event deleted from your wedding plan.')
        return redirect("member_portal")
    return render(request, "planner/event_detail.html", {"event": event})


@never_cache
@login_required
def event_form(request, event_id=None):
    member = getattr(request.user, "member_profile", None)
    if member is None:
        return redirect("member_portal")

    budget = getattr(member, "wedding_budget", None)
    event = get_object_or_404(WeddingEvent, pk=event_id, budget=budget) if event_id and budget else None
    if event_id and event is None:
        return redirect("member_portal")

    form = WeddingEventForm(request.POST or None, instance=event, budget=budget)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if budget is None:
                    budget, _ = WeddingBudget.objects.get_or_create(member=member)
                saved_event = form.save(commit=False)
                saved_event.budget = budget
                saved_event.save()
                saved_event.guests.set(form.cleaned_data["guests"])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Event updated.' if event_id else 'Event added to your wedding plan.')
            return redirect("event_detail", event_id=saved_event.id)

    return render(request, "planner/event_form.html", {"form": form, "event": event})


@never_cache
@login_required
def shopping_management(request):
    member = getattr(request.user, 'member_profile', None)
    if member is None:
        return redirect('member_portal')
    events = WeddingEvent.objects.filter(budget__member=member).prefetch_related('shopping_items')
    initial = {'list_category': request.GET.get('list', 'other')}
    if request.GET.get('event', '').isdigit():
        initial['event'] = get_object_or_404(events, pk=request.GET['event']).pk
    manual_form = ShoppingManagementItemForm(member=member, initial=initial, prefix="manual")
    import_form = ShoppingManagementImportForm(member=member, initial=initial)
    preview = None
    token = ''
    event = None
    key = 'shopping_management_import'
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_manual_item':
            manual_form = ShoppingManagementItemForm(request.POST, member=member, prefix='manual')
            if manual_form.is_valid():
                item = manual_form.save(commit=False)
                item.is_purchased = False
                item.save()
                messages.success(request, f'{item.name} added to {item.event.name} as To buy.')
                return redirect(f"{reverse('shopping_management')}?event={item.event_id}&list={item.list_category}#manual-item")
        elif action == 'preview_import':
            request.session.pop(key, None)
            import_form = ShoppingManagementImportForm(request.POST, request.FILES, member=member)
            if import_form.is_valid():
                event = import_form.cleaned_data['event']
                try:
                    preview = read_shopping_csv(import_form.cleaned_data['file'], event, import_form.cleaned_data['list_category'])
                    token = secrets.token_urlsafe(24)
                    request.session[key] = {'token': token, 'event_id': event.pk, 'rows': preview}
                    messages.info(request, 'Review the import below before adding the items to your shopping list.')
                except ValidationError as error:
                    import_form.add_error(None, error)
        elif action == 'confirm_import':
            pending = request.session.get(key)
            if not pending or request.POST.get('import_token') != pending['token']:
                messages.error(request, 'This import review has expired or was already imported. Upload the CSV again.')
                return redirect('shopping_management')
            event = get_object_or_404(events, pk=pending['event_id'])
            added = skipped = 0
            with transaction.atomic():
                for row in pending['rows']:
                    if event.shopping_items.filter(name__iexact=row['name'], list_category=row['list_category']).exists():
                        skipped += 1
                        continue
                    ShoppingListItem.objects.create(event=event, **row)
                    added += 1
            request.session.pop(key, None)
            messages.success(request, f'Imported {added} items as To buy; skipped {skipped} duplicates.')
            return redirect('event_shopping_list', event_id=event.pk)
    return render(request, 'planner/shopping_management.html', {
        'events': events, 'event': event, 'import_form': import_form, 'manual_form': manual_form,
        'import_preview': preview, 'import_token': token,
        'list_choices': ShoppingListItem.ListCategory.choices,
    })


@never_cache
@login_required
def event_shopping_list(request, event_id):
    member = getattr(request.user, "member_profile", None)
    if member is None:
        return redirect("member_portal")
    event = get_object_or_404(WeddingEvent, pk=event_id, budget__member=member)
    all_items = event.shopping_items.all()
    selected_list = request.GET.get('list', '')
    if selected_list not in ShoppingListItem.ListCategory.values:
        selected_list = ''
    items = all_items.filter(list_category=selected_list) if selected_list else all_items
    receipt_form = ReceiptUploadForm()
    receipt_rows = None
    receipt_text = ''
    receipt_token = ''
    receipt_key = f'receipt_review_{event.pk}'
    editing_item = get_object_or_404(ShoppingListItem, pk=request.GET["edit_item"], event=event) if request.GET.get("edit_item") else None
    item_form = ShoppingListItemForm(instance=editing_item, initial={'list_category': selected_list or 'other'} if not editing_item else None)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "scan_receipt":
            receipt_form = ReceiptUploadForm(request.POST, request.FILES)
            if receipt_form.is_valid():
                try:
                    receipt_text = scan_receipt(receipt_form.cleaned_data['image'])
                    suggestions = receipt_items(receipt_text)
                    if not suggestions:
                        raise ValidationError('No item prices were found. Try a clearer photo showing the item names and prices, or add items manually.')
                    for row in suggestions:
                        match = event.shopping_items.filter(is_purchased=False, name__iexact=row['name']).first()
                        if match:
                            row['existing_item'] = match.pk
                            row['supplier_name'] = match.supplier_name
                            row['list_category'] = match.list_category
                        else:
                            row['list_category'] = selected_list or 'other'
                    receipt_rows = ReceiptItemFormSet(initial=suggestions, form_kwargs={'event': event}, prefix='receipt')
                    receipt_token = secrets.token_urlsafe(24)
                    request.session[receipt_key] = receipt_token
                    messages.info(request, 'Receipt scanned. Review the items below before confirming your purchases.')
                except ValidationError as error:
                    receipt_form.add_error(None, error)
        elif action == "confirm_receipt":
            receipt_token = request.POST.get('receipt_token', '')
            receipt_rows = ReceiptItemFormSet(request.POST, form_kwargs={'event': event}, prefix='receipt')
            if not receipt_token or receipt_token != request.session.get(receipt_key):
                receipt_form = ReceiptUploadForm({})
                receipt_form.is_valid()
                receipt_form.add_error(None, 'This receipt review has expired or was already imported. Please scan again.')
                receipt_rows = None
            elif receipt_rows.is_valid():
                with transaction.atomic():
                    for row in receipt_rows.cleaned_data:
                        if not row.get('include'):
                            continue
                        item = row.get('existing_item') or ShoppingListItem(event=event)
                        for field in ('name', 'quantity', 'unit_cost', 'supplier_name'):
                            setattr(item, field, row[field])
                        item.list_category = row.get('list_category') or item.list_category or 'other'
                        item.is_purchased = True
                        item.save()
                request.session.pop(receipt_key, None)
                messages.success(request, 'Receipt items imported and marked as purchased.')
                return redirect('event_shopping_list', event_id=event.id)
        elif action == "add_item":
            item_form = ShoppingListItemForm(request.POST)
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.event = event
                item.save()
                messages.success(request, 'Shopping item added.')
                return redirect("event_shopping_list", event_id=event.id)
        elif action == "update_item":
            editing_item = get_object_or_404(ShoppingListItem, pk=request.POST.get("item_id"), event=event)
            item_form = ShoppingListItemForm(request.POST, instance=editing_item)
            if item_form.is_valid():
                item_form.save()
                messages.success(request, 'Shopping item updated.')
                return redirect("event_shopping_list", event_id=event.id)
        elif action == "toggle_item":
            item = get_object_or_404(ShoppingListItem, pk=request.POST.get("item_id"), event=event)
            item.is_purchased = not item.is_purchased
            item.save(update_fields=["is_purchased"])
            messages.success(request, 'Item marked as purchased.' if item.is_purchased else 'Item marked as To buy.')
            return redirect("event_shopping_list", event_id=event.id)
        elif action == "delete_item":
            item = get_object_or_404(ShoppingListItem, pk=request.POST.get("item_id"), event=event)
            item.delete()
            messages.success(request, 'Shopping item deleted.')
            return redirect("event_shopping_list", event_id=event.id)

    grouped_items = {}
    for item in items:
        grouped_items.setdefault(item.list_category, []).append(item)
    item_groups = [
        {'category': category, 'label': label, 'items': grouped_items[category],
         'total': sum((item.total_cost for item in grouped_items[category]), Decimal('0')),
         'committed': sum((item.total_cost for item in grouped_items[category] if item.is_purchased), Decimal('0')),
         'pending': sum((item.total_cost for item in grouped_items[category] if not item.is_purchased), Decimal('0')),
         'unpriced_count': sum(item.unit_cost is None for item in grouped_items[category]),
         'open': selected_list == category or bool(editing_item and editing_item.list_category == category)}
        for category, label in ShoppingListItem.ListCategory.choices if category in grouped_items
    ]
    return render(request, "planner/shopping_list.html", {
        "event": event,
        "items": items,
        "item_groups": item_groups,
        "list_choices": ShoppingListItem.ListCategory.choices,
        "selected_list": selected_list,
        "unpriced_count": all_items.filter(unit_cost__isnull=True).count(),
        "receipt_form": receipt_form,
        "receipt_rows": receipt_rows,
        "receipt_text": receipt_text,
        "receipt_token": receipt_token,
        "item_form": item_form,
        "editing_item": editing_item,
        "purchased_total": sum((item.total_cost for item in all_items if item.is_purchased), 0),
        "pending_total": sum((item.total_cost for item in all_items if not item.is_purchased), 0),
    })


@never_cache
@login_required
def event_catalogue(request, template_id=None):
    member = getattr(request.user, 'member_profile', None)
    if member is None:
        return redirect('member_portal')
    if template_id is None:
        planned_events = WeddingEvent.objects.filter(budget__member=member).alias(
            _event_name=Lower(Trim('name')),
        ).filter(
            Q(event_template_id=OuterRef('pk')) | Q(_event_name=Lower(Trim(OuterRef('name')))),
        )
        templates = EventTemplate.objects.filter(is_published=True).annotate(
            already_in_plan=Exists(planned_events),
        ).prefetch_related('shopping_suggestions')
        query = request.GET.get('q', '').strip()[:160]
        if query:
            templates = templates.filter(Q(name__icontains=query) | Q(description__icontains=query))
        return render(request, 'planner/event_catalogue.html', {'templates': templates, 'query': query})
    template = get_object_or_404(EventTemplate.objects.prefetch_related('shopping_suggestions'), pk=template_id, is_published=True)
    initial = {'items': list(template.shopping_suggestions.values_list('pk', flat=True))}
    if request.GET.get('event', '').isdigit():
        initial['event'] = get_object_or_404(WeddingEvent, pk=request.GET['event'], budget__member=member).pk
    form = EventTemplatePlanForm(request.POST if request.method == 'POST' else None, member=member, template=template, initial=initial)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            event = form.cleaned_data['event']
            if event is None:
                budget, _ = WeddingBudget.objects.get_or_create(member=member)
                WeddingBudget.objects.select_for_update().get(pk=budget.pk)
                event = budget.events.filter(event_template=template).first()
                if event is None:
                    event = events_named(budget.events, template.name).order_by('pk').first()
                if event is None:
                    event = WeddingEvent.objects.create(
                        budget=budget, event_template=template, name=template.name,
                        description=template.description, event_date=form.cleaned_data['event_date'],
                    )
                elif event.event_template_id is None:
                    event.event_template = template
                    event.save(update_fields=['event_template'])
            added = 0
            for suggestion in form.cleaned_data['items']:
                if not event.shopping_items.filter(name__iexact=suggestion.name, list_category=suggestion.list_category).exists():
                    ShoppingListItem.objects.create(event=event, name=suggestion.name, list_category=suggestion.list_category, quantity=suggestion.quantity, notes=suggestion.notes)
                    added += 1
        messages.success(request, f'{added} suggested items added to {event.name}. Quantities and costs can be updated in its shopping list.')
        return redirect('event_shopping_list', event_id=event.pk)
    return render(request, 'planner/event_template_detail.html', {'template': template, 'form': form})


@never_cache
@login_required
def venue_directory(request):
    member = getattr(request.user, 'member_profile', None)
    if member is None:
        return redirect('member_portal')
    if request.method == 'POST':
        listing = get_object_or_404(DirectoryVenue, pk=request.POST.get('venue_id') if request.POST.get('venue_id', '').isdigit() else None, is_published=True)
        budget, _ = WeddingBudget.objects.get_or_create(member=member)
        _, created = Venue.objects.get_or_create(budget=budget, directory_entry=listing, defaults={
            'name': listing.name, 'address': listing.address, 'contact_name': listing.contact_name,
            'email': listing.email, 'phone': listing.phone, 'website': listing.website,
        })
        messages.success(request, 'Venue added to your plan. Open Manage venues to assign it to an event.' if created else 'This venue is already in your plan.')
        return redirect('venue_directory')
    venues = DirectoryVenue.objects.filter(is_published=True)
    search_form = VenueDirectorySearchForm(request.GET)
    if search_form.is_valid():
        filters = search_form.cleaned_data
        if filters['query']:
            venues = venues.filter(Q(name__icontains=filters['query']) | Q(facilities__icontains=filters['query']) | Q(description__icontains=filters['query']))
        if filters['location']:
            venues = venues.filter(Q(location__icontains=filters['location']) | Q(address__icontains=filters['location']))
        if filters['venue_type']:
            venues = venues.filter(venue_type=filters['venue_type'])
        if filters['capacity']:
            venues = venues.filter(capacity__gte=filters['capacity'])
    else:
        venues = venues.none()
    page = Paginator(venues, 12).get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)
    return render(request, 'planner/venue_directory.html', {
        'search_form': search_form, 'page_obj': page, 'query_params': query_params.urlencode(),
        'saved_venue_ids': set(Venue.objects.filter(budget__member=member, directory_entry__isnull=False).values_list('directory_entry_id', flat=True)),
    })


@never_cache
@login_required
def venue_list(request):
    member = getattr(request.user, "member_profile", None)
    if member is None:
        return redirect("member_portal")
    budget, _ = WeddingBudget.objects.get_or_create(member=member)
    editing_venue = None
    if request.GET.get("edit"):
        editing_venue = get_object_or_404(Venue, pk=request.GET["edit"], budget=budget)
    venue_form = VenueForm(request.POST or None, instance=editing_venue)

    if request.method == "POST":
        action = request.POST.get("action")
        if action in {"save_venue", "update_venue"}:
            editing_venue = None
            if action == "update_venue":
                editing_venue = get_object_or_404(Venue, pk=request.POST.get("venue_id"), budget=budget)
            venue_form = VenueForm(request.POST, instance=editing_venue)
            if venue_form.is_valid():
                venue = venue_form.save(commit=False)
                venue.budget = budget
                venue.save()
                messages.success(request, 'Venue updated.' if action == 'update_venue' else 'Venue added to your plan.')
                return redirect("venue_list")
        elif action == "delete_venue":
            venue = get_object_or_404(Venue, pk=request.POST.get("venue_id"), budget=budget)
            venue.delete()
            messages.success(request, 'Venue deleted from your plan.')
            return redirect("venue_list")

    return render(request, "planner/venue_list.html", {
        "venues": budget.venues.all(),
        "venue_form": venue_form,
        "editing_venue": editing_venue,
    })


@never_cache
@login_required
def guest_list(request):
    member = getattr(request.user, "member_profile", None)
    if member is None:
        return redirect("member_portal")
    budget, _ = WeddingBudget.objects.get_or_create(member=member)
    selected_event = None
    event_id = request.GET.get("event")
    if event_id:
        selected_event = get_object_or_404(WeddingEvent, pk=event_id, budget=budget)

    editing_guest = None
    if request.GET.get("edit"):
        editing_guest = get_object_or_404(WeddingGuest, pk=request.GET["edit"], budget=budget)
    initial = {"events": [selected_event]} if selected_event and not editing_guest else None
    guest_form = WeddingGuestForm(budget=budget, instance=editing_guest, initial=initial)

    if request.method == "POST":
        action = request.POST.get("action")
        if action in {"save_guest", "update_guest"}:
            editing_guest = None
            if action == "update_guest":
                editing_guest = get_object_or_404(WeddingGuest, pk=request.POST.get("guest_id"), budget=budget)
            guest_form = WeddingGuestForm(request.POST, budget=budget, instance=editing_guest)
            if guest_form.is_valid():
                guest = guest_form.save(commit=False)
                guest.budget = budget
                guest.save()
                guest_form.save_m2m()
                messages.success(request, 'Guest updated.' if action == 'update_guest' else 'Guest added to your list.')
                return redirect("guest_list")
        elif action == "delete_guest":
            guest = get_object_or_404(WeddingGuest, pk=request.POST.get("guest_id"), budget=budget)
            guest.delete()
            messages.success(request, 'Guest removed from your list.')
            return redirect("guest_list")
        elif action == "import_guests":
            upload = request.FILES.get("guest_file")
            if not upload:
                messages.error(request, "Choose a CSV file to import.")
            elif upload.size > 5 * 1024 * 1024:
                messages.error(request, "The CSV file must be 5 MB or smaller.")
            else:
                try:
                    text = upload.read().decode("utf-8-sig")
                    reader = csv.DictReader(io.StringIO(text))
                    if not reader.fieldnames:
                        raise ValueError("The CSV file needs a header row.")

                    def normalized(row):
                        return {
                            str(key or "").strip().lower(): value.strip()
                            for key, value in row.items()
                            if key is not None and isinstance(value, str)
                        }

                    created = skipped = 0
                    imported_emails = set()
                    with transaction.atomic():
                        for row_number, raw_row in enumerate(reader, start=2):
                            if row_number > 2001:
                                skipped += 1
                                continue
                            row = normalized(raw_row)
                            first_name = (row.get("first name") or row.get("given name") or row.get("firstname") or "").strip()
                            last_name = (row.get("last name") or row.get("surname") or row.get("lastname") or "").strip()
                            display_name = row.get("display name") or row.get("full name") or row.get("name") or ""
                            if not first_name and display_name:
                                name_parts = display_name.split()
                                first_name = name_parts[0]
                                last_name = last_name or " ".join(name_parts[1:])
                            email = (row.get("email address") or row.get("e-mail address") or row.get("email") or row.get("e-mail") or "").strip().lower()
                            phone = (row.get("mobile phone") or row.get("phone") or row.get("primary phone") or row.get("business phone") or row.get("home phone") or "").strip()
                            if not first_name:
                                skipped += 1
                                continue
                            if email and (email in imported_emails or budget.guests.filter(email__iexact=email).exists()):
                                skipped += 1
                                continue
                            guest = WeddingGuest.objects.create(
                                budget=budget,
                                first_name=first_name[:80],
                                last_name=last_name[:80],
                                email=email,
                                phone=phone[:40],
                            )
                            if selected_event:
                                guest.events.add(selected_event)
                            if email:
                                imported_emails.add(email)
                            created += 1
                    messages.success(request, f"Imported {created} guest{'s' if created != 1 else ''}; skipped {skipped} blank, duplicate, or over-limit row{'s' if skipped != 1 else ''}.")
                except (UnicodeDecodeError, csv.Error, ValueError):
                    messages.error(request, "We couldn’t read that CSV. Export it as UTF-8 CSV and try again.")
            return redirect("guest_list" + (f"?event={selected_event.id}" if selected_event else ""))

    guests = budget.guests.all()
    if selected_event:
        guests = guests.filter(events=selected_event).distinct()
    return render(request, "planner/guest_list.html", {
        "budget": budget,
        "selected_event": selected_event,
        "guests": guests,
        "guest_form": guest_form,
        "editing_guest": editing_guest,
    })


@never_cache
@staff_member_required
def member_list(request):
    members = Member.objects.all()
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if query:
        members = members.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
            | Q(wedding_budget__bride_name__icontains=query)
            | Q(wedding_budget__groom_name__icontains=query)
        )
    if status in Member.Status.values:
        members = members.filter(status=status)
    return render(request, "planner/member_list.html", {
        "members": members,
        "query": query,
        "status_filter": status,
        "total_count": Member.objects.count(),
        "pending_count": Member.objects.filter(status=Member.Status.PENDING).count(),
        "active_count": Member.objects.filter(status=Member.Status.ACTIVE).count(),
    })


@never_cache
@staff_member_required
def member_status(request, member_id):
    if request.method == "POST":
        member = get_object_or_404(Member, pk=member_id)
        new_status = request.POST.get("status")
        if new_status in Member.Status.values:
            member.status = new_status
            member.save(update_fields=["status"])
            if member.user_id:
                member.user.is_active = new_status == Member.Status.ACTIVE
                member.user.save(update_fields=["is_active"])
            messages.success(request, 'Membership status updated.')
        else:
            messages.error(request, 'Choose a valid membership status.')
    return redirect("member_list")


@never_cache
@login_required
def table_plan(request, event_id):
    member = getattr(request.user, "member_profile", None)
    if member is None:
        return redirect("member_portal")
    event = get_object_or_404(WeddingEvent, pk=event_id, budget__member=member)
    editing_table = None
    if request.GET.get("edit"):
        editing_table = get_object_or_404(SeatingTable, pk=request.GET["edit"], event=event)
    form = SeatingTableForm(event=event, instance=editing_table)
    if request.method == "POST":
        # Serialize assignments within an event so simultaneous moves cannot overfill tables.
        with transaction.atomic():
            event = WeddingEvent.objects.select_for_update().get(pk=event.pk)
            action = request.POST.get("action")
            if action == "delete_table":
                get_object_or_404(SeatingTable, pk=request.POST.get("table_id"), event=event).delete()
                messages.success(request, "Table deleted. Its guests are now unseated.")
                return redirect("table_plan", event_id=event.pk)
            if action == "save_table":
                editing_table = get_object_or_404(SeatingTable, pk=request.POST["table_id"], event=event) if request.POST.get("table_id") else None
                form = SeatingTableForm(request.POST, event=event, instance=editing_table)
                if form.is_valid():
                    table = form.save(commit=False)
                    table.save()
                    guests = form.cleaned_data["guests"]
                    SeatingAssignment.objects.filter(event=event).filter(Q(table=table) | Q(guest__in=guests)).delete()
                    SeatingAssignment.objects.bulk_create([
                        SeatingAssignment(event=event, table=table, guest=guest) for guest in guests
                    ])
                    messages.success(request, "Table plan saved.")
                    return redirect("table_plan", event_id=event.pk)
    eligible = event.guests.filter(budget=event.budget).exclude(rsvp_status=WeddingGuest.RSVPStatus.DECLINED)
    assignments = event.seating_assignments.filter(guest__in=eligible)
    tables = list(event.seating_tables.prefetch_related("assignments__guest"))
    eligible_ids = set(eligible.values_list("pk", flat=True))
    for table in tables:
        table.seated_guests = [a.guest for a in table.assignments.all() if a.guest_id in eligible_ids]
        table.available_seats = max(0, table.capacity - len(table.seated_guests))
    return render(request, "planner/table_plan.html", {
        "event": event, "tables": tables, "table_form": form, "editing_table": editing_table,
        "unseated_guests": eligible.exclude(pk__in=assignments.values("guest_id")),
        "guest_count": eligible.count(), "seated_count": assignments.count(),
        "seat_count": sum(table.capacity for table in tables),
    })
