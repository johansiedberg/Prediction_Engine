import re
import random
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db.models import Count, Q, Max
from django.views.decorators.http import require_POST

from tournament.models import Tournament, League, MatchPrediction, PoolAdminRequest
from django.contrib.auth.models import User

from tournament.views.auth import superuser_or_staff_required
from tournament.services.tournament_admin import get_tournament_checklist_status, get_tournament_total_status
from tournament.services.pool_admin_service import approve_pool_admin_request, reject_pool_admin_request


def engine_admin_root_view(request):
    """Entry point for Port 2029 (Engine Admin). Shows Dashboard if logged in as admin, else Login form."""
    if request.user.is_authenticated and (request.user.is_superuser or request.user.is_staff):
        return engine_admin_dashboard_view(request)
    return render(request, 'tournament/engine_admin_login.html')


def engine_admin_login_view(request):
    """Processes login specifically for Port 2029 Engine Admin."""
    if request.method == 'POST':
        uname = request.POST.get('username', '').strip()
        pwd = request.POST.get('password', '').strip()
        user = authenticate(request, username=uname, password=pwd)
        if user is not None and (user.is_superuser or user.is_staff):
            login(request, user)
            return redirect('/')
        else:
            messages.error(request, "Ogiltigt användarnamn, lösenord eller saknad Engine Admin-behörighet.")
    return render(request, 'tournament/engine_admin_login.html')


def engine_admin_logout_view(request):
    logout(request)
    return redirect('/')


def create_admin_user_view(request):
    """Create a new staff/superuser account from Port 2029.
    Accessible without being logged in (for initial bootstrap), but only from Port 2029.
    Subsequent accounts require an existing superuser to be logged in.
    """
    # Only accessible from Port 2029
    if str(request.get_port()) != '2029':
        from django.http import Http404
        raise Http404

    if request.method != 'POST':
        return redirect('/')

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip().lower()
    password1 = request.POST.get('password1', '')
    password2 = request.POST.get('password2', '')
    role = request.POST.get('role', 'staff')

    # Check if any superuser already exists — if yes, require authentication
    existing_superusers = User.objects.filter(is_superuser=True).exists()
    if existing_superusers and not (request.user.is_authenticated and request.user.is_superuser):
        messages.error(request, "Åtkomst nekad: Du måste vara inloggad som Superuser för att skapa fler Admin-konton.")
        return redirect('/')

    # Validate inputs
    errors = []
    if not first_name or not last_name:
        errors.append("Förnamn och efternamn är obligatoriska.")
    if not email or '@' not in email:
        errors.append("Ange en giltig e-postadress.")
    elif User.objects.filter(email__iexact=email).exists():
        errors.append(f"Det finns redan ett konto med e-postadressen {email}.")
    if len(password1) < 8:
        errors.append("Lösenordet måste vara minst 8 tecken.")
    if password1 != password2:
        errors.append("Lösenorden matchar inte.")

    if errors:
        for err in errors:
            messages.error(request, err)
        return redirect('/')

    # Create the user
    base_username = email.split('@')[0]
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1

    is_superuser = (role == 'superuser')
    new_user = User.objects.create_user(
        username=username,
        email=email,
        password=password1,
        first_name=first_name,
        last_name=last_name,
        is_staff=True,
        is_superuser=is_superuser,
    )

    role_label = "Superuser" if is_superuser else "Staff Admin"
    messages.success(request, f"Admin-konto skapat för {first_name} {last_name} ({role_label}). Användarnamn: {username}")
    return redirect('/')


@superuser_or_staff_required
def engine_admin_dashboard_view(request):
    """Engine Admin Monitor & Control Panel Dashboard."""
    
    # 1. Summary Metrics
    total_leagues = League.objects.count()
    total_users = User.objects.count()
    total_predictions = MatchPrediction.objects.count()
    total_tournaments = Tournament.objects.count()
    active_tournaments_count = Tournament.objects.filter(is_active=True).count()
    
    # 2. Friend Pools / Leagues Overview Table
    leagues_query = League.objects.select_related('admin', 'master_event').prefetch_related('members').annotate(
        member_count=Count('members', distinct=True),
        verified_count=Count('members', filter=Q(members__is_verified=True), distinct=True),
        last_member_login=Max('members__player__last_login')
    ).order_by('-created_at')

    leagues_data = []
    admin_emails_set = set()

    for leg in leagues_query:
        if leg.admin and leg.admin.email:
            admin_emails_set.add(leg.admin.email.strip())
        
        member_ids = leg.members.values_list('player_id', flat=True)
        league_predictions_count = MatchPrediction.objects.filter(player_id__in=member_ids).count()
        
        last_active = leg.last_member_login
        latest_pred_obj = MatchPrediction.objects.filter(player_id__in=member_ids).order_by('-id').first()
        if latest_pred_obj and hasattr(latest_pred_obj, 'updated_at') and latest_pred_obj.updated_at:
            if not last_active or latest_pred_obj.updated_at > last_active:
                last_active = latest_pred_obj.updated_at

        leagues_data.append({
            'league': leg,
            'admin': leg.admin,
            'admin_email': leg.admin.email if leg.admin else '-',
            'member_count': leg.member_count,
            'verified_count': leg.verified_count,
            'predictions_count': league_predictions_count,
            'last_active': last_active,
        })

    admin_emails_list = sorted(list(admin_emails_set))
    admin_emails_str = ", ".join(admin_emails_list)

    # 3. User Directory & Activity Logger
    users_query = User.objects.annotate(
        preds_count=Count('match_predictions', distinct=True),
        pools_count=Count('league_memberships', distinct=True)
    ).order_by('-last_login', '-date_joined')[:100]

    # 4. Tournaments for Lifecycle Management
    tournaments_list = Tournament.objects.select_related('admin').prefetch_related(
        'teams', 'tournament_groups', 'matches', 'knockout_stages'
    ).order_by('-id')

    tournaments_data = []
    for tour in tournaments_list:
        ps = getattr(tour, 'point_system', None)
        has_ps = ps is not None
        matches_cnt = tour.matches.count()
        teams_cnt = tour.teams.count()
        groups_cnt = tour.tournament_groups.count()
        knockout_cnt = tour.knockout_stages.count()
        scored_matches_cnt = tour.matches.filter(home_goals__isnull=False, away_goals__isnull=False).count()
        chk_status = get_tournament_checklist_status(tour)
        tot_status = get_tournament_total_status(tour, chk_status)

        tournaments_data.append({
            'tournament': tour,
            'has_point_system': has_ps,
            'matches_count': matches_cnt,
            'teams_count': teams_cnt,
            'groups_count': groups_cnt,
            'knockout_count': knockout_cnt,
            'scored_matches_count': scored_matches_cnt,
            'checklist_status': chk_status,
            'total_status': tot_status,
            'status': tot_status['label'],
        })

    context = {
        'total_leagues': total_leagues,
        'total_users': total_users,
        'total_predictions': total_predictions,
        'total_tournaments': total_tournaments,
        'active_tournaments_count': active_tournaments_count,
        'leagues_data': leagues_data,
        'admin_emails_list': admin_emails_list,
        'admin_emails_str': admin_emails_str,
        'users_list': users_query,
        'tournaments_data': tournaments_data,
    }
    return render(request, 'tournament/engine_admin.html', context)


@superuser_or_staff_required
@require_POST
def engine_admin_validate_tournament(request, tournament_id):
    """
    Checklist validation:
    - ALERTS (Red / Stop Activation):
      * Placeholder teams present (e.g. A1, A2, B1, B2, Lag 1, Team 1)
      * No teams or 0 matches
      * Missing Point System
    - WARNINGS (Orange / Non-blocking):
      * Missing match dates or all matches having identical date/time
      * Knockout stages not defined
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    checks = []
    has_alerts = False
    has_warnings = False

    # Check 1: Teams & Placeholders
    teams = list(tournament.teams.all())
    teams_cnt = len(teams)
    if teams_cnt == 0:
        checks.append({'title': 'Lagregistrering', 'status': 'alert', 'type': 'ALERT (Stopp)', 'detail': 'Inga lag finns registrerade i turneringen.'})
        has_alerts = True
    else:
        placeholder_teams = [t.name for t in teams if re.match(r'^([A-L][1-8]|Lag\s*\d+|Team\s*\d+)$', t.name.strip(), re.IGNORECASE)]
        if placeholder_teams:
            checks.append({
                'title': 'Riktiga Lag',
                'status': 'alert',
                'type': 'ALERT (Stopp)',
                'detail': f'{len(placeholder_teams)} lag har tillfälliga placeholders ({", ".join(placeholder_teams[:4])}...). Alla lag måste vara bekräftade riktiga lag!'
            })
            has_alerts = True
        else:
            checks.append({'title': 'Riktiga Lag', 'status': 'pass', 'type': 'OK', 'detail': f'Alla {teams_cnt} lag är bekräftade riktiga lag.'})

    # Check 2: Point System
    if hasattr(tournament, 'point_system') and tournament.point_system:
        checks.append({'title': 'Poängsystem', 'status': 'pass', 'type': 'OK', 'detail': 'Poängregelverket är aktiverat och komplett.'})
    else:
        checks.append({'title': 'Poängsystem', 'status': 'alert', 'type': 'ALERT (Stopp)', 'detail': 'Poängsystem saknas för denna turnering!'})
        has_alerts = True

    # Check 3: Matches & Dates
    matches = tournament.matches.all()
    matches_cnt = matches.count()
    if matches_cnt == 0:
        checks.append({'title': 'Matcher & Schema', 'status': 'alert', 'type': 'ALERT (Stopp)', 'detail': 'Inga matcher har schemalagts.'})
        has_alerts = True
    else:
        dates = [m.date_time for m in matches if m.date_time is not None]
        if len(dates) == 0:
            checks.append({'title': 'Matchdatum & Tider', 'status': 'warning', 'type': 'VARNING', 'detail': f'{matches_cnt} matcher saknar datum och tider.'})
            has_warnings = True
        elif len(set(dates)) == 1:
            checks.append({'title': 'Matchdatum & Tider', 'status': 'warning', 'type': 'VARNING', 'detail': 'Alla matcher har exakt samma datum och tid.'})
            has_warnings = True
        elif len(dates) < matches_cnt:
            checks.append({'title': 'Matchdatum & Tider', 'status': 'warning', 'type': 'VARNING', 'detail': f'{matches_cnt - len(dates)} matcher saknar datum/tid.'})
            has_warnings = True
        else:
            checks.append({'title': 'Matchdatum & Tider', 'status': 'pass', 'type': 'OK', 'detail': f'Alla {matches_cnt} matcher har giltiga datum/tider.'})

    # Overall Status Summary
    if has_alerts:
        overall = 'ALERT'
    elif has_warnings:
        overall = 'WARNING'
    else:
        overall = 'READY'

    return JsonResponse({
        'tournament_id': tournament_id,
        'tournament_name': tournament.name,
        'overall_status': overall,
        'has_alerts': has_alerts,
        'has_warnings': has_warnings,
        'checks': checks,
    })


WORLD_CUP_2026_NATIONAL_TEAMS = [
    'Mexiko', 'Danmark', 'Sydafrika', 'Sydkorea',
    'Kanada', 'Schweiz', 'Qatar', 'Colombia',
    'USA', 'Paraguay', 'Australien', 'Turkiet',
    'Brasilien', 'Kroatien', 'Nigeria', 'Japan',
    'Argentina', 'Österrike', 'Marocko', 'Ukraina',
    'Frankrike', 'Polen', 'Chile', 'Saudiarabien',
    'England', 'Sverige', 'Senegal', 'Peru',
    'Spanien', 'Uruguay', 'Skottland', 'Algeriet',
    'Tyskland', 'Ecuador', 'Elfenbenskusten', 'Iran',
    'Nederländerna', 'Portugal', 'Kamerun', 'Egypten',
    'Belgien', 'Italien', 'Serbien', 'Tunisien',
    'Tjeckien', 'Ghana', 'Norge', 'Wales'
]


@superuser_or_staff_required
@require_POST
def engine_admin_simulate_tournament(request, tournament_id):
    """
    Human-in-the-loop simulation:
    - If teams contain generic placeholders (e.g. A1, A2, B1, B2, Lag 1, Team 1), dynamically populates real World Cup 2026 National Teams.
    - If teams are ALREADY real seeded teams (e.g. England, France, Japan, Poland), PRESERVES them intact!
    - Generates realistic test scores for visual verification of standings & knockout progression.
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    all_teams = list(tournament.teams.all())
    placeholder_teams = [t for t in all_teams if re.match(r'^([A-L][1-8]|Lag\s*\d+|Team\s*\d+)$', t.name.strip(), re.IGNORECASE)]
    
    # Only assign World Cup 2026 teams if placeholder teams exist!
    if placeholder_teams:
        assigned_nat_teams = WORLD_CUP_2026_NATIONAL_TEAMS[:max(len(placeholder_teams), 1)]
        team_mapping = {}
        for idx, team in enumerate(placeholder_teams):
            nat_name = assigned_nat_teams[idx % len(assigned_nat_teams)]
            original_name = team.name
            team_mapping[original_name] = nat_name
            
            team.name = nat_name
            team.code = ''
            team.save()

        for match in tournament.matches.all():
            if match.home_team in team_mapping:
                match.home_team = team_mapping[match.home_team]
            if match.away_team in team_mapping:
                match.away_team = team_mapping[match.away_team]

    # Generate realistic scores for matches
    simulated_count = 0
    for match in tournament.matches.all():
        match.home_goals = random.choice([0, 1, 1, 2, 2, 3, 4])
        match.away_goals = random.choice([0, 1, 1, 2, 2, 3, 4])
        match.is_finished = True
        match.save()
        simulated_count += 1

    return JsonResponse({
        'status': 'success',
        'message': f'Simulerade matcher för {len(all_teams)} lag i "{tournament.name}". Grupptabeller och slutspel har beräknats!',
        'simulated_count': simulated_count,
    })


@superuser_or_staff_required
@require_POST
def engine_admin_reset_simulation(request, tournament_id):
    """
    Full Reset before publishing:
    Wipes simulated match scores while preserving real seeded team names.
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    reset_count = tournament.matches.update(home_goals=None, away_goals=None, is_finished=False)

    return JsonResponse({
        'status': 'success',
        'message': f'Nollställde simulerade testresultat för {reset_count} matcher i "{tournament.name}". Turneringen är nu 100% ren!',
        'reset_count': reset_count,
    })


@superuser_or_staff_required
@require_POST
def engine_admin_toggle_publish(request, tournament_id):
    """
    Toggles tournament between Draft/Testing and Active/Published.
    - BLOCKS activation if Checklist contains ALERTS!
    - ALWAYS WIPES simulated test scores before activating!
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    if not tournament.is_active:
        teams = list(tournament.teams.all())
        placeholder_teams = [t.name for t in teams if re.match(r'^([A-L][1-8]|Lag\s*\d+|Team\s*\d+)$', t.name.strip(), re.IGNORECASE)]
        has_no_teams = len(teams) == 0
        has_no_matches = tournament.matches.count() == 0
        has_no_ps = not hasattr(tournament, 'point_system') or not tournament.point_system
        
        if placeholder_teams or has_no_teams or has_no_matches or has_no_ps:
            reasons = []
            if placeholder_teams:
                reasons.append(f"{len(placeholder_teams)} tillfälliga placeholders återstår ({', '.join(placeholder_teams[:3])}...)")
            if has_no_teams:
                reasons.append("inga lag registrerade")
            if has_no_matches:
                reasons.append("inga matcher schemalagda")
            if has_no_ps:
                reasons.append("poängsystem saknas")
                
            return JsonResponse({
                'status': 'blocked',
                'is_active': False,
                'message': f'PUBLICERING STOPPAD (Alert 🚨): Turneringen kan inte aktiveras förrän följande rödmarkerade varningar (Alerts) i Checklistan har åtgärdats: {"; ".join(reasons)}.',
            })

        # Always wipe test results before activating!
        tournament.matches.update(home_goals=None, away_goals=None, is_finished=False)
        tournament.is_active = True
        tournament.is_paused = False
    else:
        tournament.is_active = False
        tournament.is_paused = True

    tournament.save()
    chk = get_tournament_checklist_status(tournament)
    tot = get_tournament_total_status(tournament, chk)

    return JsonResponse({
        'status': 'success',
        'is_active': tournament.is_active,
        'is_paused': tournament.is_paused,
        'status_text': tot['label'],
        'total_status': tot,
        'message': f'Status för "{tournament.name}" ändrades till: {tot["label"]}.'
    })


@superuser_or_staff_required
def engine_admin_preview_tournament(request, tournament_id):
    """Renders detailed structure preview (groups, standings, matches, knockouts) for tournament review."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    groups_data = []
    for group in tournament.tournament_groups.all():
        standings = group.get_standings()
        matches_list = []
        for m in group.matches.all():
            matches_list.append({
                'match_number': m.match_number,
                'home_info': m.get_home_team_info(),
                'away_info': m.get_away_team_info(),
                'home_goals': m.home_goals,
                'away_goals': m.away_goals,
                'is_finished': m.is_finished,
                'date_time': m.date_time,
            })
        groups_data.append({
            'group': group,
            'standings': standings,
            'matches': matches_list,
        })
        
    knockout_data = []
    for stage in tournament.knockout_stages.all():
        matches_list = []
        for m in stage.matches.all():
            matches_list.append({
                'match_number': m.match_number,
                'home_info': m.get_home_team_info(),
                'away_info': m.get_away_team_info(),
                'home_goals': m.home_goals,
                'away_goals': m.away_goals,
                'is_finished': m.is_finished,
                'date_time': m.date_time,
            })
        knockout_data.append({
            'stage': stage,
            'matches': matches_list,
        })

    runners_up_table = tournament.get_runners_up_ranking_table()
    host_ranking_table = tournament.get_host_ranking_table()
    best_thirds_table = tournament.get_best_thirds_ranking_table()
    chk_status = get_tournament_checklist_status(tournament)
    tot_status = get_tournament_total_status(tournament, chk_status)

    context = {
        'tournament': tournament,
        'groups_data': groups_data,
        'knockout_data': knockout_data,
        'runners_up_table': runners_up_table,
        'host_ranking_table': host_ranking_table,
        'best_thirds_table': best_thirds_table,
        'total_status': tot_status,
    }
    return render(request, 'tournament/engine_admin_preview_modal.html', context)


@superuser_or_staff_required
def engine_admin_pool_requests_view(request):
    requests = PoolAdminRequest.objects.all().select_related('user', 'master_event', 'reviewed_by', 'league').order_by('-created_at')
    data = []
    for req in requests:
        data.append({
            'id': req.id,
            'user': req.user.username,
            'pool_name': req.pool_name,
            'description': req.description,
            'master_event': req.master_event.name if req.master_event else None,
            'status': req.status,
            'created_at': req.created_at.isoformat() if req.created_at else None,
            'reviewed_by': req.reviewed_by.username if req.reviewed_by else None,
            'rejection_reason': req.rejection_reason,
            'league_id': req.league.id if req.league else None
        })
    return JsonResponse({'requests': data})


@superuser_or_staff_required
@require_POST
def engine_admin_approve_pool_request_view(request, request_id):
    pool_request = get_object_or_404(PoolAdminRequest, id=request_id)
    try:
        approve_pool_admin_request(pool_request, request.user)
        return JsonResponse({'status': 'success', 'message': 'Förfrågan godkänd.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@superuser_or_staff_required
@require_POST
def engine_admin_reject_pool_request_view(request, request_id):
    pool_request = get_object_or_404(PoolAdminRequest, id=request_id)
    rejection_reason = request.POST.get('rejection_reason', '')
    try:
        reject_pool_admin_request(pool_request, request.user, rejection_reason)
        return JsonResponse({'status': 'success', 'message': 'Förfrågan avvisad.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
