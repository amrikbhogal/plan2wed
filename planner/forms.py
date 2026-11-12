from .event_descriptions import EVENT_DESCRIPTIONS
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import SeatingTable, SeatingAssignment, Member, ShoppingListItem, Venue, WeddingBudget, WeddingEvent, WeddingGuest


class MemberSignupForm(forms.ModelForm):
    signup_role = forms.ChoiceField(
        label="Who is signing up?",
        choices=[
            (Member.SignupRole.COUPLE, "We’re the couple (one shared login)"),
            (Member.SignupRole.REPRESENTATIVE, "I’m helping a couple as a planner, family member, or friend (one individual login)"),
        ],
        widget=forms.RadioSelect(attrs={"class": "choice-list"}),
    )
    bride_name = forms.CharField(max_length=160, label="Bride’s name")
    bride_email = forms.EmailField(required=False, label="Bride’s email", widget=forms.EmailInput(attrs={"placeholder": "Optional"}))
    bride_phone = forms.CharField(max_length=40, required=False, label="Bride’s phone", widget=forms.TelInput(attrs={"placeholder": "Optional"}))
    groom_name = forms.CharField(max_length=160, label="Groom’s name")
    groom_email = forms.EmailField(required=False, label="Groom’s email", widget=forms.EmailInput(attrs={"placeholder": "Optional"}))
    groom_phone = forms.CharField(max_length=40, required=False, label="Groom’s phone", widget=forms.TelInput(attrs={"placeholder": "Optional"}))
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "placeholder": "At least 8 characters"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "placeholder": "Enter your password again"}),
    )

    class Meta:
        model = Member
        fields = [
            "signup_role",
            "bride_name", "bride_email", "bride_phone",
            "groom_name", "groom_email", "groom_phone",
            "first_name", "last_name", "email", "phone",
        ]
        labels = {
            "first_name": "Account contact first name",
            "last_name": "Account contact last name",
            "email": "Shared login email",
            "phone": "Account contact phone",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name", "placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name", "placeholder": "Last name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
            "phone": forms.TelInput(attrs={"autocomplete": "tel", "placeholder": "Optional"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields([
            "signup_role",
            "bride_name", "bride_email", "bride_phone",
            "groom_name", "groom_email", "groom_phone",
            "first_name", "last_name", "email", "phone", "password1", "password2",
        ])

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Member.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email is already registered.")
        user_model = get_user_model()
        if user_model.objects.filter(username__iexact=email).exists() or user_model.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email already has a login. Please log in or use a different email address.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        if password1:
            try:
                validate_password(password1)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned_data


class WeddingBudgetForm(forms.ModelForm):
    has_separate_meal = forms.TypedChoiceField(
        label="Will you have a separate meal or reception after the Anand Karaj?",
        choices=[("False", "No / not decided yet"), ("True", "Yes, at a separate venue")],
        coerce=lambda value: value == "True",
        widget=forms.Select(),
        help_text="Choose Yes to add a Wedding Meal / Reception event. Set the Gurdwara on your Wedding Day event and the banquet hall on the meal event using Edit. Each has its own guests and shopping list. Choosing No later keeps any existing event and its details; you can delete it from Wedding events.",
    )

    class Meta:
        model = WeddingBudget
        fields = [
            "wedding_date",
            "has_separate_meal", "meal_date",
            "bride_name", "bride_email", "bride_phone",
            "groom_name", "groom_email", "groom_phone",
            "allocated",
        ]
        labels = {
            "wedding_date": "Wedding date",
            "meal_date": "Meal / reception date (if different)",
            "bride_name": "Bride’s name",
            "bride_email": "Bride’s email",
            "bride_phone": "Bride’s phone",
            "groom_name": "Groom’s name",
            "groom_email": "Groom’s email",
            "groom_phone": "Groom’s phone",
            "allocated": "Total budget allocated",
        }
        widgets = {
            "wedding_date": forms.DateInput(attrs={"type": "date"}),
            "meal_date": forms.DateInput(attrs={"type": "date"}),
            "bride_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "bride_email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "bride_phone": forms.TelInput(attrs={"autocomplete": "tel"}),
            "groom_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "groom_email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "groom_phone": forms.TelInput(attrs={"autocomplete": "tel"}),
            "allocated": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
        }
        help_texts = {"meal_date": "Leave blank to use the wedding date. You can choose the venue and invite guests once the event is created."}


class WeddingEventForm(forms.ModelForm):
    guests = forms.ModelMultipleChoiceField(
        queryset=WeddingGuest.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-list"}),
        label="Guests invited to this event",
    )

    EVENT_SUGGESTIONS = list(EVENT_DESCRIPTIONS)
    EVENT_DESCRIPTIONS = EVENT_DESCRIPTIONS

    class Meta:
        model = WeddingEvent
        fields = ["name", "description", "event_date", "venue", "guests", "other_spent", "other_pending", "notes"]
        labels = {
            "name": "Event or expense",
            "description": "Description",
            "event_date": "Date",
            "venue": "Venue",
            "other_spent": "Other amount spent (outside shopping list)",
            "other_pending": "Other pending amount (outside shopping list)",
            "notes": "Notes",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Choose or enter an event", "list": "wedding-event-suggestions", "autocomplete": "off"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Describe this event"}),
            "event_date": forms.DateInput(attrs={"type": "date"}),
            "venue": forms.Select(),
            "other_spent": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
            "other_pending": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "0.00"}),
            "notes": forms.TextInput(attrs={"placeholder": "Optional details"}),
        }

    def __init__(self, *args, budget=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["venue"].queryset = Venue.objects.filter(budget=budget) if budget else Venue.objects.none()
        self.fields["guests"].queryset = WeddingGuest.objects.filter(budget=budget) if budget else WeddingGuest.objects.none()
        if self.instance.pk and not self.is_bound:
            self.initial["guests"] = self.instance.guests.values_list("pk", flat=True)


class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = ["name", "address", "contact_name", "email", "phone", "website", "notes"]
        labels = {
            "name": "Venue name",
            "address": "Address",
            "contact_name": "Contact person",
            "email": "Email",
            "phone": "Phone",
            "website": "Website",
            "notes": "Notes",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Venue name"}),
            "address": forms.TextInput(attrs={"placeholder": "Street, town, postcode"}),
            "contact_name": forms.TextInput(attrs={"placeholder": "Optional"}),
            "email": forms.EmailInput(attrs={"placeholder": "Optional"}),
            "phone": forms.TelInput(attrs={"placeholder": "Optional"}),
            "website": forms.URLInput(attrs={"placeholder": "https://"}),
            "notes": forms.TextInput(attrs={"placeholder": "Optional details"}),
        }

class ShoppingListItemForm(forms.ModelForm):
    class Meta:
        model = ShoppingListItem
        fields = ["name", "list_category", "quantity", "unit_cost", "supplier_name", "supplier_contact", "supplier_email", "supplier_phone", "supplier_website", "notes"]
        labels = {
            "name": "Item",
            "quantity": "Quantity",
            "unit_cost": "Cost per item (optional)",
            "list_category": "Shopping list",
            "supplier_name": "Supplier name",
            "supplier_contact": "Supplier contact person",
            "supplier_email": "Supplier email",
            "supplier_phone": "Supplier phone",
            "supplier_website": "Supplier website",
            "notes": "Notes",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Table candles"}),
            "quantity": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "unit_cost": forms.NumberInput(attrs={"min": "0", "step": "0.01", "placeholder": "0.00"}),
            "supplier_name": forms.TextInput(attrs={"placeholder": "Supplier or shop"}),
            "supplier_contact": forms.TextInput(attrs={"placeholder": "Contact name"}),
            "supplier_email": forms.EmailInput(attrs={"placeholder": "supplier@example.com"}),
            "supplier_phone": forms.TelInput(attrs={"placeholder": "Phone number"}),
            "supplier_website": forms.URLInput(attrs={"placeholder": "https://"}),
            "notes": forms.TextInput(attrs={"placeholder": "Optional details"}),
        }


class WeddingGuestForm(forms.ModelForm):
    events = forms.ModelMultipleChoiceField(
        queryset=WeddingEvent.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-list"}),
        label="Events this guest is invited to",
    )

    class Meta:
        model = WeddingGuest
        fields = ["first_name", "last_name", "email", "phone", "rsvp_status", "events", "notes"]
        labels = {
            "first_name": "First name",
            "last_name": "Last name",
            "email": "Email",
            "phone": "Phone",
            "rsvp_status": "RSVP status",
            "notes": "Notes",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TelInput(attrs={"autocomplete": "tel"}),
            "notes": forms.TextInput(attrs={"placeholder": "Dietary needs or other notes"}),
        }

    def __init__(self, *args, budget, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["events"].queryset = WeddingEvent.objects.filter(budget=budget)


class SeatingTableForm(forms.ModelForm):
    guests = forms.ModelMultipleChoiceField(
        queryset=WeddingGuest.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-list"}),
        label="Guests at this table",
        help_text="Only invited guests who have not declined are shown. Selecting someone seated elsewhere moves them to this table.",
    )

    class Meta:
        model = SeatingTable
        fields = ["name", "capacity", "notes", "guests"]
        labels = {"name": "Table name or number", "capacity": "Number of seats"}
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. Table 1 or Family"})}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event
        self.fields["guests"].queryset = event.guests.filter(budget=event.budget).exclude(rsvp_status=WeddingGuest.RSVPStatus.DECLINED)
        if self.instance.pk and not self.is_bound:
            self.initial["guests"] = self.instance.assignments.values_list("guest_id", flat=True)

    def clean(self):
        data = super().clean()
        guests, capacity = data.get("guests"), data.get("capacity")
        if guests is not None and capacity and len(guests) > capacity:
            self.add_error("guests", "There are more guests than seats. Increase the capacity or choose fewer guests.")
        if data.get("name") and SeatingTable.objects.filter(event=self.instance.event, name=data["name"]).exclude(pk=self.instance.pk).exists():
            self.add_error("name", "This event already has a table with that name.")
        return data


class ReceiptUploadForm(forms.Form):
    image = forms.FileField(label="Receipt photo", error_messages={"required": "Upload a receipt photo."}, widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/tiff"}))


class ReceiptItemForm(forms.Form):
    include = forms.BooleanField(required=False, initial=True, label="Import")
    existing_item = forms.ModelChoiceField(queryset=ShoppingListItem.objects.none(), required=False, label="Match shopping item", empty_label="Add as a new item")
    name = forms.CharField(max_length=160)
    quantity = forms.IntegerField(min_value=1, max_value=2147483647)
    unit_cost = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2)
    supplier_name = forms.CharField(max_length=160, required=False)
    list_category = forms.ChoiceField(choices=ShoppingListItem.ListCategory.choices, initial=ShoppingListItem.ListCategory.OTHER, required=False, label="Shopping list")

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['existing_item'].queryset = event.shopping_items.filter(is_purchased=False)


class BaseReceiptFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        included = [f.cleaned_data for f in self.forms if f.cleaned_data.get('include')]
        if not included:
            raise forms.ValidationError('Select at least one item to import.')
        matches = [row['existing_item'].pk for row in included if row.get('existing_item')]
        if len(matches) != len(set(matches)):
            raise forms.ValidationError('Match each shopping item only once.')


ReceiptItemFormSet = forms.formset_factory(ReceiptItemForm, formset=BaseReceiptFormSet, extra=0, max_num=50, validate_max=True, absolute_max=50)


class ShoppingImportForm(forms.Form):
    file = forms.FileField(label='CSV shopping list', widget=forms.FileInput(attrs={'accept': '.csv,text/csv'}))
    list_category = forms.ChoiceField(choices=ShoppingListItem.ListCategory.choices, label='Default shopping list')


class ShoppingManagementImportForm(ShoppingImportForm):
    event = forms.ModelChoiceField(queryset=WeddingEvent.objects.none(), label='Wedding event')

    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['event'].queryset = WeddingEvent.objects.filter(budget__member=member)
        self.order_fields(['event', 'file', 'list_category'])


class ShoppingManagementItemForm(ShoppingListItemForm):
    event = forms.ModelChoiceField(queryset=WeddingEvent.objects.none(), label='Wedding event')

    class Meta(ShoppingListItemForm.Meta):
        fields = ['event', *ShoppingListItemForm.Meta.fields]

    def __init__(self, *args, member, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['event'].queryset = WeddingEvent.objects.filter(budget__member=member)
