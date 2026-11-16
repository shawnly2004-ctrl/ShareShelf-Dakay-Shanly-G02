from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from .decorators import role_required

from .forms import RegisterForm, LoginForm


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
        'recent_users': members.order_by('-date_joined')[:5],
    }
    return render(request, 'accounts/admin_dashboard.html', context)


@role_required('member')
def member_dashboard_view(request):
    return render(request, 'accounts/member_dashboard.html')