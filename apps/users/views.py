# apps/users/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import CustomUser
from .forms import UserRegistrationForm, UserLoginForm


# apps/users/views.py - Update register_view function
def register_view(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
        
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Registration successful! Please login.')
            return redirect('users:login')
        else:
            # Form will automatically show errors
            pass
    else:
        form = UserRegistrationForm()
    
    return render(request, 'users/register.html', {'form': form})


# apps/users/views.py - Use this as your login_view
def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
        
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        # SIMPLE SOLUTION: Find user and check password directly
        try:
            user = CustomUser.objects.get(email=email)
            # Check if password matches
            if user.check_password(password):
                # Manually set the backend and login
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user)
                messages.success(request, f'Welcome back, {user.email}!')
                return redirect('core:dashboard')
            else:
                messages.error(request, 'Invalid email or password.')
        except CustomUser.DoesNotExist:
            messages.error(request, 'Invalid email or password.')
    
    return render(request, 'users/login.html')


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('core:home')

@login_required
def profile_view(request):
    return render(request, 'users/profile.html', {'user': request.user})