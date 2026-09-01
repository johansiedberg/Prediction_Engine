from typing import Callable, Any
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
from django.http import HttpRequest, HttpResponse, JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404

from tournament.models import (
    Tournament, Match, MatchPrediction, TournamentSubmission, Sidebet, SidebetAnswer, Group, Team,
    StaticInsight, DailyGazette, UserProfile, League, LeagueMember
)
from tournament.forms import CustomLoginForm




def _get_player_landing_url(user) -> str:
    """
    Returns the correct post-login landing URL for a player.
    - If the player has at least one saved TournamentSubmission in any active
      tournament → land on the Dashboard home tab.
    - Otherwise (no predictions saved yet) → land on the Predictions tab so
      they are immediately prompted to fill in their tips.
    """
    has_saved = TournamentSubmission.objects.filter(
        player=user,
        is_saved=True,
        tournament__is_active=True,
    ).exists()
    if has_saved:
        return '/dashboard/?tab=home'
    return '/dashboard/?tab=predictions'


class CustomLoginView(LoginView):

    template_name = 'tournament/login.html'
    form_class = CustomLoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self.request.GET.get('role', '')
        if 'pool-admin' in self.request.path or role == 'pool_admin':
            context['active_role'] = 'pool_admin'
        else:
            context['active_role'] = 'player'
        return context

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
        next_url = self.request.POST.get('next', self.request.GET.get('next', ''))
        if next_url:
            return next_url

        role = self.request.POST.get('role', self.request.GET.get('role', ''))
        user = self.request.user

        if role == 'pool_admin':
            return '/pool-admin/'

        # Check if user is primarily a pool admin without active player leagues
        is_pool_admin = League.objects.filter(admin=user).exists()
        has_player_leagues = LeagueMember.objects.filter(player=user).exists()
        if is_pool_admin and not has_player_leagues:
            return '/pool-admin/'

        return _get_player_landing_url(user)


def superuser_or_staff_required(view_func: Callable) -> Callable:
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated or not request.user.is_superuser:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', ''):
                from django.http import JsonResponse
                return JsonResponse({'status': 'error', 'message': 'Sessionen har gått ut eller saknar Engine Admin-behörighet.'}, status=401)
            if str(request.get_port()) in ['2029', '8029'] or request.META.get('HTTP_HOST', '').endswith('2029'):
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

            # Set terms accepted
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.terms_accepted = True
            profile.terms_accepted_at = timezone.now()
            profile.terms_version = "2026-08-26"
            profile.save()

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


def magic_login_view(request, token):
    """
    Passwordless login via signed one-click magic link.
    Authenticates user, sets active pool context, and initiates sequential onboarding:
    Step 1: Terms & Conditions (accept_terms) -> Step 2: Set Password (set_password) -> Dashboard.
    """
    from tournament.utils.magic_link import verify_magic_token
    payload = verify_magic_token(token)
    if not payload or not payload.get('user_id'):
        messages.error(request, "Inbjudningslänken är ogiltig eller har gått ut. Kontakta din pool-administratör.")
        return redirect('login')

    user = User.objects.filter(id=payload['user_id']).first()
    if not user:
        messages.error(request, "Användarkontot kunde inte hittas.")
        return redirect('login')

    # Authenticate and login session
    login(request, user, backend='tournament.backends.EmailAuthBackend')

    league_id = payload.get('league_id')
    if league_id:
        league = League.objects.filter(id=league_id, is_active=True).first()
        if league:
            LeagueMember.objects.get_or_create(league=league, player=user)
            request.session['active_league_id'] = league.id

    profile, _ = UserProfile.objects.get_or_create(user=user)

    # Step 1: Must review and accept full Terms & Conditions first
    if not profile.terms_accepted:
        messages.info(request, f"Välkommen {user.first_name or user.username}! Vänligen läs igenom och godkänn användaravtalet för att aktivera ditt konto.")
        return redirect('accept_terms')

    # Step 2: Set personal password
    if profile.must_set_password or not user.has_usable_password():
        messages.info(request, f"Välkommen {user.first_name or user.username}! Välj ditt lösenord för att slutföra aktiveringen.")
        return redirect('set_password')

    messages.success(request, f"Välkommen tillbaka, {user.first_name or user.username}!")
    return redirect(_get_player_landing_url(user))


def terms_view(request):
    """
    Publicly accessible Terms and Conditions view (Användaravtal).
    """
    return render(request, 'tournament/terms.html')


@login_required
def accept_terms_view(request):
    """
    Step 1 of Onboarding: Review full Terms & Conditions on screen and scroll to accept.
    Once accepted, advances directly to Step 2: Set Password (if password is required), else Dashboard.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        accept = request.POST.get('accept_terms')
        if not accept:
            messages.error(request, "Du måste godkänna Användaravtalet för att fortsätta.")
            return render(request, 'tournament/terms.html', {'require_acceptance': True})

        profile.terms_accepted = True
        profile.terms_accepted_at = timezone.now()
        profile.terms_version = "2026-08-26"
        profile.save()

        messages.success(request, "Tack! Du har godkänt Användaravtalet.")

        # If user still needs to choose their password, advance to Step 2
        if profile.must_set_password or not request.user.has_usable_password():
            return redirect('set_password')

        next_url = request.POST.get('next', request.GET.get('next', ''))
        return redirect(next_url or _get_player_landing_url(request.user))

    if profile.terms_accepted:
        if profile.must_set_password or not request.user.has_usable_password():
            return redirect('set_password')
        return redirect(_get_player_landing_url(request.user))

    return render(request, 'tournament/terms.html', {'require_acceptance': True})


@login_required
def set_password_view(request):
    """
    Step 2 of Onboarding: Mandatory first-time password setup for invited users.
    Terms & Conditions have already been accepted in Step 1.
    """
    from django.contrib.auth import update_session_auth_hash

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        if not password:
            messages.error(request, "Vänligen ange ett lösenord.")
            return render(request, 'tournament/set_password.html', {'profile': profile})

        if len(password) < 4:
            messages.error(request, "Lösenordet måste innehålla minst 4 tecken.")
            return render(request, 'tournament/set_password.html', {'profile': profile})

        if password != confirm_password:
            messages.error(request, "Lösenorden matchar inte varandra.")
            return render(request, 'tournament/set_password.html', {'profile': profile})

        # Save new password
        request.user.set_password(password)
        request.user.save()

        profile.must_set_password = False
        profile.save()

        # Keep user logged in with updated password hash
        update_session_auth_hash(request, request.user)

        messages.success(request, "Ditt lösenord har sparats! Välkommen till mästerskapstipset.")
        return redirect(_get_player_landing_url(request.user))

    return render(request, 'tournament/set_password.html', {
        'profile': profile,
    })


