from .event_descriptions import description_source, suggested_description

from decimal import Decimal

from django.db import models, transaction
from django.conf import settings
from django.core.validators import MinValueValidator


class Member(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    class SignupRole(models.TextChoices):
        COUPLE = "couple", "Couple"
        REPRESENTATIVE = "representative", "Representative"

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="member_profile",
    )
    signup_role = models.CharField(max_length=20, choices=SignupRole.choices, default=SignupRole.COUPLE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def couple_name(self):
        try:
            budget = self.wedding_budget
        except WeddingBudget.DoesNotExist:
            return f"{self.first_name} {self.last_name}"
        names = " & ".join(name for name in (budget.bride_name, budget.groom_name) if name)
        return names or f"{self.first_name} {self.last_name}"

    @property
    def couple_initials(self):
        try:
            budget = self.wedding_budget
        except WeddingBudget.DoesNotExist:
            budget = None
        first_names = [budget.bride_name, budget.groom_name] if budget else [self.first_name, self.last_name]
        return "".join(name[:1].upper() for name in first_names if name)


class WeddingBudget(models.Model):
    member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name="wedding_budget")
    wedding_date = models.DateField(null=True, blank=True)
    has_separate_meal = models.BooleanField(default=False)
    meal_date = models.DateField(null=True, blank=True)
    bride_name = models.CharField(max_length=160, blank=True)
    bride_email = models.EmailField(blank=True)
    bride_phone = models.CharField(max_length=40, blank=True)
    groom_name = models.CharField(max_length=160, blank=True)
    groom_email = models.EmailField(blank=True)
    groom_phone = models.CharField(max_length=40, blank=True)
    allocated = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "wedding budget"
        verbose_name_plural = "wedding budgets"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            if kwargs.get("update_fields") is None or "wedding_date" in kwargs["update_fields"]:
                event = self.events.filter(is_wedding_day=True).first()
                if event:
                    self.events.filter(pk=event.pk).update(event_date=self.wedding_date)
                elif self.wedding_date:
                    self.events.create(name="Wedding Day", event_date=self.wedding_date, is_wedding_day=True)
            fields = kwargs.get("update_fields")
            if fields is None or {"wedding_date", "has_separate_meal", "meal_date"}.intersection(fields):
                if self.has_separate_meal:
                    self.events.update_or_create(
                        is_wedding_meal=True,
                        defaults={"event_date": self.meal_date or self.wedding_date},
                        create_defaults={
                            "name": "Wedding Meal / Reception",
                            "event_date": self.meal_date or self.wedding_date,
                        },
                    )

    @property
    def spent(self):
        return sum((event.spent for event in self.events.all()), Decimal("0.00"))

    @property
    def pending(self):
        return sum((event.pending for event in self.events.all()), Decimal("0.00"))

    @property
    def remaining(self):
        return self.allocated - self.spent - self.pending

    def __str__(self):
        return f"{self.member} wedding budget"


class Venue(models.Model):
    budget = models.ForeignKey(WeddingBudget, on_delete=models.CASCADE, related_name="venues")
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=300, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class WeddingEvent(models.Model):
    budget = models.ForeignKey(WeddingBudget, on_delete=models.CASCADE, related_name="events")
    venue = models.ForeignKey(Venue, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    event_date = models.DateField(null=True, blank=True)
    is_wedding_day = models.BooleanField(default=False, editable=False)
    is_wedding_meal = models.BooleanField(default=False, editable=False)
    other_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    other_pending = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["event_date", "name"]
        constraints = [
            models.UniqueConstraint(fields=["budget"], condition=models.Q(is_wedding_day=True), name="one_wedding_day_per_budget"),
            models.UniqueConstraint(fields=["budget"], condition=models.Q(is_wedding_meal=True), name="one_wedding_meal_per_budget"),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and not self.description:
            self.description = suggested_description(self.name)
        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.is_wedding_day and (kwargs.get("update_fields") is None or "event_date" in kwargs["update_fields"]):
                WeddingBudget.objects.filter(pk=self.budget_id).update(wedding_date=self.event_date)
                budget = WeddingBudget.objects.get(pk=self.budget_id)
                if budget.has_separate_meal and not budget.meal_date:
                    budget.events.filter(is_wedding_meal=True).update(event_date=self.event_date)
            if self.is_wedding_meal and (kwargs.get("update_fields") is None or "event_date" in kwargs["update_fields"]):
                # A date matching the ceremony continues to follow the wedding date.
                budget = WeddingBudget.objects.get(pk=self.budget_id)
                meal_date = self.event_date if self.event_date != budget.wedding_date else None
                WeddingBudget.objects.filter(pk=self.budget_id).update(meal_date=meal_date)

    def __str__(self):
        return self.name

    @property
    def description_source(self):
        return description_source(self.name, self.description)

    def _shopping_total(self, purchased):
        return sum(
            (item.total_cost for item in self.shopping_items.filter(is_purchased=purchased)),
            Decimal("0.00"),
        )

    @property
    def spent(self):
        return self.other_spent + self._shopping_total(True)

    @property
    def pending(self):
        return self.other_pending + self._shopping_total(False)


class ShoppingListItem(models.Model):
    event = models.ForeignKey(WeddingEvent, on_delete=models.CASCADE, related_name="shopping_items")
    name = models.CharField(max_length=160)
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    notes = models.CharField(max_length=300, blank=True)
    supplier_name = models.CharField(max_length=160, blank=True)
    supplier_contact = models.CharField(max_length=120, blank=True)
    supplier_email = models.EmailField(blank=True)
    supplier_phone = models.CharField(max_length=40, blank=True)
    supplier_website = models.URLField(blank=True)
    is_purchased = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_purchased", "name"]
        verbose_name = "shopping list item"
        verbose_name_plural = "shopping list items"

    def __str__(self):
        return self.name

    @property
    def total_cost(self):
        return self.unit_cost * self.quantity


class WeddingGuest(models.Model):
    class RSVPStatus(models.TextChoices):
        INVITED = "invited", "Invited"
        ATTENDING = "attending", "Attending"
        DECLINED = "declined", "Declined"

    budget = models.ForeignKey(WeddingBudget, on_delete=models.CASCADE, related_name="guests")
    events = models.ManyToManyField(WeddingEvent, blank=True, related_name="guests")
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    rsvp_status = models.CharField(max_length=10, choices=RSVPStatus.choices, default=RSVPStatus.INVITED)
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()


class SeatingTable(models.Model):
    event = models.ForeignKey(WeddingEvent, on_delete=models.CASCADE, related_name="seating_tables")
    name = models.CharField(max_length=80)
    capacity = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1)])
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["event", "name"], name="unique_table_name_per_event"),
            models.CheckConstraint(condition=models.Q(capacity__gte=1), name="table_capacity_positive"),
        ]

    def __str__(self):
        return self.name


class SeatingAssignment(models.Model):
    event = models.ForeignKey(WeddingEvent, on_delete=models.CASCADE, related_name="seating_assignments")
    table = models.ForeignKey(SeatingTable, on_delete=models.CASCADE, related_name="assignments")
    guest = models.ForeignKey(WeddingGuest, on_delete=models.CASCADE, related_name="seating_assignments")

    class Meta:
        ordering = ["guest__first_name", "guest__last_name"]
        constraints = [models.UniqueConstraint(fields=["event", "guest"], name="one_table_per_guest_per_event")]
