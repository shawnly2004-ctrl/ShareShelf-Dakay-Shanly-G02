from django.contrib import messages
from django.shortcuts import render, redirect
from .forms import RegisterForm


def register_view(request):
    form = RegisterForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully! You can now log in.")
            return redirect('register')   # will change to 'login' in the next step
        messages.error(request, "Please fix the errors below.")
    return render(request, 'accounts/register.html', {'form': form})