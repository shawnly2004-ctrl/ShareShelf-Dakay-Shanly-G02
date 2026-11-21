from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from .forms import BorrowRequestForm, ItemForm, WindowFormSet
from .models import BorrowRequest, Category, HandoffConfirmation, Item, ItemPhoto


def _can_lend(user):
    return user.user_type in ('lender', 'both')


def _ensure_primary(item):
    photos = list(item.photos.order_by('uploaded_at'))
    if not photos:
        return
    primary = next((photo for photo in photos if photo.is_primary), photos[0])
    item.photos.exclude(pk=primary.pk).filter(is_primary=True).update(is_primary=False)
    if not primary.is_primary:
        primary.is_primary = True
        primary.save(update_fields=['is_primary'])


def _add_photos(item, files):
    for file in files:
        ItemPhoto.objects.create(item=item, image=file)
    _ensure_primary(item)


@role_required('member')
def my_items_view(request):
    items = (Item.objects.filter(owner=request.user)
             .select_related('category')
             .prefetch_related('photos', 'windows'))
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
    formset = WindowFormSet(request.POST or None, prefix='windows')
    if request.method == 'POST':
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                item = form.save(commit=False)
                item.owner = request.user
                item.save()
                formset.instance = item
                formset.save()
                _add_photos(item, form.cleaned_data['photos'])
            messages.success(request, f'"{item.name}" has been listed.')
            return redirect('my_items')
        messages.error(request, "Please fix the errors below.")
    return render(request, 'items/item_form.html', {
        'form': form,
        'formset': formset,
        'title': 'List a new item',
        'item': None,
    })


@login_required
def item_detail_view(request, pk):
    item = get_object_or_404(
        Item.objects.select_related('owner', 'category')
        .prefetch_related('photos', 'windows'),
        pk=pk,
    )
    is_owner = item.owner_id == request.user.id
    if (request.user.role == 'member' and not is_owner
            and item.owner.community_id != request.user.community_id):
        raise Http404
    return render(request, 'items/item_detail.html', {
        'item': item,
        'is_owner': is_owner,
    })


@role_required('member')
def item_edit_view(request, pk):
    item = get_object_or_404(
        Item.objects.prefetch_related('photos', 'windows'),
        pk=pk,
        owner=request.user,
    )
    form = ItemForm(request.POST or None, request.FILES or None, instance=item)
    formset = WindowFormSet(request.POST or None, instance=item, prefix='windows')
    if request.method == 'POST':
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
                delete_ids = request.POST.getlist('delete_photos')
                if delete_ids:
                    item.photos.filter(pk__in=delete_ids).delete()
                _add_photos(item, form.cleaned_data['photos'])
                primary_id = request.POST.get('primary_photo')
                if primary_id and item.photos.filter(pk=primary_id).exists():
                    item.photos.update(is_primary=False)
                    item.photos.filter(pk=primary_id).update(is_primary=True)
                _ensure_primary(item)
            messages.success(request, "Item updated.")
            return redirect('item_detail', pk=item.pk)
        messages.error(request, "Please fix the errors below.")
    return render(request, 'items/item_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Edit item',
        'item': item,
    })


@role_required('member')
@require_POST
def item_toggle_view(request, pk):
    item = get_object_or_404(Item, pk=pk, owner=request.user)
    if item.status == 'on_loan' or item.requests.filter(
        status__in=BorrowRequest.BLOCKING_STATUSES,
    ).exists():
        messages.error(request, "This item has an active loan and can't be unlisted.")
        return redirect('my_items')
    item.status = 'unlisted' if item.status == 'available' else 'available'
    item.save(update_fields=['status', 'updated_at'])
    state = "is now available" if item.status == 'available' else "has been unlisted"
    messages.success(request, f'"{item.name}" {state}.')
    return redirect('my_items')


@role_required('member')
@require_POST
def item_delete_view(request, pk):
    item = get_object_or_404(Item, pk=pk, owner=request.user)
    if item.status == 'on_loan' or item.requests.filter(
        status__in=BorrowRequest.BLOCKING_STATUSES,
    ).exists():
        messages.error(request, "This item has an active loan and can't be deleted.")
        return redirect('my_items')
    name = item.name
    item.delete()
    messages.success(request, f'"{name}" has been deleted.')
    return redirect('my_items')


@role_required('member')
def browse_items_view(request):
    today = timezone.localdate()
    items = (Item.objects
             .filter(
                 status='available',
                 windows__end_date__gte=today,
                 owner__community=request.user.community,
             )
             .exclude(owner=request.user)
             .select_related('owner', 'category')
             .prefetch_related('photos', 'windows')
             .distinct())

    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    on_date = parse_date(request.GET.get('date', '') or '')

    if q:
        items = items.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if category.isdigit():
        items = items.filter(category_id=int(category))
    else:
        category = ''
    if on_date and on_date >= today:
        items = items.filter(windows__start_date__lte=on_date, windows__end_date__gte=on_date)

    page_obj = Paginator(items, 9).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'items/browse_items.html', {
        'page_obj': page_obj,
        'q': q,
        'category': category,
        'date': request.GET.get('date', ''),
        'categories': Category.objects.all(),
        'querystring': params.urlencode(),
    })


@role_required('admin')
def admin_items_view(request):
    items = (Item.objects.select_related('owner', 'category')
             .prefetch_related('windows'))
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
        'page_obj': page_obj,
        'q': q,
        'querystring': params.urlencode(),
    })


@role_required('admin')
@require_POST
def admin_item_delete_view(request, pk):
    item = get_object_or_404(Item, pk=pk)
    name = item.name
    item.delete()
    messages.success(request, f'"{name}" was removed by the admin.')
    return redirect('admin_items')


@role_required('member')
def request_create_view(request, pk):
    BorrowRequest.expire_stale()
    BorrowRequest.mark_overdue()
    item = get_object_or_404(
        Item.objects.select_related('owner', 'category').prefetch_related('windows'),
        pk=pk,
    )

    if item.owner.community_id != request.user.community_id:
        raise Http404
    if item.owner_id == request.user.id:
        messages.error(request, "You can't borrow your own item.")
        return redirect('item_detail', pk=item.pk)
    if request.user.user_type == 'lender':
        messages.error(
            request,
            "Lenders can't borrow. Change your type to Borrower or Both in your profile.",
        )
        return redirect('profile_edit')
    if BorrowRequest.objects.filter(borrower=request.user, status='overdue').exists():
        messages.error(request, "You have an overdue item. Return it before requesting another.")
        return redirect('my_requests')
    if (item.status != 'available'
            or not any(window.end_date >= timezone.localdate() for window in item.windows.all())):
        messages.error(request, "This item isn't available for borrowing right now.")
        return redirect('item_detail', pk=item.pk)

    form = BorrowRequestForm(request.POST or None, item=item, borrower=request.user)
    if request.method == 'POST':
        if form.is_valid():
            borrow_request = form.save(commit=False)
            borrow_request.item = item
            borrow_request.borrower = request.user
            borrow_request.save()
            messages.success(
                request,
                f'Request sent to {item.owner.first_name} for "{item.name}".',
            )
            return redirect('my_requests')
        messages.error(request, "Please fix the errors below.")
    return render(request, 'items/request_form.html', {'form': form, 'item': item})


@role_required('member')
def my_requests_view(request):
    BorrowRequest.expire_stale()
    BorrowRequest.mark_overdue()
    requests = (BorrowRequest.objects.filter(borrower=request.user)
                .select_related('item', 'item__owner'))
    return render(request, 'items/my_requests.html', {'requests': requests})


@role_required('member')
def incoming_requests_view(request):
    BorrowRequest.expire_stale()
    BorrowRequest.mark_overdue()
    requests = (BorrowRequest.objects.filter(item__owner=request.user)
                .select_related('item', 'borrower'))
    return render(request, 'items/incoming_requests.html', {'requests': requests})


@role_required('member')
@require_POST
def request_respond_view(request, pk):
    BorrowRequest.expire_stale()
    BorrowRequest.mark_overdue()
    action = request.POST.get('action')
    if action not in ('approve', 'decline'):
        messages.error(request, "Invalid action.")
        return redirect('incoming_requests')

    with transaction.atomic():
        borrow_request = get_object_or_404(
            BorrowRequest.objects.select_related('item', 'borrower'),
            pk=pk,
            item__owner=request.user,
        )
        Item.objects.select_for_update().get(pk=borrow_request.item_id)
        borrow_request.refresh_from_db()

        if borrow_request.status != 'pending':
            messages.error(request, "This request is no longer pending.")
            return redirect('incoming_requests')

        now = timezone.now()
        if action == 'approve':
            if borrow_request.overlapping_blocking().exists():
                messages.error(
                    request,
                    "Can't approve: these dates overlap with another approved loan.",
                )
                return redirect('incoming_requests')
            borrow_request.status = 'approved'
            borrow_request.decided_at = now
            borrow_request.save(update_fields=['status', 'decided_at'])
            BorrowRequest.objects.filter(
                item=borrow_request.item,
                status='pending',
                start_date__lte=borrow_request.end_date,
                end_date__gte=borrow_request.start_date,
            ).exclude(pk=borrow_request.pk).update(status='declined', decided_at=now)
        else:
            borrow_request.status = 'declined'
            borrow_request.decided_at = now
            borrow_request.save(update_fields=['status', 'decided_at'])

    messages.success(
        request,
        f"Request from {borrow_request.borrower.first_name} was {borrow_request.status}.",
    )
    return redirect('incoming_requests')


@role_required('member')
@require_POST
def request_cancel_view(request, pk):
    borrow_request = get_object_or_404(
        BorrowRequest,
        pk=pk,
        borrower=request.user,
        status__in=['pending', 'approved'],
    )
    borrow_request.status = 'cancelled'
    borrow_request.save(update_fields=['status'])
    messages.success(request, "Your request was cancelled.")
    return redirect('my_requests')


@role_required('member')
@require_POST
def handoff_confirm_view(request, pk, handoff_type):
    if handoff_type not in ('pickup', 'return'):
        raise Http404

    BorrowRequest.expire_stale()
    BorrowRequest.mark_overdue()

    with transaction.atomic():
        borrow_request = get_object_or_404(
            BorrowRequest.objects.select_related('item', 'borrower', 'item__owner'),
            Q(item__owner=request.user) | Q(borrower=request.user),
            pk=pk,
        )
        Item.objects.select_for_update().get(pk=borrow_request.item_id)

        if handoff_type == 'pickup':
            if borrow_request.status not in ('approved', 'borrowed'):
                messages.error(request, "Pickup confirmation isn't available for this request.")
                return redirect('my_requests')
        elif borrow_request.status not in ('borrowed', 'overdue'):
            messages.error(request, "Return confirmation isn't available for this request.")
            return redirect('my_requests')

        confirmation, _ = HandoffConfirmation.objects.select_for_update().get_or_create(
            request=borrow_request,
            handoff_type=handoff_type,
        )
        now = timezone.now()

        if borrow_request.item.owner_id == request.user.id:
            confirmation.lender_confirmed_at = confirmation.lender_confirmed_at or now
        else:
            confirmation.borrower_confirmed_at = confirmation.borrower_confirmed_at or now

        if confirmation.lender_confirmed_at and confirmation.borrower_confirmed_at:
            confirmation.completed_at = confirmation.completed_at or now
        confirmation.save()

        if confirmation.completed_at:
            if handoff_type == 'pickup' and borrow_request.status == 'approved':
                borrow_request.status = 'borrowed'
                borrow_request.save(update_fields=['status'])
                borrow_request.item.status = 'on_loan'
                borrow_request.item.save(update_fields=['status', 'updated_at'])
            elif handoff_type == 'return' and borrow_request.status in ('borrowed', 'overdue'):
                borrow_request.status = 'completed'
                borrow_request.save(update_fields=['status'])
                borrow_request.item.status = 'available'
                borrow_request.item.save(update_fields=['status', 'updated_at'])

    messages.success(
        request,
        f'{handoff_type.title()} confirmation recorded.',
    )
    if borrow_request.item.owner_id == request.user.id:
        return redirect('incoming_requests')
    return redirect('my_requests')


@role_required('admin')
def admin_requests_view(request):
    BorrowRequest.expire_stale()
    BorrowRequest.mark_overdue()
    requests = BorrowRequest.objects.select_related('item', 'borrower', 'item__owner')
    status = request.GET.get('status', '')
    if status in dict(BorrowRequest.STATUS_CHOICES):
        requests = requests.filter(status=status)
    page_obj = Paginator(requests, 10).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'items/admin_requests.html', {
        'page_obj': page_obj,
        'status': status,
        'statuses': BorrowRequest.STATUS_CHOICES,
        'querystring': params.urlencode(),
    })
