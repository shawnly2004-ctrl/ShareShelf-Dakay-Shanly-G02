from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from .forms import ItemForm
from .models import Item
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone


def _can_lend(user):
    return user.user_type in ('lender', 'both')


@role_required('member')
def my_items_view(request):
    items = Item.objects.filter(owner=request.user)
    return render(request, 'items/my_items.html', {
        'items': items,
        'can_lend': _can_lend(request.user),
    })


@role_required('member')
def item_create_view(request):
    if not _can_lend(request.user):
        messages.error(request, "Only lenders can list items. Change your type to Lender or Both in your profile.")
        return redirect('profile_edit')

    form = ItemForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if form.is_valid():
            item = form.save(commit=False)
            item.owner = request.user
            item.save()
            messages.success(request, f'"{item.name}" has been listed.')
            return redirect('my_items')
        messages.error(request, "Please fix the errors below.")
    return render(request, 'items/item_form.html', {'form': form, 'title': 'List a new item'})


@login_required
def item_detail_view(request, pk):
    item = get_object_or_404(Item, pk=pk)
    return render(request, 'items/item_detail.html', {
        'item': item,
        'is_owner': item.owner_id == request.user.id,
    })


@role_required('member')
def item_edit_view(request, pk):
    item = get_object_or_404(Item, pk=pk, owner=request.user)   # owner only
    form = ItemForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Item updated.")
            return redirect('item_detail', pk=item.pk)
        messages.error(request, "Please fix the errors below.")
    return render(request, 'items/item_form.html', {'form': form, 'title': 'Edit item'})


@role_required('member')
@require_POST
def item_toggle_view(request, pk):
    item = get_object_or_404(Item, pk=pk, owner=request.user)
    item.is_available = not item.is_available
    item.save(update_fields=['is_available'])
    state = "is now available" if item.is_available else "has been paused"
    messages.success(request, f'"{item.name}" {state}.')
    return redirect('my_items')


@role_required('member')
@require_POST
def item_delete_view(request, pk):
    item = get_object_or_404(Item, pk=pk, owner=request.user)
    name = item.name
    item.delete()
    messages.success(request, f'"{name}" has been deleted.')
    return redirect('my_items')

@role_required('member')
def browse_items_view(request):
    today = timezone.localdate()
    items = (Item.objects
             .filter(is_available=True, available_until__gte=today)
             .exclude(owner=request.user)
             .select_related('owner'))

    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    if q:
        items = items.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if category in dict(Item.CATEGORY_CHOICES):
        items = items.filter(category=category)

    page_obj = Paginator(items, 9).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'items/browse_items.html', {
        'page_obj': page_obj,
        'q': q,
        'category': category,
        'categories': Item.CATEGORY_CHOICES,
        'querystring': params.urlencode(),
    })


@role_required('admin')
def admin_items_view(request):
    items = Item.objects.select_related('owner')
    q = request.GET.get('q', '').strip()
    if q:
        items = items.filter(
            Q(name__icontains=q) | Q(owner__email__icontains=q) |
            Q(owner__first_name__icontains=q) | Q(owner__last_name__icontains=q)
        )
    page_obj = Paginator(items, 10).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'items/admin_items.html', {
        'page_obj': page_obj, 'q': q, 'querystring': params.urlencode(),
    })


@role_required('admin')
@require_POST
def admin_item_delete_view(request, pk):
    item = get_object_or_404(Item, pk=pk)
    name = item.name
    item.delete()
    messages.success(request, f'"{name}" was removed by the admin.')
    return redirect('admin_items')