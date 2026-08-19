import re
import random
import json

import logging
from django.db import transaction, models
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404

logger = logging.getLogger(__name__)

from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db.models import Count, Q, Max, F
from django.views.decorators.http import require_POST
from django.utils import timezone

from tournament.models import (
    Tournament, League, LeagueMember, MatchPrediction, PoolAdminRequest, ScannedTournament,
    PointSystem, Sidebet
)
from django.contrib.auth.models import User

from tournament.views.auth import superuser_or_staff_required
from tournament.services.tournament_admin import get_tournament_checklist_status, get_tournament_total_status
from tournament.services.pool_admin_service import approve_pool_admin_request, reject_pool_admin_request
from tournament.services.cache_service import invalidate_tournament_cache
from tournament.services.scout_service import (
    parse_and_save_scouted_json, convert_scanned_to_live_tournament, scrape_web_for_tournaments
)


def engine_admin_root_view(request):
    """Entry point for Port 2029 (Engine Admin). Shows Dashboard if logged in as admin, else Login form."""
    if request.user.is_authenticated and (request.user.is_superuser or request.user.is_staff):
        return engine_admin_dashboard_view(request)
    return render(request, 'tournament/engine_admin_login.html')


def engine_admin_login_view(request):
    """Processes login specifically for Port 2029 Engine Admin."""
    if request.method == 'POST':
        login_input = request.POST.get('email', '').strip() or request.POST.get('username', '').strip()
        pwd = request.POST.get('password', '').strip()
        user = authenticate(request, username=login_input, password=pwd)
        if user is None:
            user_obj = User.objects.filter(email__iexact=login_input).first()
            if user_obj:
                user = authenticate(request, username=user_obj.username, password=pwd)
        if user is not None and (user.is_superuser or user.is_staff):
            login(request, user)
            return redirect('/')
        else:
            messages.error(request, "Felaktig e-postadress, lösenord eller saknad Engine Admin-behörighet.")
    return render(request, 'tournament/engine_admin_login.html')


def engine_admin_logout_view(request):
    logout(request)
    return redirect('/')


def create_admin_user_view(request):
    """Admin creation via HTTP endpoint is disabled.
    Engine Admin credentials are managed strictly in the Python codebase (seed_members management command).
    """
    from django.http import HttpResponseForbidden
    return HttpResponseForbidden("Admin account creation via HTTP is disabled. Admin accounts are managed strictly via Python codebase.")


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
            'admin_name': (leg.admin.get_full_name() or leg.admin.email) if leg.admin else '-',
            'admin_email': leg.admin.email if leg.admin else '-',
            'tournament_name': leg.master_event.name if leg.master_event else '-',
            'member_count': leg.member_count,
            'verified_count': leg.verified_count,
            'predictions_count': league_predictions_count,
            'last_active': last_active,
        })

    admin_emails_list = sorted(list(admin_emails_set))
    admin_emails_str = ", ".join(admin_emails_list)

    # 3. Player Directory & Activity Logger (Connecting Pool to Player, multiple rows per pool membership)
    player_rows = []
    memberships = LeagueMember.objects.select_related('league', 'player', 'league__admin', 'league__master_event').order_by('-player__last_login', '-joined_at')
    
    users_with_pools = set()
    for m in memberships:
        users_with_pools.add(m.player_id)
        tour_id = m.league.master_event_id if m.league and m.league.master_event else None
        if tour_id:
            preds_cnt = MatchPrediction.objects.filter(player=m.player, match__tournament_id=tour_id).count()
        else:
            preds_cnt = MatchPrediction.objects.filter(player=m.player).count()

        player_rows.append({
            'player': m.player,
            'player_name': m.player.get_full_name() or m.player.email,
            'player_email': m.player.email,
            'league': m.league,
            'league_name': m.league.name if m.league else '-',
            'admin': m.league.admin if m.league else None,
            'admin_name': (m.league.admin.get_full_name() or m.league.admin.email) if (m.league and m.league.admin) else '-',
            'admin_email': m.league.admin.email if (m.league and m.league.admin) else '-',
            'tournament_name': m.league.master_event.name if (m.league and m.league.master_event) else '-',
            'is_verified': m.is_verified,
            'joined_at': m.joined_at,
            'last_login': m.player.last_login,
            'predictions_count': preds_cnt,
        })

    standalone_users = User.objects.exclude(id__in=users_with_pools).order_by('-last_login', '-date_joined')
    for u in standalone_users:
        preds_cnt = MatchPrediction.objects.filter(player=u).count()
        player_rows.append({
            'player': u,
            'player_name': u.get_full_name() or u.email,
            'player_email': u.email,
            'league': None,
            'league_name': '-',
            'admin': None,
            'admin_name': '-',
            'admin_email': '-',
            'tournament_name': '-',
            'is_verified': False,
            'joined_at': u.date_joined,
            'last_login': u.last_login,
            'predictions_count': preds_cnt,
        })

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

        pools_for_tour = League.objects.filter(tournaments=tour)
        pools_cnt = pools_for_tour.count()
        pool_names_str = ", ".join([p.name for p in pools_for_tour]) if pools_cnt > 0 else '-'
        tour_players_cnt = LeagueMember.objects.filter(league__tournaments=tour).values('player_id').distinct().count()
        tour_preds_cnt = MatchPrediction.objects.filter(match__tournament=tour).count()

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
            'pools_count': pools_cnt,
            'pool_names_str': pool_names_str,
            'tour_players_count': tour_players_cnt,
            'tour_preds_count': tour_preds_cnt,
        })

    # 5. AI Tournament Scout Prospects (Sorted nearest in time first)
    scanned_list = ScannedTournament.objects.select_related('converted_tournament').order_by(
        F('start_date').asc(nulls_last=True), '-created_at'
    )
    scanned_data = []
    scout_counts = {
        'total': 0,
        'new': 0,
        'ready': 0,
        'watchlist': 0,
        'not_ready': 0,
        'archived': 0,
        'converted': 0,
    }

    SPORT_ICONS = {
        'football': '⚽',
        'soccer': '⚽',
        'ice hockey': '🏒',
        'ishockey': '🏒',
        'hockey': '🏒',
        'floorball': '🏑',
        'innebandy': '🏑',
        'handball': '🤾',
        'handboll': '🤾',
        'rugby': '🏉',
        'basketball': '🏀',
        'basket': '🏀',
        'water polo': '🤽',
        'volleyball': '🏐',
    }

    today = timezone.localdate()

    for p in scanned_list:
        payload = p.payload or {}
        audit = payload.get('scouting_audit', {})
        scouting_stage = audit.get('scouting_stage', 'DEEP')  # Legacy prospects treated as DEEP

        # Compute Unified Status (combining Status + Grade)
        if p.status == 'CONVERTED':
            unified_status = 'CONVERTED'
        elif p.status == 'WATCHLIST':
            unified_status = 'WATCHLIST'
        elif p.status == 'ARCHIVED':
            unified_status = 'ARCHIVED'
        elif scouting_stage == 'SHALLOW':
            unified_status = 'NEW'
        elif p.completeness_grade == 'GRADE_A':
            unified_status = 'READY'
        else:
            unified_status = 'NOT_READY'

        scout_counts['total'] += 1
        if unified_status == 'CONVERTED':
            scout_counts['converted'] += 1
        elif unified_status == 'WATCHLIST':
            scout_counts['watchlist'] += 1
        elif unified_status == 'ARCHIVED':
            scout_counts['archived'] += 1
        elif unified_status == 'NEW':
            scout_counts['new'] += 1
        elif unified_status == 'READY':
            scout_counts['ready'] += 1
        elif unified_status == 'NOT_READY':
            scout_counts['not_ready'] += 1
        groups = payload.get('groups', [])
        fixtures = payload.get('fixtures_sample', [])
        knockouts = payload.get('knockout_mapping_sample', [])
        sidebets = payload.get('sidebets_suggestions', [])
        
        teams_count = sum(len(g.get('teams', [])) for g in groups) or payload.get('tournament_config', {}).get('total_teams', 0)
        groups_count = len(groups)
        matches_count = len(fixtures) + len(knockouts)
        sidebets_count = len(sidebets)

        sport_clean = (p.sport or '').lower().strip()
        allsport_emoji = payload.get('raw_allsportdb', {}).get('emoji')
        icon = allsport_emoji or SPORT_ICONS.get(sport_clean, '🏆')

        days_to_start = None
        if p.start_date:
            days_to_start = (p.start_date - today).days

        # AGENTS.md Monochromatic Tonal Contrast — Grade Badges
        # Surface: 950 deep, Border: 700 mid-dark, Text: 100 pale tint, Icon: fa-solid
        grade_meta = {
            'GRADE_A': {
                'label': 'Redo',
                'icon':  'fa-shield-check',
                'style': 'background:#052E16;border:1px solid #15803D;color:#DCFCE7;',
            },
            'GRADE_B': {
                'label': 'Bevakas',
                'icon':  'fa-eye',
                'style': 'background:#082F49;border:1px solid #0284C7;color:#BAE6FD;',
            },
            'GRADE_C': {
                'label': 'Inte redo',
                'icon':  'fa-circle-info',
                'style': 'background:#451A03;border:1px solid #D97706;color:#FEF3C7;',
            },
            'GRADE_D': {
                'label': 'Ej kompatibel',
                'icon':  'fa-circle-xmark',
                'style': 'background:#1c0404;border:1px solid #7f1d1d;color:#fecaca;',
            },
        }.get(p.completeness_grade, {
            'label': p.completeness_grade,
            'icon':  'fa-circle-question',
            'style': 'background:#1e293b;border:1px solid #475569;color:#cbd5e1;',
        })


        status_meta = {
            'NEW': {'label': 'Nytt Prospekt', 'badge_class': 'bg-primary text-white', 'icon': 'fa-sparkles'},
            'WATCHLIST': {'label': 'Bevakas (Survey)', 'badge_class': 'bg-info text-dark', 'icon': 'fa-eye'},
            'CONVERTED': {'label': 'Skapad / Live', 'badge_class': 'bg-success text-white', 'icon': 'fa-circle-check'},
            'ARCHIVED': {'label': 'Ignorerad', 'badge_class': 'bg-secondary text-white', 'icon': 'fa-ban'},
        }.get(p.status, {'label': p.status, 'badge_class': 'bg-secondary text-white', 'icon': 'fa-question'})

        audit = payload.get('scouting_audit', {})
        grade_reason = p.grade_reason or audit.get('grade_reason') or ''
        missing_items = audit.get('missing_items', [])
        action_needed = audit.get('action_needed', '')

        if not missing_items:
            if p.completeness_grade == 'GRADE_B':
                missing_items = [
                    "Exakta matchtider/klockslag saknas eller är preliminära",
                    "Vissa deltagande lag/playoff-platser inväntar kvalificering"
                ]
            elif p.completeness_grade == 'GRADE_C':
                missing_items = [
                    "Officiell lottning ej genomförd",
                    "Spelschema och matchdatum ej fastställda",
                    "Deltagande lag ej klara"
                ]
            elif p.completeness_grade == 'GRADE_D':
                missing_items = [
                    "Sporttypen eller turneringsstrukturen saknar 1X2-/tabellmekanik",
                    "Turneringen har redan passerat eller avbrutits"
                ]

        is_grade_a = (p.completeness_grade == 'GRADE_A')
        draw_done = bool(audit.get('draw_completed', False) or is_grade_a or (groups_count > 0 and teams_count > 0))
        fixtures_done = bool(audit.get('fixtures_completed', False) or is_grade_a or matches_count > 0)
        scheduled_matchdays = int(audit.get('scheduled_matchdays', 0))
        fixtures_have_placeholders = bool(audit.get('fixtures_have_placeholders', False))
        scouting_stage = audit.get('scouting_stage', 'DEEP')  # Legacy prospects treated as DEEP

        readiness = {
            'draw_completed': draw_done,
            'schedule_ready': fixtures_done,
        }

        # Override missing_items for SHALLOW prospects or Grade A
        if scouting_stage == 'SHALLOW':
            missing_items = []  # No bullet points — card shows "Inväntar djupscanning" block instead
        elif is_grade_a:
            missing_items = []  # Grade A has 100% readiness, no missing items

        official_rules_val = p.official_rules or audit.get('official_rules') or audit.get('advancement_rules') or ''

        import urllib.parse
        wiki_url_val = (
            payload.get('master_event', {}).get('wikipedia_url')
            or audit.get('wikipedia_url')
            or (p.official_source_url if p.official_source_url and 'wikipedia.org' in p.official_source_url else '')
            or f"https://en.wikipedia.org/wiki/{urllib.parse.quote((audit.get('wikipedia_title') or p.name).replace(' ', '_'))}"
        )

        scanned_data.append({
            'prospect': p,
            'unified_status': unified_status,
            'teams_count': teams_count,
            'groups_count': groups_count,
            'matches_count': matches_count,
            'sidebets_count': sidebets_count,
            'sport_icon': icon,
            'days_to_start': days_to_start,
            'grade_meta': grade_meta,
            'status_meta': status_meta,
            'grade_reason': grade_reason,
            'missing_items': missing_items,
            'action_needed': action_needed,
            'official_source_url': p.official_source_url or payload.get('master_event', {}).get('official_source_url') or '',
            'wikipedia_url': wiki_url_val,
            'official_rules': official_rules_val,
            'draw_done': draw_done,
            'fixtures_done': fixtures_done,
            'readiness': readiness,
            'scheduled_matchdays': scheduled_matchdays,
            'fixtures_have_placeholders': fixtures_have_placeholders,
            'scouting_stage': scouting_stage,
            'groups': groups,
            'fixtures': fixtures,
            'knockouts': knockouts,
            'sidebets': sidebets,
            'raw_json': json.dumps(payload, ensure_ascii=False, indent=2),
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
        'player_rows': player_rows,
        'tournaments_data': tournaments_data,
        'scanned_tournaments': scanned_data,
        'scout_counts': scout_counts,
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


EURO_2028_EUROPEAN_TEAMS = [
    'Spanien', 'Frankrike', 'England', 'Belgien', 'Nederländerna', 'Portugal',
    'Italien', 'Kroatien', 'Tyskland', 'Danmark', 'Turkiet', 'Sverige',
    'Tjeckien', 'Grekland', 'Skottland', 'Wales', 'Polen', 'Ungern',
    'Ukraina', 'Österrike', 'Schweiz', 'Serbien', 'Slovakien', 'Norge',
    'Georgien', 'Irland', 'Nordmakedonien', 'Montenegro', 'Albanien', 'Armenien',
    'Island', 'Bosnien och Hercegovina', 'Slovenien', 'Bulgarien', 'Finland', 'Nordirland',
    'Cypern', 'Gibraltar', 'Malta', 'Färöarna', 'Andorra', 'San Marino',
    'Azerbajdzjan', 'Kazakstan', 'Kosovo', 'Luxemburg', 'Lettland', 'Rumänien',
    'Liechtenstein', 'Moldavien', 'Belarus', 'Litauen', 'Estland', 'Israel'
]


@superuser_or_staff_required
@require_POST
def engine_admin_simulate_tournament(request, tournament_id):
    """
    Human-in-the-loop simulation:
    - If teams contain generic placeholders (e.g. A1, A2, B1, B2, Lag 1, Team 1), dynamically populates real National Teams (UEFA teams for Euro tournaments, World Cup teams otherwise).
    - If teams are ALREADY real seeded teams (e.g. England, France, Japan, Poland), PRESERVES them intact!
    - Generates realistic test scores for visual verification of standings & knockout progression.
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    all_teams = list(tournament.teams.all())
    placeholder_teams = [t for t in all_teams if re.match(r'^([A-L][1-8]|Lag\s*\d+|Team\s*\d+)$', t.name.strip(), re.IGNORECASE)]
    
    # Dynamically select nation team pool
    if 'euro' in tournament.name.lower():
        available_pool = EURO_2028_EUROPEAN_TEAMS
    else:
        available_pool = WORLD_CUP_2026_NATIONAL_TEAMS

    # Only assign national teams if placeholder teams exist!
    if placeholder_teams:
        assigned_nat_teams = available_pool[:max(len(placeholder_teams), 1)]
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

    invalidate_tournament_cache(tournament.id)

    return JsonResponse({
        'status': 'success',
        'message': f'Simulerade matcher för {len(all_teams)} lag i "{tournament.name}". Grupptabeller och slutspel har beräknats!',
        'simulated_count': simulated_count,
    })


@superuser_or_staff_required
@require_POST
def engine_admin_reset_simulation(request, tournament_id):
    """
    Full Reset:
    - Resets all teams back to their official pre-draw group placeholders (e.g. A1, A2, B1, G5, etc.).
    - Updates group match home/away team names back to the corresponding placeholders.
    - Wipes all simulated match scores and finishes.
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    # 1. Reset Teams to Group Placeholders (A1, A2, B1, B2...)
    groups = tournament.tournament_groups.all().order_by('order', 'id')
    team_mapping = {}
    total_teams_reset = 0

    for g_idx, group in enumerate(groups):
        parts = group.name.strip().split()
        if parts and len(parts[-1]) == 1 and parts[-1].isalpha():
            letter = parts[-1].upper()
        else:
            letter = chr(ord('A') + g_idx)
        
        group_teams = list(group.teams.all().order_by('id'))
        for t_idx, team in enumerate(group_teams):
            old_name = team.name
            placeholder_name = f"{letter}{t_idx + 1}"
            team_mapping[old_name] = placeholder_name
            
            team.name = placeholder_name
            team.code = ''
            team.save()
            total_teams_reset += 1

    # 2. Reset Matches: restore placeholder names in group fixtures & wipe scores
    reset_matches_count = 0
    for match in tournament.matches.all():
        if match.home_team in team_mapping:
            match.home_team = team_mapping[match.home_team]
        if match.away_team in team_mapping:
            match.away_team = team_mapping[match.away_team]
        
        match.home_goals = None
        match.away_goals = None
        match.is_finished = False
        match.box_score_data = {}
        match.save()
        reset_matches_count += 1

    invalidate_tournament_cache(tournament.id)

    return JsonResponse({
        'status': 'success',
        'message': f'Nollställde simulerade testresultat för {reset_matches_count} matcher och återställde {total_teams_reset} lag till korrekta placeholders i "{tournament.name}".',
        'reset_count': reset_matches_count,
        'teams_reset_count': total_teams_reset,
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
    invalidate_tournament_cache(tournament.id)
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
@require_POST
def engine_admin_delete_tournament_view(request, tournament_id):
    """Permanently deletes a live Tournament and all associated matches, predictions, and rules from Engine Admin."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    name = tournament.name
    
    # Detach any linked ScannedTournament prospect so it can be re-converted or scouted if needed
    ScannedTournament.objects.filter(converted_tournament=tournament).update(
        converted_tournament=None,
        status='NEW'
    )
    
    tournament.delete()
    
    return JsonResponse({
        'status': 'success',
        'message': f'Turneringen "{name}" (#{tournament_id}) raderades permanent!'
    })



@superuser_or_staff_required
def engine_admin_pool_requests_view(request):
    requests = PoolAdminRequest.objects.all().select_related('user', 'master_event', 'reviewed_by', 'league').order_by('-created_at')
    data = []
    for req in requests:
        data.append({
            'id': req.id,
            'user': req.user.get_full_name() or req.user.email,
            'user_email': req.user.email,
            'pool_name': req.pool_name,
            'description': req.description,
            'master_event': req.master_event.name if req.master_event else None,
            'status': req.status,
            'created_at': req.created_at.isoformat() if req.created_at else None,
            'reviewed_by': (req.reviewed_by.get_full_name() or req.reviewed_by.email) if req.reviewed_by else None,
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


@superuser_or_staff_required
@require_POST
def engine_admin_update_tournament(request, tournament_id):
    """Updates tournament name, logotype (icon), and backdrop banner."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    name = request.POST.get('name', '').strip()
    if not name:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'status': 'error', 'message': 'Turneringsnamnet kan inte vara tomt.'}, status=400)
        messages.error(request, 'Turneringsnamnet kan inte vara tomt.')
        return redirect('/engine-admin/')

    tournament.name = name

    # Handle Icon / Logotype
    clear_icon = request.POST.get('clear_icon') in ['true', '1', 'on']
    if clear_icon:
        if tournament.icon:
            tournament.icon.delete(save=False)
        tournament.icon = None
    elif 'icon' in request.FILES:
        tournament.icon = request.FILES['icon']

    # Handle Backdrop Banner
    clear_backdrop = request.POST.get('clear_backdrop') in ['true', '1', 'on']
    if clear_backdrop:
        if tournament.backdrop:
            tournament.backdrop.delete(save=False)
        tournament.backdrop = None
    elif 'backdrop' in request.FILES:
        tournament.backdrop = request.FILES['backdrop']

    tournament.save()
    invalidate_tournament_cache(tournament.id)

    icon_url = tournament.icon.url if tournament.icon else None
    backdrop_url = tournament.backdrop.url if tournament.backdrop else None

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '') or request.POST.get('ajax') == '1':
        return JsonResponse({
            'status': 'success',
            'message': f'Turneringen "{tournament.name}" har sparats!',
            'tournament': {
                'id': tournament.id,
                'name': tournament.name,
                'icon_url': icon_url,
                'backdrop_url': backdrop_url,
            }
        })

    messages.success(request, f'Turneringen "{tournament.name}" har sparats!')
    return redirect('/engine-admin/')


# --- AI Tournament Scout Endpoints ---

@superuser_or_staff_required
@require_POST
def scout_import_json_view(request):
    """Imports or updates a ScannedTournament from JSON payload."""
    try:
        raw_data = request.POST.get('json_data')
        if not raw_data and request.body:
            try:
                body_json = json.loads(request.body.decode('utf-8'))
                raw_data = body_json.get('json_data') if isinstance(body_json, dict) else request.body.decode('utf-8')
            except Exception:
                raw_data = request.body.decode('utf-8')

        if not raw_data:
            return JsonResponse({'status': 'error', 'message': 'Ingen JSON-data mottogs.'}, status=400)

        payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        scanned_obj, created, error = parse_and_save_scouted_json(payload)

        if error:
            return JsonResponse({'status': 'error', 'message': error}, status=400)

        verb = 'importerades som nytt prospekt' if created else 'uppdaterades'
        return JsonResponse({
            'status': 'success',
            'message': f'"{scanned_obj.name}" {verb} ({scanned_obj.completeness_grade})!',
            'prospect': {
                'id': scanned_obj.id,
                'name': scanned_obj.name,
                'grade': scanned_obj.completeness_grade,
                'status': scanned_obj.status,
            }
        })
    except json.JSONDecodeError as jde:
        return JsonResponse({'status': 'error', 'message': f'Ogiltig JSON: {str(jde)}'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Ett fel uppstod: {str(e)}'}, status=500)


@superuser_or_staff_required
@require_POST
def scout_import_wikipedia_view(request):
    """
    Stage 1 Shallow Import: imports a tournament prospect from a Wikipedia URL,
    extracting ONLY the infobox metadata (name, host, team count, dates) WITHOUT
    running the full deep Wikipedia audit. Saves with scouting_stage='SHALLOW'
    and grade GRADE_C. User triggers Stage 2 via the per-card 'Djupscanna' button.
    """
    try:
        wiki_url = request.POST.get('wikipedia_url', '').strip()
        if not wiki_url:
            return JsonResponse({'status': 'error', 'message': 'Ange en giltig Wikipedia URL.'}, status=400)

        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.scout_service import parse_and_save_scouted_json
        import datetime

        wiki_scout = WikipediaScout()
        page_title = wiki_scout.get_article_title_from_url(wiki_url)
        if not page_title:
            page_title = wiki_scout.search_wikipedia_article(wiki_url)

        if not page_title:
            return JsonResponse({'status': 'error', 'message': f'Kunde inte hittas någon Wikipedia-artikel för "{wiki_url}".'}, status=404)

        # Stage 1: Shallow infobox parse only (fast, < 1s)
        infobox = wiki_scout.audit_infobox_only(page_title)
        if not infobox:
            return JsonResponse({'status': 'error', 'message': f'Kunde inte läsa Wikipedia-infobox för "{page_title}".'}, status=400)

        title       = infobox['page_title']
        resolved_url = infobox['wiki_url']
        master_code  = title.lower().replace(' ', '-').replace("'", '').replace('/', '-')[:100]

        final_grade     = 'GRADE_C'
        grade_reason_str = f"Grad C (Inväntar djupscanning): Wikipedia-länk hittad för '{title}'. Klicka 'Djupscanna' för fullständig analys."

        today_date       = datetime.date.today()
        next_rescan_date = today_date + datetime.timedelta(days=7)

        scout_payload = {
            "scouting_audit": {
                "scan_timestamp":     datetime.datetime.now().isoformat(),
                "scouting_stage":     "SHALLOW",
                "completeness_grade": final_grade,
                "grade_reason":       grade_reason_str,
                "official_source_url": resolved_url,
                "wikipedia_url":      resolved_url,
                "wikipedia_title":    title,
                "is_compatible_sport": True,
                "draw_date":          "",
                "next_rescan_date":   next_rescan_date.isoformat(),
                "advancement_rules":  "",
                "wikipedia_audit":    None,
            },
            "master_event": {
                "name":               title,
                "code":               master_code,
                "sport":              "Championship",
                "organizer":          "International Federation",
                "host_country":       infobox.get('host_country') or "Värdnation",
                "official_source_url": resolved_url,
                "wikipedia_url":      resolved_url,
                "start_date":         "",
                "end_date":           "",
            },
            "tournament_config": {
                "name":           title,
                "total_teams":    infobox.get('teams_count') or 16,
                "knockout_stages": ["Quarterfinals", "Semifinals", "Final"],
            },
            "groups":          [],
            "fixtures_sample": [],
            "raw_allsportdb":  {"source": "Wikipedia Direct Import", "wiki_url": resolved_url},
        }

        scanned_obj, created, error = parse_and_save_scouted_json(scout_payload)
        if error:
            return JsonResponse({'status': 'error', 'message': error}, status=400)

        verb = 'importerades som nytt prospekt' if created else 'uppdaterades'
        return JsonResponse({
            'status':  'success',
            'message': f'Turnering "{scanned_obj.name}" {verb} från Wikipedia! Klicka "Djupscanna" för fullständig analys.',
            'prospect': {
                'id':     scanned_obj.id,
                'name':   scanned_obj.name,
                'grade':  scanned_obj.completeness_grade,
                'status': scanned_obj.status,
            }
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Ett fel uppstod vid Wikipedia-import: {str(e)}'}, status=500)


@superuser_or_staff_required
@require_POST
def scout_convert_view(request, prospect_id):

    """Converts a ScannedTournament prospect into a full live tournament."""
    try:
        is_active = request.POST.get('is_active') in ['true', '1', 'on']
        
        # Optional custom point system payload
        custom_pts = None
        custom_pts_str = request.POST.get('custom_point_system')
        if custom_pts_str:
            try:
                custom_pts = json.loads(custom_pts_str)
            except Exception:
                pass

        tournament, error = convert_scanned_to_live_tournament(
            scanned_id=prospect_id,
            admin_user=request.user,
            is_active=is_active,
            custom_point_system=custom_pts
        )

        if error:
            return JsonResponse({'status': 'error', 'message': error}, status=400)

        return JsonResponse({
            'status': 'success',
            'message': f'Turneringen "{tournament.name}" har skapats och finns nu i Engine Admin!',
            'tournament_id': tournament.id,
            'tournament_name': tournament.name,
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Kunde inte konvertera prospekt: {str(e)}'}, status=500)


@superuser_or_staff_required
@require_POST
def scout_update_status_view(request, prospect_id):
    """Updates status for a ScannedTournament (e.g. WATCHLIST, ARCHIVED, NEW)."""
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    new_status = request.POST.get('status', '').upper().strip()

    valid_statuses = ['NEW', 'WATCHLIST', 'CONVERTED', 'ARCHIVED']
    if new_status not in valid_statuses:
        return JsonResponse({'status': 'error', 'message': f'Ogiltig status "{new_status}".'}, status=400)

    prospect.status = new_status
    prospect.save()

    return JsonResponse({
        'status': 'success',
        'message': f'Status för "{prospect.name}" ändrades till {new_status}.',
        'prospect_id': prospect.id,
        'new_status': prospect.status
    })


@superuser_or_staff_required
@require_POST
def scout_delete_view(request, prospect_id):
    """Deletes a ScannedTournament prospect from staging."""
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    name = prospect.name
    prospect.delete()

    return JsonResponse({
        'status': 'success',
        'message': f'Prospektet "{name}" raderades från scout-listan.'
    })


@superuser_or_staff_required
def scout_prospect_json_view(request, prospect_id):
    """Returns raw payload JSON for review modal."""
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    return JsonResponse({
        'status': 'success',
        'prospect': {
            'id': prospect.id,
            'name': prospect.name,
            'sport': prospect.sport,
            'organizer': prospect.organizer,
            'host_country': prospect.host_country,
            'start_date': str(prospect.start_date) if prospect.start_date else '',
            'end_date': str(prospect.end_date) if prospect.end_date else '',
            'grade': prospect.completeness_grade,
            'grade_reason': prospect.grade_reason,
            'official_source_url': prospect.official_source_url or prospect.payload.get('master_event', {}).get('official_source_url') or '',
            'status': prospect.status,
            'payload': prospect.payload,
        }
    })


@superuser_or_staff_required
@require_POST
def scout_scrape_web_view(request):
    """Triggers AllSportDB web scanning to discover upcoming tournaments."""
    try:
        custom_query = request.POST.get('query', '').strip()
        created_cnt, updated_cnt, prospects = scrape_web_for_tournaments(custom_query)
        total_found = len(prospects)
        
        api_key = getattr(settings, 'ALLSPORTDB_API_KEY', '')
        if total_found == 0 and not api_key:
            return JsonResponse({
                'status': 'error',
                'message': 'Ingen giltig AllSportDB API-nyckel konfigurerad. Ange ALLSPORTDB_API_KEY i inställningarna eller använd "Importera via Wikipedia".'
            }, status=400)
            
        return JsonResponse({
            'status': 'success',
            'message': f'Webbscanning slutförd! Hittade {total_found} prospekt ({created_cnt} nya, {updated_cnt} uppdaterade).',
            'created_count': created_cnt,
            'updated_count': updated_cnt,
            'total_count': total_found
        })

    except Exception as e:
        logger.error(f"Error in scout_scrape_web_view: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Fel under webbscanning: {str(e)}'
        }, status=500)


def _run_deep_scan_on_prospect(prospect, wiki_scout, off_verifier):
    """
    Shared Stage 2–4 deep-scan engine.

    Fetches Wikipedia article plaintext and uses Google Gemini Flash (LLM) to
    semantically extract groups, fixtures, draw dates, and advancement rules
    without any structure assumptions.  Falls back transparently to the HTML
    heuristic WikipediaScout if GEMINI_API_KEY is not set or the LLM call fails.

    Also runs OfficialRegulationsVerifier cross-audit (Stage 3) and Multi-Level
    Grade A/B/C classification (Stage 4).

    Returns a dict with keys:
        ok (bool), error (str|None), grade, grade_reason,
        fixtures_count, groups_count, teams_count,
        draw_completed, draw_date, scheduled_matchdays

    The caller is responsible for calling prospect.save().
    """
    import datetime
    from tournament.services.llm_wikipedia_scout import LLMWikipediaScout

    payload        = prospect.payload or {}
    scouting_audit = payload.get('scouting_audit', {})

    # Resolve Wikipedia page title (wiki_scout used only for title resolution)
    wiki_url   = scouting_audit.get('wikipedia_url') or prospect.official_source_url or ''
    page_title = wiki_scout.get_article_title_from_url(wiki_url)
    if not page_title:
        page_title = scouting_audit.get('wikipedia_title') or ''
    if not page_title:
        page_title = wiki_scout.search_wikipedia_article(prospect.name)

    if not page_title:
        return {
            'ok': False,
            'error': f'Kunde inte hitta Wikipedia-artikel för "{prospect.name}". Kontrollera Wikipedia-länken.',
        }

    # Stage 2 – LLM deep audit (falls back to HTML heuristics automatically)
    audit = LLMWikipediaScout().audit_with_llm(page_title)
    if not audit:
        return {
            'ok': False,
            'error': f'Kunde inte läsa Wikipedia-sidan för "{page_title}".',
        }

    # Disambiguation / Split Tournament Portal Handling (e.g. 2026 FIBA 3x3 U23 World Cup)
    if audit.get('is_disambiguation') and audit.get('sub_tournaments'):
        import urllib.parse
        from tournament.services.scout_service import parse_and_save_scouted_json
        created_names = []
        for sub in audit.get('sub_tournaments'):
            sub_name = sub.get('name') or sub.get('wiki_title')
            if not sub_name:
                continue
            sub_url = sub.get('wiki_url') or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(sub_name.replace(' ', '_'))}"
            sub_code = sub_name.lower().replace(' ', '-').replace("'", '').replace('/', '-')[:100]

            sub_payload = {
                "scouting_audit": {
                    "scan_timestamp": datetime.datetime.now().isoformat(),
                    "scouting_stage": "SHALLOW",
                    "completeness_grade": "GRADE_C",
                    "grade_reason": f"Uppdelad från samlingssida '{prospect.name}'. Klicka 'Djupscanna' för fullständig analys.",
                    "official_source_url": "",
                    "wikipedia_url": sub_url,
                    "wikipedia_title": sub_name,
                    "is_compatible_sport": True,
                },
                "master_event": {
                    "name": sub_name,
                    "code": sub_code,
                    "sport": prospect.sport or "Sports",
                    "organizer": prospect.organizer or "Wikipedia",
                    "host_country": prospect.host_country or "",
                    "official_source_url": "",
                    "wikipedia_url": sub_url,
                    "start_date": "",
                    "end_date": "",
                },
                "tournament_config": {
                    "name": sub_name,
                    "total_teams": 16,
                    "knockout_stages": ["Quarterfinals", "Semifinals", "Final"],
                },
                "groups": [],
                "fixtures_sample": [],
            }
            sub_obj, _, _ = parse_and_save_scouted_json(sub_payload)
            if sub_obj:
                created_names.append(sub_obj.name)

        prospect.completeness_grade = 'GRADE_C'
        prospect.grade_reason = f"Grad C (Uppdelad): Innehåller {len(created_names)} separata turneringar ({', '.join(created_names)}). Se respektive turneringskort i scout-listan."
        prospect.save()

        return {
            'ok': True,
            'grade': 'GRADE_C',
            'grade_reason': prospect.grade_reason,
            'fixtures_count': 0,
            'groups_count': 0,
            'teams_count': 0,
            'draw_completed': False,
            'draw_date': '',
            'scheduled_matchdays': 0,
        }

    today_date = datetime.date.today()

    # Stage 2b - Wikidata Entity Cross-Audit
    from tournament.services.wikidata_scout import WikidataScout
    wikidata = WikidataScout.fetch_wikidata_entity(page_title)

    # Extract start and end dates from audit, Wikidata, or existing prospect
    audit_start_str = audit.get('tournament_start_date') or audit.get('start_date') or wikidata.get('start_date') or ''
    audit_end_str   = audit.get('tournament_end_date') or audit.get('end_date') or wikidata.get('end_date') or ''

    start_date_obj = None
    if audit_start_str:
        try:
            start_date_obj = datetime.date.fromisoformat(audit_start_str)
        except Exception:
            pass

    if not start_date_obj and prospect.start_date:
        start_date_obj = prospect.start_date

    end_date_obj = None
    if audit_end_str:
        try:
            end_date_obj = datetime.date.fromisoformat(audit_end_str)
        except Exception:
            pass

    if not end_date_obj and prospect.end_date:
        end_date_obj = prospect.end_date

    min_upcoming_date = today_date + datetime.timedelta(days=30)

    # Rejection Rule 1: Tournaments with played match scores or marked as ongoing/finished
    if audit.get('is_ongoing_or_finished'):
        prospect_name = prospect.name
        prospect.delete()
        return {
            'ok': False,
            'error': f"Djupscanning misslyckades: Turneringen '{prospect_name}' är pågående eller avslutad (Spelade matcher/resultat hittades på Wikipedia). Endast framtida turneringar accepteras.",
        }

    # Rejection Rule 2: Tournaments starting in less than 30 days or in the past (start_date < today + 30 days)
    if start_date_obj and start_date_obj < min_upcoming_date:
        prospect_name = prospect.name
        prospect.delete()
        return {
            'ok': False,
            'error': f"Djupscanning misslyckades: Turneringen '{prospect_name}' är pågående eller startar inom mindre än 30 dagar (Startdatum: {start_date_obj}, tröskel: {min_upcoming_date}). Endast framtida turneringar som startar om minst 30 dagar accepteras.",
        }

    # Rejection Rule 3: Tournaments already finished (end_date < today)
    if end_date_obj and end_date_obj < today_date:
        prospect_name = prospect.name
        prospect.delete()
        return {
            'ok': False,
            'error': f"Djupscanning misslyckades: Turneringen '{prospect_name}' har redan avslutats (Slutdatum: {end_date_obj}). Endast framtida turneringar accepteras.",
        }

    # Update prospect dates
    prospect.start_date = start_date_obj
    prospect.end_date   = end_date_obj

    payload.setdefault('master_event', {})['start_date'] = str(start_date_obj) if start_date_obj else ""
    payload.setdefault('master_event', {})['end_date']   = str(end_date_obj) if end_date_obj else ""

    # Stage 3 – Official Regulations cross-audit
    official_website = (
        payload.get('master_event', {}).get('official_source_url')
        or scouting_audit.get('official_source_url')
        or ''
    )
    official_audit = off_verifier.verify_official_regulations(official_website, prospect.name)

    # Stage 4 – Multi-Level Grade Classification: Redo (A), Väntar lottning (B), Ej redo (C), Rejected (Delete)
    has_full_dates = bool(start_date_obj and end_date_obj)
    has_start_date = bool(start_date_obj)
    draw_ok        = bool(audit.get('draw_completed') and audit.get('groups_count', 0) >= 2)
    fixtures_ok    = bool(audit.get('fixtures_completed') and
                          (audit.get('fixtures_count', 0) >= 4 or audit.get('scheduled_matchdays', 0) >= 4))

    # Rejection Rule 4: Completely empty unviable prospect (Missing dates AND fixtures AND teams)
    if not has_start_date and not draw_ok and not fixtures_ok and audit.get('teams_count', 0) == 0:
        prospect_name = prospect.name
        prospect.delete()
        return {
            'ok': False,
            'error': f"Djupscanning misslyckades: Turneringen '{prospect_name}' saknar datum, spelschema och lag. Turneringen avvisades.",
        }

    # Grade A: Redo (100% Ready) - Green
    if has_full_dates and draw_ok and fixtures_ok:
        final_grade  = 'GRADE_A'
        final_reason = (f"Grad A (Redo): Djupskannad från Wikipedia: '{page_title}' "
                        f"({start_date_obj} – {end_date_obj}, {audit.get('fixtures_count', 0)} matcher, "
                        f"{audit.get('teams_count', 0)} lag i {audit.get('groups_count', 0)} grupper verifierade).")

    # Grade B: Väntar lottning (Draw pending, with LLM draw date) - Blue
    elif has_start_date and not draw_ok:
        final_grade  = 'GRADE_B'
        draw_date_str = audit.get('draw_date') or ''
        draw_info = f" (Lottningsdatum: {draw_date_str})" if draw_date_str else " (Lottningsdatum ej angivet)"
        final_reason = (f"Grad B (Väntar lottning): Turneringen startar {start_date_obj}, men lag/grupper är inte lottade ännu{draw_info}.")

    # Grade C: Ej redo (Missing Fixtures/Dates or structure) - Yellow/Amber
    else:
        final_grade  = 'GRADE_C'
        date_info    = f"Startdatum: {start_date_obj}" if start_date_obj else "Startdatum ej bekräftat ännu"
        final_reason = f"Grad C (Ej redo): Djupskannad från Wikipedia ('{page_title}'). {date_info}. Saknar spelschema, datum eller turneringsstruktur."

    # Rescan date calculation
    next_rescan_date = today_date + datetime.timedelta(days=7)
    draw_date_str    = audit.get('draw_date') or ''
    if draw_date_str:
        m_eng     = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', draw_date_str)
        month_map = {
            'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
            'july':7,'august':8,'september':9,'october':10,'november':11,'december':12
        }
        if m_eng and m_eng.group(2).lower() in month_map:
            try:
                d_obj = datetime.date(int(m_eng.group(3)), month_map[m_eng.group(2).lower()], int(m_eng.group(1)))
                if d_obj >= today_date:
                    next_rescan_date = d_obj + datetime.timedelta(days=7)
            except Exception:
                pass

    # Extract & normalise fixtures
    extracted_fixtures = []
    for i, fix in enumerate(audit.get('fixtures', []), 1):
        dt_str = f"{fix.get('date', '')} {fix.get('time', '')}".strip()
        extracted_fixtures.append({
            'match_number':   i,
            'stage_or_group': fix.get('stage_or_group', 'Gruppspel'),
            'date_time':      dt_str,
            'home_team':      fix.get('home_team', ''),
            'away_team':      fix.get('away_team', ''),
            'venue':          fix.get('venue', ''),
            'is_placeholder': fix.get('is_placeholder', False),
        })

    official_rules_str = audit.get('official_rules') or audit.get('advancement_rules') or ''

    # Persist back into payload
    payload.setdefault('scouting_audit', {}).update({
        'scouting_stage':      'DEEP',
        'scan_timestamp':      datetime.datetime.now().isoformat(),
        'completeness_grade':  final_grade,
        'grade_reason':        final_reason,
        'wikipedia_url':       audit.get('wiki_url', wiki_url),
        'wikipedia_title':     audit.get('page_title', page_title),
        'draw_date':           draw_date_str,
        'next_rescan_date':    next_rescan_date.isoformat(),
        'advancement_rules':   audit.get('advancement_rules', ''),
        'official_rules':      official_rules_str,
        'official_site_audit': official_audit,
        'wikipedia_audit':     audit,
    })
    if audit.get('groups'):
        payload['groups'] = audit['groups']
    payload['fixtures_sample'] = extracted_fixtures
    if audit.get('knockout_stages'):
        payload.setdefault('tournament_config', {})['knockout_stages'] = audit['knockout_stages']
    if audit.get('teams_count'):
        payload.setdefault('tournament_config', {})['total_teams'] = audit['teams_count']
    if audit.get('host_country') and not payload.get('master_event', {}).get('host_country'):
        payload.setdefault('master_event', {})['host_country'] = audit['host_country']

    extracted_logo_url = audit.get('logo_url') or wikidata.get('logo_url') or ''
    if extracted_logo_url:
        prospect.logo_url = extracted_logo_url
        payload['logo_url'] = extracted_logo_url

    prospect.payload            = payload
    prospect.completeness_grade = final_grade
    prospect.grade_reason       = final_reason
    if official_rules_str:
        prospect.official_rules = official_rules_str
    
    extracted_official_url = audit.get('official_regulations_url') or wikidata.get('official_website_url') or ''
    if extracted_official_url:
        prospect.official_source_url = extracted_official_url

    if wikidata.get('wikidata_qid'):
        payload['wikidata_qid'] = wikidata['wikidata_qid']

    prospect.save()

    return {
        'ok':                True,
        'error':             None,
        'grade':             final_grade,
        'grade_reason':      final_reason,
        'fixtures_count':    audit.get('fixtures_count', 0),
        'groups_count':      audit.get('groups_count', 0),
        'teams_count':       audit.get('teams_count', 0),
        'draw_completed':    audit.get('draw_completed', False),
        'draw_date':         draw_date_str,
        'scheduled_matchdays': audit.get('scheduled_matchdays', 0),
    }


@superuser_or_staff_required
@require_POST
def scout_deep_scan_one_view(request, prospect_id):
    """
    Stage 2–4 Deep Scout for a single prospect.
    Delegates to _run_deep_scan_on_prospect() and returns a JSON response.
    Called by the per-card '🔬 Djupscanna' button in the Engine Admin Scout UI.
    """
    from tournament.services.wikipedia_scout import WikipediaScout
    from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

    prospect = get_object_or_404(ScannedTournament, id=prospect_id)

    try:
        result = _run_deep_scan_on_prospect(
            prospect,
            WikipediaScout(),
            OfficialRegulationsVerifier(),
        )
        if not result['ok']:
            return JsonResponse({'status': 'error', 'message': result['error']}, status=400)

        prospect.save()
        
        # Merge duplicate prospects sharing the exact same Wikipedia link
        from tournament.services.scout_service import merge_duplicate_scanned_tournaments_by_wikipedia
        merge_duplicate_scanned_tournaments_by_wikipedia()

        return JsonResponse({
            'status':              'success',
            'message':             f'Djupscanning slutförd! "{prospect.name}" → {result["grade"]}',
            'grade':               result['grade'],
            'grade_reason':        result['grade_reason'],
            'fixtures_count':      result['fixtures_count'],
            'groups_count':        result['groups_count'],
            'teams_count':         result['teams_count'],
            'draw_completed':      result['draw_completed'],
            'draw_date':           result['draw_date'],
            'scheduled_matchdays': result['scheduled_matchdays'],
        })

    except Exception as e:
        logger.error(f"Error in scout_deep_scan_one_view (prospect #{prospect_id}): {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Fel under djupscanning: {str(e)}'}, status=500)


@superuser_or_staff_required
@require_POST
def scout_update_official_url_view(request, prospect_id):
    """
    Manually sets or updates the official source URL for a scanned prospect card.
    Re-runs OfficialRegulationsVerifier on the URL and updates prospect payload in-place.
    """
    from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier
    
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    official_url = request.POST.get('official_url', '').strip()
    
    off_verifier = OfficialRegulationsVerifier()
    official_audit = off_verifier.verify_official_regulations(official_url, prospect.name) if official_url else None
    
    prospect.official_source_url = official_url
    
    payload = prospect.payload or {}
    scouting_audit = payload.setdefault('scouting_audit', {})
    scouting_audit['official_source_url'] = official_url
    if official_audit:
        scouting_audit['official_site_audit'] = official_audit
        
    master_event = payload.setdefault('master_event', {})
    master_event['official_source_url'] = official_url
    
    prospect.payload = payload
    prospect.save()
    
    return JsonResponse({
        'status': 'success',
        'message': f'Officiell webbadress för "{prospect.name}" har sparats och verifierats!',
        'official_url': official_url,
        'official_site_audit': official_audit,
    })


@superuser_or_staff_required
@require_POST
def scout_update_official_rules_view(request, prospect_id):
    """
    Updates official rules text and regulations URL for a scanned prospect card or live tournament.
    """
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    official_rules = request.POST.get('official_rules', '').strip()
    official_url = request.POST.get('official_url', '').strip()

    prospect.official_rules = official_rules
    if official_url:
        prospect.official_source_url = official_url

    payload = prospect.payload or {}
    scouting_audit = payload.setdefault('scouting_audit', {})
    scouting_audit['official_rules'] = official_rules
    if official_url:
        scouting_audit['official_source_url'] = official_url
    prospect.payload = payload
    prospect.save()

    # Also update converted tournament if already converted
    if prospect.converted_tournament:
        tour = prospect.converted_tournament
        tour.official_rules = official_rules
        if official_url:
            tour.official_regulations_url = official_url
        tour.save()

    return JsonResponse({
        'status': 'success',
        'message': f'Officiella föreskrifter & reglemente för "{prospect.name}" har sparats!',
        'official_rules': prospect.official_rules,
        'official_url': prospect.official_source_url,
    })


@superuser_or_staff_required
@require_POST
def scout_clear_list_view(request):
    """Clears scanned tournament prospects from the scout list."""
    try:
        clear_all = request.POST.get('clear_all') in ['1', 'true']
        with transaction.atomic():
            if clear_all:
                deleted_cnt, _ = ScannedTournament.objects.all().delete()
            else:
                deleted_cnt, _ = ScannedTournament.objects.exclude(status='CONVERTED').delete()
        return JsonResponse({
            'status': 'success',
            'message': f'Rensade {deleted_cnt} prospekt från scout-listan.'
        })
    except Exception as e:
        logger.error(f"Fel i scout_clear_list_view: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Kunde inte rensa listan: {str(e)}'
        }, status=500)


@superuser_or_staff_required
@require_POST
def scout_refresh_all_view(request):
    """
    Bulk Stage 2–4 Deep Scout for ALL non-converted prospects.
    Delegates each prospect to _run_deep_scan_on_prospect() — the same full
    pipeline as the per-card '🔬 Djupscanna' button — so that grades,
    fixtures, groups, official-site audits, scouting_stage, and rescan dates
    are all updated identically.
    """
    from tournament.services.wikipedia_scout import WikipediaScout
    from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

    wiki_scout   = WikipediaScout()
    off_verifier = OfficialRegulationsVerifier()
    prospects    = ScannedTournament.objects.exclude(status='CONVERTED')

    refreshed_count = 0
    skipped_count   = 0
    results         = []

    for prospect in prospects:
        try:
            result = _run_deep_scan_on_prospect(prospect, wiki_scout, off_verifier)
            if result['ok']:
                prospect.save()
                refreshed_count += 1
                results.append({
                    'id':    prospect.id,
                    'name':  prospect.name,
                    'grade': result['grade'],
                    'ok':    True,
                })
            else:
                skipped_count += 1
                results.append({
                    'id':    prospect.id,
                    'name':  prospect.name,
                    'ok':    False,
                    'error': result['error'],
                })
                logger.warning(f"scout_refresh_all: skipped prospect #{prospect.id} '{prospect.name}': {result['error']}")
        except Exception as e:
            skipped_count += 1
            results.append({'id': prospect.id, 'name': prospect.name, 'ok': False, 'error': str(e)})
            logger.error(f"scout_refresh_all: error on prospect #{prospect.id}: {e}", exc_info=True)

    return JsonResponse({
        'status':          'success',
        'message':         f'Djupskannade {refreshed_count} turneringar ({skipped_count} hoppades över).',
        'refreshed_count': refreshed_count,
        'skipped_count':   skipped_count,
        'results':         results,
    })


@superuser_or_staff_required
def tournament_points_sidebets_get_view(request, tournament_id):
    """Returns PointSystem rules and Sidebets list for a given tournament."""
    tour = get_object_or_404(Tournament, id=tournament_id)
    ps, _ = PointSystem.objects.get_or_create(tournament=tour)
    sidebets = tour.sidebets.all().order_by('id')

    sidebets_list = [{
        'id': sb.id,
        'question': sb.question,
        'points': sb.points,
        'question_type': sb.question_type,
        'correct_answers': sb.correct_answers or '',
    } for sb in sidebets]

    points_data = {
        # Match scoring
        'match_correct_1x2': ps.match_correct_1x2,
        'match_correct_goals_per_team': ps.match_correct_goals_per_team,
        'match_correct_total_goals': ps.match_correct_total_goals,
        # Group scoring
        'group_correct_placement': ps.group_correct_placement,
        'group_correct_points': ps.group_correct_points,
        'group_correct_goals_scored': ps.group_correct_goals_scored,
        'group_correct_goals_conceded': ps.group_correct_goals_conceded,
        'group_correct_goal_diff': ps.group_correct_goal_diff,
        'group_team_qualified': ps.group_team_qualified,
        # Special table scoring
        'qualifying_table_team_qualified': ps.qualifying_table_team_qualified,
        'qualifying_table_exact_rank': ps.qualifying_table_exact_rank,
        'qualifying_table_points': ps.qualifying_table_points,
        'qualifying_table_goals_scored': ps.qualifying_table_goals_scored,
        'qualifying_table_goals_conceded': ps.qualifying_table_goals_conceded,
        'qualifying_table_goal_diff': ps.qualifying_table_goal_diff,
        # Knockout scoring
        'knockout_qualified_third': ps.knockout_qualified_third,
        'knockout_round_of_32': ps.knockout_round_of_32,
        'knockout_round_of_16': ps.knockout_round_of_16,
        'knockout_quarterfinal': ps.knockout_quarterfinal,
        'knockout_semifinal': ps.knockout_semifinal,
        'knockout_bronze_match': ps.knockout_bronze_match,
        'knockout_final': ps.knockout_final,
    }

    return JsonResponse({
        'status': 'success',
        'tournament_id': tour.id,
        'tournament_name': tour.name,
        'points': points_data,
        'sidebets': sidebets_list,
    })


@superuser_or_staff_required
@require_POST
def tournament_points_save_view(request, tournament_id):
    """Saves updated PointSystem values for a tournament."""
    tour = get_object_or_404(Tournament, id=tournament_id)
    ps, _ = PointSystem.objects.get_or_create(tournament=tour)

    FIELDS = [
        'match_correct_1x2',
        'match_correct_goals_per_team',
        'match_correct_total_goals',
        'group_correct_placement',
        'group_correct_points',
        'group_correct_goals_scored',
        'group_correct_goals_conceded',
        'group_correct_goal_diff',
        'group_team_qualified',
        'qualifying_table_team_qualified',
        'qualifying_table_exact_rank',
        'qualifying_table_points',
        'qualifying_table_goals_scored',
        'qualifying_table_goals_conceded',
        'qualifying_table_goal_diff',
        'knockout_qualified_third',
        'knockout_round_of_32',
        'knockout_round_of_16',
        'knockout_quarterfinal',
        'knockout_semifinal',
        'knockout_bronze_match',
        'knockout_final',
    ]

    for f in FIELDS:
        if f in request.POST:
            try:
                val = int(request.POST.get(f, 0))
                setattr(ps, f, max(0, val))
            except (ValueError, TypeError):
                pass

    ps.save()
    return JsonResponse({
        'status': 'success',
        'message': f'Poängsystemet för "{tour.name}" sparades framgångsrikt!'
    })


@superuser_or_staff_required
@require_POST
def tournament_sidebet_save_view(request, tournament_id):
    """Creates or updates a single Sidebet for a tournament."""
    tour = get_object_or_404(Tournament, id=tournament_id)
    sidebet_id = request.POST.get('sidebet_id')
    question = request.POST.get('question', '').strip()
    question_type = request.POST.get('question_type', 'TEXT').strip()
    points_raw = request.POST.get('points', 25)
    correct_answers = request.POST.get('correct_answers', '').strip()

    if not question:
        return JsonResponse({'status': 'error', 'message': 'Frågetext kan inte vara tom.'}, status=400)

    try:
        points = max(1, int(points_raw))
    except (ValueError, TypeError):
        points = 25

    if question_type not in ['TEAM', 'TEXT']:
        question_type = 'TEXT'

    if sidebet_id:
        sb = get_object_or_404(Sidebet, id=sidebet_id, tournament=tour)
        sb.question = question
        sb.question_type = question_type
        sb.points = points
        sb.correct_answers = correct_answers
        sb.save()
        msg = 'Sidebet uppdaterades.'
    else:
        sb = Sidebet.objects.create(
            tournament=tour,
            question=question,
            question_type=question_type,
            points=points,
            correct_answers=correct_answers
        )
        msg = 'Ny sidebet skapades.'

    return JsonResponse({
        'status': 'success',
        'message': msg,
        'sidebet': {
            'id': sb.id,
            'question': sb.question,
            'question_type': sb.question_type,
            'points': sb.points,
            'correct_answers': sb.correct_answers or '',
        }
    })


@superuser_or_staff_required
@require_POST
def tournament_sidebet_delete_view(request, tournament_id, sidebet_id):
    """Deletes a single Sidebet from a tournament."""
    tour = get_object_or_404(Tournament, id=tournament_id)
    sb = get_object_or_404(Sidebet, id=sidebet_id, tournament=tour)
    q = sb.question
    sb.delete()

    return JsonResponse({
        'status': 'success',
        'message': f'Sidebet "{q}" raderades.'
    })



