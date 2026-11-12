from django.contrib import admin

from .models import Member, ShoppingListItem, Venue, WeddingBudget, WeddingEvent, WeddingGuest


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("couple", "email", "signup_role", "status", "joined_at")
    list_filter = ("signup_role", "status", "joined_at")
    search_fields = ("first_name", "last_name", "email", "wedding_budget__bride_name", "wedding_budget__groom_name")
    readonly_fields = ("joined_at",)

    @admin.display(description="Couple")
    def couple(self, obj):
        return obj.couple_name

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.user_id:
            should_be_active = obj.status == Member.Status.ACTIVE
            if obj.user.is_active != should_be_active:
                obj.user.is_active = should_be_active
                obj.user.save(update_fields=("is_active",))


@admin.register(WeddingBudget)
class WeddingBudgetAdmin(admin.ModelAdmin):
    list_display = ("member", "allocated", "spent", "pending", "remaining", "updated_at")
    search_fields = ("member__first_name", "member__last_name", "member__email")
    readonly_fields = ("updated_at",)


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "budget", "contact_name", "phone", "email")
    search_fields = ("name", "address", "budget__member__email")


@admin.register(WeddingEvent)
class WeddingEventAdmin(admin.ModelAdmin):
    list_display = ("name", "budget", "event_date", "venue", "spent", "pending")
    list_filter = ("event_date",)
    search_fields = ("name", "budget__member__first_name", "budget__member__last_name", "budget__member__email")


@admin.register(ShoppingListItem)
class ShoppingListItemAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "list_category", "quantity", "unit_cost", "total_cost", "supplier_name", "is_purchased")
    list_filter = ("is_purchased", "list_category")
    search_fields = ("name", "event__name", "event__budget__member__email")


@admin.register(WeddingGuest)
class WeddingGuestAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "rsvp_status", "budget")
    list_filter = ("rsvp_status",)
    search_fields = ("first_name", "last_name", "email", "budget__member__email")
