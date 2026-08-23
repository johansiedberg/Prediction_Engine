import os
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
    """Entry point for Port 2029 (Engine Admin). Shows Dashboard if logged in as standalone system Engine Admin ('johansiedberg'), else Login form."""
    if request.user.is_authenticated and request.user.username == 'johansiedberg' and request.user.is_superuser:
        return engine_admin_dashboard_view(request)
    return render(request, 'tournament/engine_admin_login.html')


def engine_admin_login_view(request):
    """Processes login specifically for Port 2029 Engine Admin (Restricted strictly to system admin 'johansiedberg')."""
    if request.method == 'POST':
        login_input = request.POST.get('email', '').strip() or request.POST.get('username', '').strip()
        pwd = request.POST.get('password', '').strip()
        user = authenticate(request, username=login_input, password=pwd)
        if user is None:
            user_obj = User.objects.filter(email__iexact=login_input).first()
            if user_obj:
                user = authenticate(request, username=user_obj.username, password=pwd)
        if user is not None and user.username == 'johansiedberg' and user.is_superuser:
            login(request, user)
            return redirect('/')
        else:
            messages.error(request, "Tillgång nekad: Endast det dedikerade Engine Admin-systemkontot har behörighet till Port 2029.")
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

    # Auto-rescan any WATCHLIST prospects whose next_rescan_date is due
    try:
        from tournament.services.scout_service import auto_rescan_due_watchlist_prospects
        auto_rescan_due_watchlist_prospects()
    except Exception as e:
        pass

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
    ALLSPORTDB_SPORTS_MAP = [
        ('American Football', '🏈', ['american football', 'flag football', 'nfl', 'ifaf']),
        ('Archery', '🎯', ['archery']),
        ('Artistic Gymnastics', '🤸', ['artistic gymnastics']),
        ('Artistic Swimming', '🏊', ['artistic swimming']),
        ('Athletics', '🏃', ['athletics', 'track and field', 'friidrott']),
        ('Badminton', '🏸', ['badminton']),
        ('Bandy', '🏒', ['bandy']),
        ('Baseball', '⚾', ['baseball', 'baseball5']),
        ('Basketball', '🏀', ['basketball', 'basket', 'fiba', 'nba']),
        ('Beach Soccer', '⚽', ['beach soccer']),
        ('Beach Volleyball', '🏐', ['beach volleyball']),
        ('Biathlon', '⛷⚫', ['biathlon']),
        ('Boxing', '🥊', ['boxing']),
        ('Canoeing', '🛶', ['canoeing', 'kayak']),
        ('Chess', '♟', ['chess']),
        ('Cricket', '🏏', ['cricket']),
        ('Cross-Country Skiing', '⛷', ['cross-country skiing', 'längdskidor']),
        ('Curling', '🥌', ['curling']),
        ('Cycling', '🚴', ['cycling', 'cykel']),
        ('Diving', '🏊', ['diving']),
        ('Field Hockey', '🏑', ['field hockey', 'fih hockey']),
        ('Figure Skating', '⛸', ['figure skating', 'konståkning']),
        ('Floorball', '🏑', ['floorball', 'innebandy']),
        ('Football', '⚽', ['football', 'fotboll', 'soccer', 'fifa', 'uefa', 'copa', 'gold cup', 'nations league', 'afcon', 'asian cup']),
        ('Futsal', '⚽', ['futsal']),
        ('Golf', '⛳', ['golf', 'pga']),
        ('Handball', '🤾', ['handball', 'handboll', 'ihf', 'ehf']),
        ('Ice Hockey', '🏒', ['ice hockey', 'ishockey', 'nhl', 'iihf']),
        ('Judo', '🥋', ['judo']),
        ('Karate', '🥋', ['karate']),
        ('Lacrosse', '🥍', ['lacrosse']),
        ('Motor Sports', '🏎', ['motor sports', 'formula 1', 'f1', 'motogp']),
        ('Rowing', '🚣', ['rowing', 'rodd']),
        ('Rugby', '🏉', ['rugby']),
        ('Sailing', '⛵', ['sailing', 'segling']),
        ('Ski Jumping', '🎿', ['ski jumping', 'backhoppning']),
        ('Snowboarding', '🏂', ['snowboarding']),
        ('Softball', '🥎', ['softball']),
        ('Table Tennis', '🏓', ['table tennis', 'ping pong', 'bordtennis']),
        ('Taekwondo', '🥋', ['taekwondo']),
        ('Tennis', '🎾', ['tennis', 'wimbledon', 'atp', 'wta']),
        ('Triathlon', '🏊🚴🏃', ['triathlon']),
        ('Volleyball', '🏐', ['volleyball', 'volleyboll', 'fivb', 'avc']),
        ('Water Polo', '🤽', ['water polo', 'vattenpolo']),
        ('Weightlifting', '🏋', ['weightlifting', 'tyngdlyftning']),
        ('Wrestling', '🤼', ['wrestling', 'brottning']),
    ]

    def infer_sport(title, current_sport=None):
        text = f"{title or ''} {current_sport or ''}".lower()
        for sport_name, emoji, keywords in ALLSPORTDB_SPORTS_MAP:
            for kw in keywords:
                if kw in text:
                    return sport_name, emoji
        return (current_sport.title() if current_sport and current_sport.lower() != 'sports' else 'Other'), '🏆'

    sport_counts_raw = {}
    today = timezone.localdate()

    for p in scanned_list:
        payload = p.payload or {}
        audit = payload.get('scouting_audit', {})
        scouting_stage = audit.get('scouting_stage', 'DEEP')  # Legacy prospects treated as DEEP

        # Compute Unified Status (combining Status + Grade)
        if p.status == 'CONVERTED':
            unified_status = 'CONVERTED'
        elif p.status == 'ARCHIVED' or p.completeness_grade == 'GRADE_D':
            unified_status = 'ARCHIVED'
        elif p.status == 'WATCHLIST':
            unified_status = 'WATCHLIST'
        elif p.status == 'READY' or p.completeness_grade == 'GRADE_A':
            unified_status = 'READY'
        elif scouting_stage == 'SHALLOW' and p.status == 'NEW':
            unified_status = 'NEW'
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

        sport_name, sport_icon = infer_sport(p.name, p.sport)
        sport_key = sport_name.lower().replace(' ', '_')

        if sport_key not in sport_counts_raw:
            sport_counts_raw[sport_key] = {
                'name': sport_name,
                'key': sport_key,
                'icon': sport_icon,
                'count': 0
            }
        sport_counts_raw[sport_key]['count'] += 1

        struct_seg = payload.get('structure_and_rules_segment', {})
        groups_seg = payload.get('groups_and_teams_segment', {})
        matches_seg = payload.get('matches_and_knockout_segment', {})
        general_seg = payload.get('general_segment', {})

        groups = groups_seg.get('groups') or payload.get('groups', [])
        raw_fixtures = matches_seg.get('group_matches') or payload.get('fixtures_sample', [])
        raw_knockouts = matches_seg.get('knockout_bracket') or payload.get('knockout_mapping_sample', [])
        sidebets = payload.get('sidebets_suggestions', [])

        # Build team badge lookup map from groups
        team_badge_map = {}
        for g in groups:
            for t in g.get('teams', []):
                if isinstance(t, dict):
                    t_n = (t.get('name') or '').strip()
                    if t_n:
                        team_badge_map[t_n] = {
                            'code': t.get('code') or '',
                            'flag_url': t.get('flag_url') or '',
                            'emblem_url': t.get('emblem_url') or '',
                        }

        # Enrich fixtures with badge data if missing
        fixtures = []
        for f in raw_fixtures:
            if isinstance(f, dict):
                f_copy = dict(f)
                h_name = (f_copy.get('home_team') or f_copy.get('home') or '').strip()
                a_name = (f_copy.get('away_team') or f_copy.get('away') or '').strip()
                if h_name in team_badge_map:
                    if not f_copy.get('home_team_flag_url'): f_copy['home_team_flag_url'] = team_badge_map[h_name]['flag_url']
                    if not f_copy.get('home_team_emblem_url'): f_copy['home_team_emblem_url'] = team_badge_map[h_name]['emblem_url']
                    if not f_copy.get('home_team_code'): f_copy['home_team_code'] = team_badge_map[h_name]['code']
                elif h_name and not f_copy.get('home_team_flag_url') and not f_copy.get('home_team_emblem_url'):
                    from tournament.services.team_badge_service import TeamBadgeService
                    b = TeamBadgeService.resolve_team_badge(h_name, sport=p.sport or 'Football', tournament_name=p.name, use_gemini_fallback=False)
                    if b.flag_url: f_copy['home_team_flag_url'] = b.flag_url
                    if b.emblem_url: f_copy['home_team_emblem_url'] = b.emblem_url
                    if b.code: f_copy['home_team_code'] = b.code

                if a_name in team_badge_map:
                    if not f_copy.get('away_team_flag_url'): f_copy['away_team_flag_url'] = team_badge_map[a_name]['flag_url']
                    if not f_copy.get('away_team_emblem_url'): f_copy['away_team_emblem_url'] = team_badge_map[a_name]['emblem_url']
                    if not f_copy.get('away_team_code'): f_copy['away_team_code'] = team_badge_map[a_name]['code']
                elif a_name and not f_copy.get('away_team_flag_url') and not f_copy.get('away_team_emblem_url'):
                    from tournament.services.team_badge_service import TeamBadgeService
                    b = TeamBadgeService.resolve_team_badge(a_name, sport=p.sport or 'Football', tournament_name=p.name, use_gemini_fallback=False)
                    if b.flag_url: f_copy['away_team_flag_url'] = b.flag_url
                    if b.emblem_url: f_copy['away_team_emblem_url'] = b.emblem_url
                    if b.code: f_copy['away_team_code'] = b.code

                fixtures.append(f_copy)
            else:
                fixtures.append(f)

        # Enrich knockout matches with badge data if missing
        knockouts = []
        for stage in raw_knockouts:
            if isinstance(stage, dict):
                st_copy = dict(stage)
                m_list = st_copy.get('matches', [])
                enriched_matches = []
                for m in m_list:
                    if isinstance(m, dict):
                        m_copy = dict(m)
                        h_name = (m_copy.get('home_team') or m_copy.get('home_source') or '').strip()
                        a_name = (m_copy.get('away_team') or m_copy.get('away_source') or '').strip()
                        if h_name in team_badge_map:
                            if not m_copy.get('home_team_flag_url'): m_copy['home_team_flag_url'] = team_badge_map[h_name]['flag_url']
                            if not m_copy.get('home_team_emblem_url'): m_copy['home_team_emblem_url'] = team_badge_map[h_name]['emblem_url']
                            if not m_copy.get('home_team_code'): m_copy['home_team_code'] = team_badge_map[h_name]['code']
                        elif h_name and not m_copy.get('home_team_flag_url') and not m_copy.get('home_team_emblem_url'):
                            from tournament.services.team_badge_service import TeamBadgeService
                            if not TeamBadgeService.is_placeholder(h_name):
                                b = TeamBadgeService.resolve_team_badge(h_name, sport=p.sport or 'Football', tournament_name=p.name, use_gemini_fallback=False)
                                if b.flag_url: m_copy['home_team_flag_url'] = b.flag_url
                                if b.emblem_url: m_copy['home_team_emblem_url'] = b.emblem_url
                                if b.code: m_copy['home_team_code'] = b.code

                        if a_name in team_badge_map:
                            if not m_copy.get('away_team_flag_url'): m_copy['away_team_flag_url'] = team_badge_map[a_name]['flag_url']
                            if not m_copy.get('away_team_emblem_url'): m_copy['away_team_emblem_url'] = team_badge_map[a_name]['emblem_url']
                            if not m_copy.get('away_team_code'): m_copy['away_team_code'] = team_badge_map[a_name]['code']
                        elif a_name and not m_copy.get('away_team_flag_url') and not m_copy.get('away_team_emblem_url'):
                            from tournament.services.team_badge_service import TeamBadgeService
                            if not TeamBadgeService.is_placeholder(a_name):
                                b = TeamBadgeService.resolve_team_badge(a_name, sport=p.sport or 'Football', tournament_name=p.name, use_gemini_fallback=False)
                                if b.flag_url: m_copy['away_team_flag_url'] = b.flag_url
                                if b.emblem_url: m_copy['away_team_emblem_url'] = b.emblem_url
                                if b.code: m_copy['away_team_code'] = b.code

                        enriched_matches.append(m_copy)
                    else:
                        enriched_matches.append(m)
                st_copy['matches'] = enriched_matches
                knockouts.append(st_copy)
            else:
                knockouts.append(stage)
        
        teams_count = groups_seg.get('teams_count') or sum(len(g.get('teams', [])) for g in groups) or payload.get('tournament_config', {}).get('total_teams', 0)
        groups_count = groups_seg.get('groups_count') or len(groups)
        matches_count = matches_seg.get('total_matches') or (len(fixtures) + len(knockouts))
        sidebets_count = len(sidebets)

        allsport_emoji = payload.get('raw_allsportdb', {}).get('emoji')
        icon = allsport_emoji or sport_icon

        days_to_start = None
        if p.start_date:
            days_to_start = (p.start_date - today).days

        grade_meta = {
            'GRADE_A': {
                'label': 'Redo',
                'icon':  'fa-shield-check',
                'style': 'background:#052E16;border:1px solid #15803D;color:#DCFCE7;',
            },
            'GRADE_B': {
                'label': 'Väntar lottning',
                'icon':  'fa-clock',
                'style': 'background:#451A03;border:1px solid #B45309;color:#FEF3C7;',
            },
            'GRADE_C': {
                'label': 'Ej redo',
                'icon':  'fa-circle-info',
                'style': 'background:#0F172A;border:1px solid #475569;color:#E2E8F0;',
            },
            'GRADE_D': {
                'label': 'Ej kompatibel',
                'icon':  'fa-circle-xmark',
                'style': 'background:#1c0404;border:1px solid #7f1d1d;color:#fecaca;',
            },
        }

        status_meta = {
            'NEW': {'label': 'Ej skannad', 'badge_class': 'bg-secondary text-white', 'icon': 'fa-hourglass-start'},
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

        from tournament.services.scout_service import has_real_teams
        real_teams_ready = groups_seg.get('has_real_teams') if 'has_real_teams' in groups_seg else has_real_teams(groups)

        is_grade_a = (p.completeness_grade == 'GRADE_A' and real_teams_ready)
        draw_done = bool(
            is_grade_a
            or (
                (struct_seg.get('general_setup', {}).get('draw_completed') or audit.get('draw_completed', False))
                and real_teams_ready
                and p.completeness_grade == 'GRADE_A'
            )
        )
        fixtures_done = bool(
            is_grade_a
            or (
                (matches_seg.get('fixtures_completed') or audit.get('fixtures_completed', False))
                and draw_done
                and real_teams_ready
                and p.completeness_grade == 'GRADE_A'
            )
        )
        scheduled_matchdays = int(audit.get('scheduled_matchdays', len(fixtures)))
        fixtures_have_placeholders = bool(audit.get('fixtures_have_placeholders', False)) or not real_teams_ready
        scouting_stage = audit.get('scouting_stage', 'DEEP')

        readiness = {
            'draw_completed': draw_done,
            'schedule_ready': fixtures_done,
        }

        # Override missing_items for SHALLOW prospects or Grade A
        if scouting_stage == 'SHALLOW':
            missing_items = []
        elif is_grade_a:
            missing_items = []

        official_rules_val = p.official_rules or audit.get('official_rules') or struct_seg.get('official_rules_summary') or audit.get('advancement_rules') or ''

        import urllib.parse
        wiki_url_val = (
            general_seg.get('wikipedia_url')
            or payload.get('master_event', {}).get('wikipedia_url')
            or audit.get('wikipedia_url')
            or (p.official_source_url if p.official_source_url and 'wikipedia.org' in p.official_source_url else '')
            or f"https://en.wikipedia.org/wiki/{urllib.parse.quote((audit.get('wikipedia_title') or p.name).replace(' ', '_'))}"
        )

        TIEBREAKER_LABELS = {
            'H2H_POINTS': {'label': 'Inbördes Möten (Poäng)', 'icon': 'fa-handshake', 'short': 'Inbördes Poäng'},
            'H2H_GOAL_DIFFERENCE': {'label': 'Inbördes Målskillnad', 'icon': 'fa-scale-balanced', 'short': 'Inbördes Målskillnad'},
            'H2H_GOALS_SCORED': {'label': 'Inbördes Gjorda Mål', 'icon': 'fa-futbol', 'short': 'Inbördes Mål'},
            'OVERALL_GOAL_DIFFERENCE': {'label': 'Total Målskillnad', 'icon': 'fa-chart-simple', 'short': 'Total Målskillnad'},
            'OVERALL_GOALS_SCORED': {'label': 'Totala Gjorda Mål', 'icon': 'fa-bullseye', 'short': 'Totala Mål'},
            'DISCIPLINARY_POINTS': {'label': 'Fair Play / Disciplin', 'icon': 'fa-shield-halved', 'short': 'Fair Play'},
            'COEFFICIENT': {'label': 'Koefficient', 'icon': 'fa-award', 'short': 'Koefficient'},
            'RANDOM_DRAW': {'label': 'Lottning', 'icon': 'fa-dice', 'short': 'Lottning'},
        }

        bp = p.tournament_blueprint or payload.get('tournament_blueprint') or {}
        raw_tb = struct_seg.get('group_stage_rules', {}).get('tiebreaker_hierarchy') or bp.get('tiebreaker_hierarchy') or ['H2H_POINTS', 'H2H_GOAL_DIFFERENCE', 'OVERALL_GOAL_DIFFERENCE', 'OVERALL_GOALS_SCORED', 'DISCIPLINARY_POINTS', 'RANDOM_DRAW']
        
        tiebreakers_display = []
        for idx, rule_item in enumerate(raw_tb, 1):
            if isinstance(rule_item, dict):
                tiebreakers_display.append({
                    'step': rule_item.get('step', idx),
                    'code': rule_item.get('rule', 'CUSTOM'),
                    'label': rule_item.get('label', str(rule_item)),
                    'short': rule_item.get('label', str(rule_item)),
                    'icon': rule_item.get('icon', 'fa-list-ol'),
                    'desc': rule_item.get('desc', ''),
                })
            else:
                rule_str = str(rule_item)
                info = TIEBREAKER_LABELS.get(rule_str, {'label': rule_str, 'icon': 'fa-list-ol', 'short': rule_str})
                tiebreakers_display.append({
                    'step': idx,
                    'code': rule_str,
                    'label': info['label'],
                    'short': info['short'],
                    'icon': info['icon'],
                    'desc': '',
                })

        def _parse_rules_to_sections(text: str) -> list:
            if not text or not isinstance(text, str):
                return []
            lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
            sec_list = []
            cur_title = "Format & Reglemente"
            cur_items = []
            for line in lines:
                if re.match(r'^(?:[#=1-9\.\s]*)(?:Format|Competition|Group|Knockout|Tiebreaker|Advancement|Rules|Regler|Särskiljning|Avancemang|Slutspel)', line, re.IGNORECASE) or line.startswith('###') or line.startswith('=='):
                    if cur_items:
                        sec_list.append({'title': cur_title, 'items': cur_items})
                        cur_items = []
                    cur_title = re.sub(r'^[#=1-9\.\s]+', '', line).strip().title() or "Reglemente"
                else:
                    item_str = re.sub(r'^[\*\-\•\d\.\s]+', '', line).strip()
                    if item_str:
                        cur_items.append(item_str)
            if cur_items:
                sec_list.append({'title': cur_title, 'items': cur_items})
            return sec_list

        rules_sections = _parse_rules_to_sections(official_rules_val)

        pts_win = struct_seg.get('group_stage_rules', {}).get('points_win', bp.get('points_for_win', 3))
        pts_draw = struct_seg.get('group_stage_rules', {}).get('points_draw', bp.get('points_for_draw', 1))
        pts_loss = struct_seg.get('group_stage_rules', {}).get('points_loss', bp.get('points_for_loss', 0))
        yc_thresh = bp.get('yellow_card_suspension_threshold', 2)

        adv_text = (
            struct_seg.get('qualifying_tables_rules', {}).get('description')
            or bp.get('qualifying_advancement_summary')
            or audit.get('advancement_rules')
            or f"De 2 bästa lagen per grupp ({groups_count} grupper) avancerar direkt till Slutspel."
        )

        ko_rule_text = (
            struct_seg.get('knockout_rules', {}).get('tiebreaker_description')
            or bp.get('knockout_tiebreakers')
            or "Vid oavgjort i slutspel tillämpas Förlängning (2x15 min) följt av Straffsparksläggning vid oavgjort."
        )

        rules_grid = {
            'group_stage': {
                'points_win': pts_win,
                'points_draw': pts_draw,
                'points_loss': pts_loss,
                'yellow_cards_suspension': struct_seg.get('group_stage_rules', {}).get('yellow_cards_suspension', f"{yc_thresh} gula kort = 1 match avstängning"),
                'red_card_suspension': struct_seg.get('group_stage_rules', {}).get('red_card_suspension', "1 rött kort = minst 1 match avstängning"),
            },
            'group_table': {
                'tiebreakers': tiebreakers_display
            },
            'qualifying': {
                'groups_count': groups_count,
                'teams_count': teams_count,
                'advancement_summary': adv_text,
                'target_stage': struct_seg.get('knockout_rules', {}).get('starting_round', "Slutspel"),
            },
            'knockout_stage': {
                'extra_time': f"Förlängning ({struct_seg.get('knockout_rules', {}).get('extra_time_minutes', 30)} min)",
                'penalties': "Straffsparksläggning" if struct_seg.get('knockout_rules', {}).get('has_penalties', True) else "Nej",
                'summary': ko_rule_text,
            }
        }

        r_date_obj = p.rescan_date
        rescan_date_str = r_date_obj.strftime('%Y-%m-%d') if r_date_obj else (today + datetime.timedelta(days=7)).strftime('%Y-%m-%d')

        draw_date_val = (
            struct_seg.get('general_setup', {}).get('draw_date')
            or audit.get('draw_date')
            or bp.get('draw_date')
            or payload.get('draw_date')
            or ''
        )
        logo_url_val = (
            general_seg.get('emblem', {}).get('logo_url')
            or p.logo_url
            or payload.get('logo_url')
            or payload.get('master_event', {}).get('logo_url')
            or ''
        )

        raw_pts = payload.get('points_system') or audit.get('points_system') or {}
        pts_system_dict = {
            'win': raw_pts.get('win') or struct_seg.get('group_stage_rules', {}).get('points_win') or 3,
            'draw': raw_pts.get('draw') if raw_pts.get('draw') is not None else (struct_seg.get('group_stage_rules', {}).get('points_draw') if struct_seg.get('group_stage_rules', {}).get('points_draw') is not None else 1),
            'loss': raw_pts.get('loss') if raw_pts.get('loss') is not None else (struct_seg.get('group_stage_rules', {}).get('points_loss') if struct_seg.get('group_stage_rules', {}).get('points_loss') is not None else 0),
        }

        raw_adv = payload.get('advancement_logic') or audit.get('advancement_logic') or {}
        adv_logic_dict = {
            'teams_per_group_advancing': raw_adv.get('teams_per_group_advancing') or struct_seg.get('group_stage_rules', {}).get('teams_per_group_advancing') or 2,
            'best_third_placed_advancing': raw_adv.get('best_third_placed_advancing') or struct_seg.get('qualifying_tables_rules', {}).get('best_thirds_count', 0),
            'has_best_thirds_table': bool(raw_adv.get('has_best_thirds_table') or struct_seg.get('qualifying_tables_rules', {}).get('has_best_thirds', False)),
            'has_runners_up_table': bool(raw_adv.get('has_runners_up_table') or struct_seg.get('qualifying_tables_rules', {}).get('has_runners_up', False)),
            'runners_up_advancing': raw_adv.get('runners_up_advancing') or struct_seg.get('qualifying_tables_rules', {}).get('runners_up_count', 0),
        }

        raw_mf = payload.get('match_format') or audit.get('match_format') or {}
        match_format_dict = {
            'regular_time_minutes': raw_mf.get('regular_time_minutes') or 90,
            'extra_time_minutes': raw_mf.get('extra_time_minutes') if raw_mf.get('extra_time_minutes') is not None else struct_seg.get('knockout_rules', {}).get('extra_time_minutes', 30),
            'has_penalties': raw_mf.get('has_penalties') if raw_mf.get('has_penalties') is not None else struct_seg.get('knockout_rules', {}).get('has_penalties', True),
        }

        scanned_data.append({
            'prospect': p,
            'unified_status': unified_status,
            'sport_key': sport_key,
            'teams_count': teams_count,
            'groups_count': groups_count,
            'matches_count': matches_count,
            'sidebets_count': sidebets_count,
            'sport_icon': icon,
            'has_real_teams': real_teams_ready,
            'lifecycle_info': p.lifecycle_info,
            'tournament_type': p.tournament_type,
            'lifecycle_phase': p.lifecycle_phase,
            'rescan_date_str': rescan_date_str,
            'days_to_start': days_to_start,
            'grade_meta': grade_meta,
            'status_meta': status_meta,
            'grade_reason': grade_reason,
            'missing_items': missing_items,
            'action_needed': action_needed,
            'official_source_url': p.official_source_url or general_seg.get('official_website_url') or payload.get('master_event', {}).get('official_source_url') or '',
            'logo_url': logo_url_val,
            'wikipedia_url': wiki_url_val,
            'official_rules': official_rules_val,
            'points_system': pts_system_dict,
            'tiebreakers': payload.get('tiebreakers') or audit.get('tiebreakers', []),
            'advancement_logic': adv_logic_dict,
            'match_format': match_format_dict,
            'tiebreakers_display': tiebreakers_display,
            'rules_sections': rules_sections,
            'rules_grid': rules_grid,

            'draw_done': draw_done,
            'draw_date': draw_date_val,
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

    sport_filters = sorted(sport_counts_raw.values(), key=lambda x: x['count'], reverse=True)

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
        'sport_filters': sport_filters,
        'gemini_key_active': bool(getattr(settings, 'GEMINI_API_KEY', '')),
        'gemini_key_masked': getattr(settings, 'GEMINI_API_KEY', '')[:6] + '...' + getattr(settings, 'GEMINI_API_KEY', '')[-4:] if len(getattr(settings, 'GEMINI_API_KEY', '')) >= 10 else '',
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

WORLD_CUP_2026_NATIONAL_TEAMS = [
    'USA', 'Mexiko', 'Kanada', 'Brasilien', 'Argentina', 'Frankrike',
    'England', 'Spanien', 'Tyskland', 'Belgien', 'Nederländerna', 'Portugal',
    'Italien', 'Kroatien', 'Uruguay', 'Japan', 'Sydkorea', 'Marocko',
    'Senegal', 'Australien', 'Colombia', 'Ecuador', 'Chile', 'Peru',
    'Nigeria', 'Elfenbenskusten', 'Ghana', 'Algeriet', 'Egypten', 'Kamerun',
    'Iran', 'Saudiarabien', 'Qatar', 'Irak', 'Uzbekistan', 'Förenade Arabemiraten',
    'Costa Rica', 'Jamaica', 'Panama', 'Honduras', 'Nya Zeeland', 'Tunisien'
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

    # 1. Ensure complete knockout bracket exists (Quarterfinals, Semifinals, Final)
    from tournament.services.scout_service import ensure_complete_knockout_bracket
    ensure_complete_knockout_bracket(tournament)

    # 2. Simulate Group Matches first
    simulated_count = 0
    group_matches = list(tournament.matches.filter(group__isnull=False).order_by('match_number', 'id'))
    for match in group_matches:
        match.home_goals = random.choice([0, 1, 1, 2, 2, 3, 4])
        match.away_goals = random.choice([0, 1, 1, 2, 2, 3, 4])
        match.is_finished = True
        match.save()
        simulated_count += 1

    # Clear cached lookup maps on tournament instance
    if hasattr(tournament, '_matches_by_number_dict'):
        delattr(tournament, '_matches_by_number_dict')
    if hasattr(tournament, '_groups_by_code_dict'):
        delattr(tournament, '_groups_by_code_dict')

    # 3. Simulate Knockout Matches in sequential match_number order
    knockout_matches = list(tournament.matches.filter(group__isnull=True).order_by('match_number', 'id'))
    for match in knockout_matches:
        h_g = random.choice([1, 2, 2, 3, 4])
        a_g = random.choice([0, 1, 1, 2, 3])
        if h_g == a_g:
            h_g += 1
        match.home_goals = h_g
        match.away_goals = a_g
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
    Resets simulated results and advancing teams:
    - If tournament was converted from a ScannedTournament prospect, re-runs convert_scanned_to_live_tournament
      to restore the exact pre-simulation team names, groups, fixtures, and regulations.
    - Otherwise, wipes all simulated match scores/finishes and resets knockout stage match team names back
      to stage placeholders while preserving all group team names intact.
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    scanned = ScannedTournament.objects.filter(converted_tournament=tournament).first()

    if scanned:
        from tournament.services.scout_service import convert_scanned_to_live_tournament
        restored_tour, err = convert_scanned_to_live_tournament(scanned.id, request.user, is_active=tournament.is_active)
        if restored_tour:
            tournament = restored_tour

    reset_matches_count = 0
    for match in tournament.matches.all():
        match.home_goals = None
        match.away_goals = None
        match.is_finished = False
        match.box_score_data = {}
        match.save()
        reset_matches_count += 1

    invalidate_tournament_cache(tournament.id)

    return JsonResponse({
        'status': 'success',
        'message': f'Nollställde alla simulerade resultat och återställde turneringen "{tournament.name}" till ursprungligt skick för uppstart!',
        'reset_count': reset_matches_count,
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
    if new_status == 'WATCHLIST':
        from tournament.services.scout_service import resolve_rescan_date_for_prospect
        res_date = resolve_rescan_date_for_prospect(prospect)
        if res_date:
            payload = prospect.payload or {}
            scouting_audit = payload.get('scouting_audit', {})
            scouting_audit['next_rescan_date'] = res_date.strftime('%Y-%m-%d')
            payload['scouting_audit'] = scouting_audit
            prospect.payload = payload
    prospect.save()

    return JsonResponse({
        'status': 'success',
        'message': f'Status för "{prospect.name}" ändrades till {new_status}.',
        'prospect_id': prospect.id,
        'new_status': prospect.status,
        'rescan_date': prospect.rescan_date.strftime('%Y-%m-%d') if prospect.rescan_date else None
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
    """Triggers Phase 1 WebCrawl / Ingestion Agent to discover upcoming tournaments."""
    try:
        custom_query = request.POST.get('query', '').strip()
        from tournament.services.web_crawl_agent import WebCrawlAgent
        agent = WebCrawlAgent()
        created_cnt, updated_cnt, prospects = agent.discover_and_ingest(custom_query)
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


def _run_deep_scan_on_prospect(prospect, wiki_scout=None, off_verifier=None):
    """
    Shared Stage 2 Deep Scan Engine.
    Delegates to ModularDeepScout to populate the unified TournamentProspectBlueprint schema.
    """
    from tournament.services.modular_deep_scout import ModularDeepScout
    scout = ModularDeepScout()
    if wiki_scout is not None:
        scout.wiki_scout = wiki_scout
    if off_verifier is not None:
        scout.off_verifier = off_verifier
    return scout.deep_scan_prospect(prospect)



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
            if any(k in result.get('error', '') for k in ['avslutats', 'avvisades', 'passerats', 'mindre än 30 dagar', 'pågående', 'avslutad', 'misslyckades']):
                return JsonResponse({'status': 'deleted', 'message': result['error']}, status=200)
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
            if prospect.status == 'NEW':
                prospect.status = 'NOT_READY'
                prospect.save()
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


@superuser_or_staff_required
@require_POST
def save_gemini_api_key_view(request):
    """
    Saves or updates GEMINI_API_KEY in the project's .env file and live os.environ.
    Called from Engine Admin Scout UI.
    """
    api_key = request.POST.get('gemini_api_key', '').strip()
    if not api_key:
        messages.error(request, "Ingen API-nyckel angavs.")
        return redirect('/admin-engine/#scout-pane')

    os.environ['GEMINI_API_KEY'] = api_key
    settings.GEMINI_API_KEY = api_key

    # Save to .env file
    env_path = os.path.join(settings.BASE_DIR, '.env')
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('GEMINI_API_KEY='):
                    lines.append(f"GEMINI_API_KEY={api_key}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"GEMINI_API_KEY={api_key}\n")

    with open(env_path, 'w') as f:
        f.writelines(lines)

    messages.success(request, "Google Gemini API-nyckel har sparats och aktiverats i Engine Admin!")
    return redirect('/admin-engine/#scout-pane')




