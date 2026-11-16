"""Staff catalogue screens, using the same access gate as member administration."""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .forms import DirectoryVenueAdminForm, EventTemplateAdminForm, SuggestedShoppingItemAdminForm
from .models import DirectoryVenue, EventTemplate


def record_id(value):
    return int(value) if value and value.isascii() and value.isdigit() else 0


@never_cache
@staff_member_required
def venues(request):
    editing = get_object_or_404(DirectoryVenue, pk=record_id(request.GET['edit'])) if request.GET.get('edit') else None
    form = DirectoryVenueAdminForm(instance=editing)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action in ('delete', 'confirm_delete'):
            venue = get_object_or_404(DirectoryVenue, pk=record_id(request.POST.get('venue_id')))
            if action == 'delete':
                return render(request, 'planner/catalogue_delete.html', {'object': venue, 'record_id': venue.pk, 'record_field': 'venue_id', 'cancel_url': reverse('admin_venues'), 'message': 'This removes the shared listing. Members keep venues already saved to their own plans.'})
            venue.delete()
            messages.success(request, 'Shared venue deleted.')
            return redirect('admin_venues')
        if action == 'save':
            editing = get_object_or_404(DirectoryVenue, pk=record_id(request.POST['venue_id'])) if request.POST.get('venue_id') else None
            form = DirectoryVenueAdminForm(request.POST, instance=editing)
            if form.is_valid():
                venue = form.save()
                messages.success(request, 'Shared venue saved.')
                return redirect(f"{reverse('admin_venues')}?edit={venue.pk}#venue-form")
    query = request.GET.get('q', '').strip()[:160]
    listings = DirectoryVenue.objects.all()
    if query:
        listings = listings.filter(Q(name__icontains=query) | Q(location__icontains=query))
    return render(request, 'planner/admin_venues.html', {'listings': listings, 'form': form, 'editing': editing, 'query': query, 'admin_section': 'venues'})


@never_cache
@staff_member_required
def shopping(request):
    selected = get_object_or_404(EventTemplate, pk=record_id(request.GET['template'])) if request.GET.get('template') else None
    editing_item = get_object_or_404(selected.shopping_suggestions, pk=record_id(request.GET['item'])) if selected and request.GET.get('item') else None
    template_form = EventTemplateAdminForm(instance=selected, prefix='template')
    item_form = SuggestedShoppingItemAdminForm(instance=editing_item, prefix='item')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_template':
            # The selected URL defines the record; new forms have no template id.
            template_form = EventTemplateAdminForm(request.POST, instance=selected, prefix='template')
            if template_form.is_valid():
                template = template_form.save()
                messages.success(request, 'Suggested event and checklist details saved.')
                return redirect(f"{reverse('admin_shopping')}?template={template.pk}#template-form")
        elif selected and action in ('delete_item', 'confirm_delete'):
            item = get_object_or_404(selected.shopping_suggestions, pk=record_id(request.POST.get('item_id')))
            if action == 'delete_item':
                return render(request, 'planner/catalogue_delete.html', {'object': item, 'record_id': item.pk, 'record_field': 'item_id', 'cancel_url': f"{reverse('admin_shopping')}?template={selected.pk}", 'message': 'This removes the suggestion from this shared checklist. Members keep shopping items already added to their plans.'})
            item.delete()
            messages.success(request, 'Shopping suggestion removed.')
            return redirect(f"{reverse('admin_shopping')}?template={selected.pk}#checklist")
        elif selected and action == 'save_item':
            item_form = SuggestedShoppingItemAdminForm(request.POST, instance=editing_item, prefix='item')
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.event_template = selected
                item.save()
                messages.success(request, 'Shopping suggestion saved.')
                return redirect(f"{reverse('admin_shopping')}?template={selected.pk}#checklist")
    query = request.GET.get('q', '').strip()[:160]
    templates = EventTemplate.objects.all().prefetch_related('shopping_suggestions')
    if query:
        templates = templates.filter(name__icontains=query)
    return render(request, 'planner/admin_shopping.html', {'templates': templates, 'selected': selected, 'template_form': template_form, 'item_form': item_form, 'editing_item': editing_item, 'query': query, 'admin_section': 'shopping'})
