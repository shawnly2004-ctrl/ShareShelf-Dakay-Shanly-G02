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
from math import atan2, cos, radians, sin, sqrt

from accounts.decorators import role_required
from .forms import (
    BorrowRequestForm,
    ItemForm,
    RatingForm,
    WishlistForm,
    WindowFormSet,
)
from .models import (
    BorrowRequest,
    Category,
    HandoffConfirmation,
    Item,
    ItemPhoto,
    Notification,
    Rating,
    Wishlist,
)


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
                Notification.match_wishlist(item)
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
    distance = request.GET.get('distance', '').strip()
    if distance.isdigit() and distance != '0':
        distance_km = int(distance)
        if request.user.latitude is not None and request.user.longitude is not None:
            in_range = []
            for item in items:
                owner = item.owner
                if owner.latitude is None or owner.longitude is None:
                    continue
                lat1, lon1 = radians(float(request.user.latitude)), radians(float(request.user.longitude))
                lat2, lon2 = radians(float(owner.latitude)), radians(float(owner.longitude))
                dlat, dlon = lat2 - lat1, lon2 - lon1
                a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
                km = 6371 * 2 * atan2(sqrt(a), sqrt(1 - a))
                if km <= distance_km:
                    in_range.append(item.pk)
            items = items.filter(pk__in=in_range)

    page_obj = Paginator(items, 9).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'items/browse_items.html', {
        'page_obj': page_obj,
        'q': q,
        'category': category,
        'date': request.GET.get('date', ''),
        'distance': request.GET.get('distance', ''),
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
            Notification.create_for_participants(
                borrow_request,
                'request_received',
                f'{request.user.first_name or request.user.email} requested "{item.name}".',
            )
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
            Notification.create_for_participants(
                borrow_request,
                'request_approved',
                f'Your request for "{borrow_request.item.name}" was approved.',
            )
            overlapping_requests = list(BorrowRequest.objects.filter(
                item=borrow_request.item,
                status='pending',
                start_date__lte=borrow_request.end_date,
                end_date__gte=borrow_request.start_date,
            ).exclude(pk=borrow_request.pk).select_related('item', 'borrower', 'item__owner'))
            for overlapping_request in overlapping_requests:
                overlapping_request.status = 'declined'
                overlapping_request.decided_at = now
                overlapping_request.save(update_fields=['status', 'decided_at'])
                Notification.create_for_participants(
                    overlapping_request,
                    'request_declined',
                    f'Your request for "{overlapping_request.item.name}" was declined.',
                )
        else:
            borrow_request.status = 'declined'
            borrow_request.decided_at = now
            borrow_request.save(update_fields=['status', 'decided_at'])
            Notification.create_for_participants(
                borrow_request,
                'request_declined',
                f'Your request for "{borrow_request.item.name}" was declined.',
            )

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
def rating_create_view(request, pk):
    borrow_request = get_object_or_404(
        BorrowRequest.objects.select_related('item', 'item__owner', 'borrower'),
        Q(item__owner=request.user) | Q(borrower=request.user),
        pk=pk,
    )
    destination = (
        'incoming_requests'
        if borrow_request.item.owner_id == request.user.id
        else 'my_requests'
    )

    if borrow_request.status != 'completed':
        messages.error(request, "Ratings can only be submitted after a completed transaction.")
        return redirect(destination)
    if Rating.objects.filter(request=borrow_request, rater=request.user).exists():
        messages.error(request, "You have already rated this transaction.")
        return redirect(destination)

    ratee = (
        borrow_request.borrower
        if borrow_request.item.owner_id == request.user.id
        else borrow_request.item.owner
    )
    form = RatingForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            rating = form.save(commit=False)
            rating.request = borrow_request
            rating.rater = request.user
            rating.ratee = ratee
            rating.save()
            Notification.create_for_user(
                ratee,
                borrow_request,
                'rating_received',
                f'You received a {rating.score}-star rating for "{borrow_request.item.name}".',
            )
            messages.success(request, "Rating submitted successfully.")
            return redirect(destination)
        messages.error(request, "Please fix the errors below.")

    return render(request, 'items/rating_form.html', {
        'form': form,
        'borrow_request': borrow_request,
        'ratee': ratee,
    })


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
                Notification.create_for_participants(
                    borrow_request,
                    'pickup_confirmed',
                    f'Pickup for "{borrow_request.item.name}" was confirmed.',
                )
            elif handoff_type == 'return' and borrow_request.status in ('borrowed', 'overdue'):
                borrow_request.status = 'completed'
                borrow_request.save(update_fields=['status'])
                borrow_request.item.status = 'available'
                borrow_request.item.save(update_fields=['status', 'updated_at'])
                Notification.create_for_participants(
                    borrow_request,
                    'return_confirmed',
                    f'Return for "{borrow_request.item.name}" was confirmed.',
                )

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


@role_required('member')
def notifications_view(request):
    BorrowRequest.expire_stale()
    BorrowRequest.mark_overdue()
    Notification.send_due_reminders()
    notifications = Notification.objects.filter(user=request.user).select_related(
        'request',
        'request__item',
    )
    return render(request, 'items/notifications.html', {
        'notifications': notifications,
        'unread_count': notifications.filter(is_read=False).count(),
    })


@role_required('member')
@require_POST
def notification_mark_read_view(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    return redirect('notifications')


@role_required('member')
@require_POST
def notifications_mark_all_read_view(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read.")
    return redirect('notifications')


@role_required('member')
def wishlists_view(request):
    if request.user.user_type == 'lender':
        messages.error(request, "Change your role to Borrower or Both to use wishlists.")
        return redirect('profile_edit')

    entries = Wishlist.objects.filter(user=request.user).select_related('category')
    form = WishlistForm(request.POST or None, user=request.user)
    if request.method == 'POST':
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(request, "Wishlist entry added.")
            return redirect('wishlists')
        messages.error(request, "Please fix the errors below.")

    return render(request, 'items/wishlists.html', {
        'entries': entries,
        'form': form,
        'active_count': entries.filter(is_active=True).count(),
    })


@role_required('member')
@require_POST
def wishlist_toggle_view(request, pk):
    entry = get_object_or_404(Wishlist, pk=pk, user=request.user)
    if entry.is_active:
        entry.is_active = False
    else:
        active_count = Wishlist.objects.filter(user=request.user, is_active=True).count()
        if active_count >= 10:
            messages.error(request, "You can have at most 10 active wishlist entries.")
            return redirect('wishlists')
        entry.is_active = True
    entry.save(update_fields=['is_active'])
    messages.success(request, "Wishlist entry updated.")
    return redirect('wishlists')


@role_required('member')
@require_POST
def wishlist_delete_view(request, pk):
    entry = get_object_or_404(Wishlist, pk=pk, user=request.user)
    entry.delete()
    messages.success(request, "Wishlist entry deleted.")
    return redirect('wishlists')
