import datetime
import json
import logging
import re

from django.conf import settings
from django.shortcuts import redirect, render

logger = logging.getLogger(__name__)
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Count, F, Max, Q
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from tournament.models import (League, LeagueMember, MatchPrediction,
                               ScannedTournament, Tournament)
from tournament.services.tournament_admin import (
    get_tournament_checklist_status, get_tournament_total_status)
from tournament.views.auth import superuser_or_staff_required

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


def engine_admin_root_view(request: HttpRequest) -> HttpResponse:
    """Entry point for Port 2029 (Engine Admin). Shows Dashboard if logged in as standalone system Engine Admin ('johansiedberg'), else Login form."""
    if request.user.is_authenticated and request.user.is_superuser:
        return engine_admin_dashboard_view(request)
    return render(request, 'tournament/engine_admin_login.html')


def engine_admin_login_view(request: HttpRequest) -> HttpResponse:
    """Processes login specifically for Port 2029 Engine Admin (Restricted strictly to system admin 'johansiedberg')."""
    if request.method == 'POST':
        login_input = request.POST.get('email', '').strip() or request.POST.get('username', '').strip()
        pwd = request.POST.get('password', '').strip()
        user = authenticate(request, username=login_input, password=pwd)
        if user is None:
            user_obj = User.objects.filter(email__iexact=login_input).first()
            if user_obj:
                user = authenticate(request, username=user_obj.username, password=pwd)
        if user is not None and user.is_superuser:
            login(request, user)
            return redirect('/')
        else:
            messages.error(request, "Tillgång nekad: Endast det dedikerade Engine Admin-systemkontot har behörighet till Port 2029.")
    return render(request, 'tournament/engine_admin_login.html')


def engine_admin_logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect('/')


@superuser_or_staff_required
def engine_admin_dashboard_view(request: HttpRequest) -> HttpResponse:
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

    # NOTE: auto_rescan_due_watchlist_prospects() removed from dashboard load
    # to prevent blocking I/O (external scraping/LLM calls) during page render.
    # Rescanning is triggered explicitly via the Scout UI or management command.

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
                    from tournament.services.team_badge_service import \
                        TeamBadgeService
                    b = TeamBadgeService.resolve_team_badge(h_name, sport=p.sport or 'Football', tournament_name=p.name, use_gemini_fallback=False)
                    if b.flag_url: f_copy['home_team_flag_url'] = b.flag_url
                    if b.emblem_url: f_copy['home_team_emblem_url'] = b.emblem_url
                    if b.code: f_copy['home_team_code'] = b.code

                if a_name in team_badge_map:
                    if not f_copy.get('away_team_flag_url'): f_copy['away_team_flag_url'] = team_badge_map[a_name]['flag_url']
                    if not f_copy.get('away_team_emblem_url'): f_copy['away_team_emblem_url'] = team_badge_map[a_name]['emblem_url']
                    if not f_copy.get('away_team_code'): f_copy['away_team_code'] = team_badge_map[a_name]['code']
                elif a_name and not f_copy.get('away_team_flag_url') and not f_copy.get('away_team_emblem_url'):
                    from tournament.services.team_badge_service import \
                        TeamBadgeService
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
                            from tournament.services.team_badge_service import \
                                TeamBadgeService
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
                            from tournament.services.team_badge_service import \
                                TeamBadgeService
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
        if draw_date_val:
            try:
                from dateutil import parser
                parsed_d = parser.parse(str(draw_date_val), fuzzy=True).date()
                draw_date_val = parsed_d.strftime('%Y-%m-%d')
            except Exception:
                from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                iso_d = LLMWikipediaScout._parse_date_string(str(draw_date_val))
                if iso_d:
                    draw_date_val = iso_d
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

