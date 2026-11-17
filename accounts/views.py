from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from .decorators import role_required
from .forms import RegisterForm, LoginForm, ProfileForm
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .forms import RegisterForm, LoginForm
from django.utils import timezone
from items.models import Item


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = RegisterForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully! You can now log in.")
            return redirect('login')
        messages.error(request, "Please fix the errors below.")
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.first_name or user.email}!")

            # Send the user back to the page they originally wanted (if safe)
            next_url = request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('dashboard')
        messages.error(request, "Invalid email or password.")
    return render(request, 'accounts/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)   # ends the session
    messages.success(request, "You have been logged out.")
    return redirect('login')


@login_required
def dashboard_view(request):
    """Router: sends each user to the dashboard for their role."""
    if request.user.role == 'admin':
        return redirect('admin_dashboard')
    return redirect('member_dashboard')


@role_required('admin')
def admin_dashboard_view(request):
    User = get_user_model()
    members = User.objects.filter(role='member')
    context = {
        'total_users': members.count(),
        'lenders': members.filter(user_type__in=['lender', 'both']).count(),
        'borrowers': members.filter(user_type__in=['borrower', 'both']).count(),
        'total_items': Item.objects.count(),
        'recent_users': members.order_by('-date_joined')[:5],
        'recent_items': Item.objects.select_related('owner', 'category')[:5],
    }
    return render(request, 'accounts/admin_dashboard.html', context)


@role_required('member')
def member_dashboard_view(request):
    today = timezone.localdate()
    my_items = Item.objects.filter(owner=request.user)
    nearby = (Item.objects
              .filter(
                  status='available',
                  windows__end_date__gte=today,
                  owner__community=request.user.community,
              )
              .exclude(owner=request.user)
              .select_related('owner')
              .prefetch_related('photos')
              .distinct()[:6])
    return render(request, 'accounts/member_dashboard.html', {
        'my_items_count': my_items.count(),
        'my_active_count': my_items.filter(
            status='available',
            windows__start_date__lte=today,
            windows__end_date__gte=today,
        ).distinct().count(),
        'nearby_items': nearby,
    })

@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html')


@login_required
def profile_edit_view(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('profile')
        messages.error(request, "Please fix the errors below.")
    return render(request, 'accounts/profile_edit.html', {'form': form})


@role_required('admin')
def manage_users_view(request):
    User = get_user_model()
    users = User.objects.filter(role='member').order_by('-date_joined')

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    user_type = request.GET.get('type', '')

    if q:
        users = users.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(email__icontains=q) | Q(community__name__icontains=q)
        )
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)
    if user_type in ('lender', 'borrower', 'both'):
        users = users.filter(user_type=user_type)

    page_obj = Paginator(users, 10).get_page(request.GET.get('page'))

    # Keep the search/filters when moving between pages
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'accounts/manage_users.html', {
        'page_obj': page_obj,
        'q': q,
        'status': status,
        'user_type': user_type,
        'querystring': params.urlencode(),
    })


@role_required('admin')
@require_POST
def toggle_user_status_view(request, user_id):
    User = get_user_model()
    # Only members can be targeted, so an admin can't deactivate themselves or other admins
    target = get_object_or_404(User, pk=user_id, role='member')
    target.is_active = not target.is_active
    target.save(update_fields=['is_active'])

    state = "activated" if target.is_active else "deactivated"
    messages.success(request, f"{target.email} has been {state}.")
    return redirect('manage_users')