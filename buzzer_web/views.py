from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from .models import Team

@ensure_csrf_cookie
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and user.is_staff:
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('home')
        return render(request, 'login.html', {'error': 'Invalid username or password'})
    
    response = render(request, 'login.html')
    response.set_cookie('csrftoken', request.META.get('CSRF_COOKIE', ''), samesite='Lax')
    return response

def logout_view(request):
    logout(request)
    return render(request, 'logout_success.html')

@login_required
def admin_view(request):
    if not request.user.is_staff:
        return redirect('/')
    teams = Team.objects.all()
    return render(request, 'admin.html', {'teams': teams})

def buzzer_view(request):
    teams = Team.objects.all()
    return render(request, 'buzzer.html', {'teams': teams})

def about_view(request):
    return render(request, 'about.html')
