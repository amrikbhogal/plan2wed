import csv
import io
from decimal import Decimal

from django.utils import timezone

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from .forms import SeatingTableForm, MemberSignupForm, ShoppingListItemForm, VenueForm, WeddingBudgetForm, WeddingEventForm, WeddingGuestForm
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
            except IntegrityError:
                form.add_error("email", "This email already has a login. Please log in or use a different email address.")
            else:
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
                return redirect("member_portal")
        elif action == "delete_event" and budget:
            event = get_object_or_404(WeddingEvent, pk=request.POST.get("event_id"), budget=budget)
            event.delete()
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
        if budget is None:
            budget = WeddingBudget.objects.create(member=member)
        event = form.save(commit=False)
        event.budget = budget
        event.save()
        event.guests.set(form.cleaned_data["guests"])
        return redirect("event_detail", event_id=event.id)

    return render(request, "planner/event_form.html", {"form": form, "event": event})


@never_cache
@login_required
def event_shopping_list(request, event_id):
    member = getattr(request.user, "member_profile", None)
    if member is None:
        return redirect("member_portal")
    event = get_object_or_404(WeddingEvent, pk=event_id, budget__member=member)
    items = event.shopping_items.all()
    editing_item = get_object_or_404(ShoppingListItem, pk=request.GET["edit_item"], event=event) if request.GET.get("edit_item") else None
    item_form = ShoppingListItemForm(instance=editing_item)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_item":
            item_form = ShoppingListItemForm(request.POST)
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.event = event
                item.save()
                return redirect("event_shopping_list", event_id=event.id)
        elif action == "update_item":
            editing_item = get_object_or_404(ShoppingListItem, pk=request.POST.get("item_id"), event=event)
            item_form = ShoppingListItemForm(request.POST, instance=editing_item)
            if item_form.is_valid():
                item_form.save()
                return redirect("event_shopping_list", event_id=event.id)
        elif action == "toggle_item":
            item = get_object_or_404(ShoppingListItem, pk=request.POST.get("item_id"), event=event)
            item.is_purchased = not item.is_purchased
            item.save(update_fields=["is_purchased"])
            return redirect("event_shopping_list", event_id=event.id)
        elif action == "delete_item":
            item = get_object_or_404(ShoppingListItem, pk=request.POST.get("item_id"), event=event)
            item.delete()
            return redirect("event_shopping_list", event_id=event.id)

    return render(request, "planner/shopping_list.html", {
        "event": event,
        "items": items,
        "item_form": item_form,
        "editing_item": editing_item,
        "purchased_total": sum((item.total_cost for item in items if item.is_purchased), 0),
        "pending_total": sum((item.total_cost for item in items if not item.is_purchased), 0),
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
                return redirect("venue_list")
        elif action == "delete_venue":
            venue = get_object_or_404(Venue, pk=request.POST.get("venue_id"), budget=budget)
            venue.delete()
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
                return redirect("guest_list")
        elif action == "delete_guest":
            guest = get_object_or_404(WeddingGuest, pk=request.POST.get("guest_id"), budget=budget)
            guest.delete()
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
