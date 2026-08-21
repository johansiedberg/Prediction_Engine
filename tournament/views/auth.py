# Auth views - Login, Logout, and permission decorators
import datetime
import calendar
import json
import random
import re
from functools import wraps
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Max, Q
from django.conf import settings
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404

from tournament.models import (
    Tournament, Match, MatchPrediction, TournamentSubmission, Sidebet, SidebetAnswer, Group, Team,
    StaticInsight, DailyGazette, UserProfile, League, LeagueMember
)
from tournament.forms import CustomLoginForm


class CustomLoginView(LoginView):
    template_name = 'tournament/login.html'
    form_class = CustomLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        invite_code = self.request.POST.get('invite_code', '').strip().upper()
        if invite_code:
            league = League.objects.filter(invite_code__iexact=invite_code, is_active=True).first()
            if league:
                LeagueMember.objects.get_or_create(league=league, player=user)
                self.request.session['active_league_id'] = league.id
                messages.success(self.request, f"Välkommen till tipsgruppen {league.name}!")
            else:
                messages.warning(self.request, f"Koden '{invite_code}' hittades inte, men du loggades in.")
        return response

    def get_success_url(self):
        return '/dashboard/?tab=predictions'


def superuser_or_staff_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.username != 'johansiedberg' or not request.user.is_superuser:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', ''):
                from django.http import JsonResponse
                return JsonResponse({'status': 'error', 'message': 'Sessionen har gått ut eller saknar Engine Admin-behörighet.'}, status=401)
            if str(request.get_port()) == '2029':
                from tournament.views.engine_admin import engine_admin_root_view
                return engine_admin_root_view(request)
            messages.error(request, "Åtkomst nekad: Endast det dedikerade Engine Admin-systemkontot har behörighet.")
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def register_view(request):
    """Self-service account registration for players and Pool-Admin applicants."""
    from tournament.forms import UserRegistrationForm

    if request.user.is_authenticated:
        return redirect('hub')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            first_name = form.cleaned_data['first_name'].strip()
            last_name = form.cleaned_data['last_name'].strip()
            email = form.cleaned_data['email']
            password = form.cleaned_data['password1']
            invite_code = form.cleaned_data.get('invite_code', '').strip().upper()

            # Unique ID is the email address
            username = email.lower()
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

            # Auto-join league if invite code provided
            if invite_code:
                league = League.objects.filter(invite_code__iexact=invite_code, is_active=True).first()
                if league:
                    LeagueMember.objects.get_or_create(league=league, player=user)
                    request.session['active_league_id'] = league.id
                    messages.success(request, f"Välkommen till tipsgruppen {league.name}!")
                else:
                    messages.warning(request, f"Koden '{invite_code}' hittades inte, men ditt konto skapades.")

            # Auto-login after registration
            login(request, user, backend='tournament.backends.EmailAuthBackend')
            messages.success(request, f"Välkommen, {first_name}! Ditt konto är skapat.")
            return redirect('/hub/')
    else:
        # Pre-fill invite code from URL parameter (e.g. /register/?code=ENGINE8)
        initial_code = request.GET.get('code', '').upper()
        form = UserRegistrationForm(initial={'invite_code': initial_code})

    return render(request, 'tournament/register.html', {'form': form})


from django.http import HttpResponseBadRequest
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature

def sso_login_view(request):
    token = request.GET.get('token')
    if not token:
        return HttpResponseBadRequest("Missing token parameter.")
    
    signer = TimestampSigner(key=settings.HERRKLUBB_SSO_SECRET, salt='sso-salt')
    try:
        # Verify token signature and enforce max_age of 60 seconds
        payload = signer.unsign_object(token, max_age=60)
    except (SignatureExpired, BadSignature):
        return HttpResponseBadRequest("SSO link has expired or is invalid.")
    
    email = payload.get('email', '').strip().lower()
    first_name = payload.get('first_name', '')
    last_name = payload.get('last_name', '')
    
    if not email:
        return HttpResponseBadRequest("Invalid payload: email is required.")
    
    # Retrieve user by email or create them dynamically
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        # Note: Signals in models.py will auto-create UserProfile and enroll them in active tournaments
    
    # Standard Django login session hook
    user.backend = 'tournament.backends.EmailAuthBackend'
    login(request, user)
    
    return redirect('hub')

