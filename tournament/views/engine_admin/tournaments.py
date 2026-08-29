import datetime
import logging
import random
import re

from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

logger = logging.getLogger(__name__)
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from tournament.models import Match, ScannedTournament, Team, Tournament
from tournament.services.cache_service import invalidate_tournament_cache
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


@superuser_or_staff_required
@require_POST
def engine_admin_validate_tournament(request: HttpRequest, tournament_id: int) -> JsonResponse:
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


@superuser_or_staff_required
@require_POST
def engine_admin_simulate_tournament(request: HttpRequest, tournament_id: int) -> JsonResponse:
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

    with transaction.atomic():
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
        from tournament.services.scout_service import \
            ensure_complete_knockout_bracket
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
def engine_admin_reset_simulation(request: HttpRequest, tournament_id: int) -> JsonResponse:
    """
    Resets simulated results and advancing teams:
    - If tournament was converted from a ScannedTournament prospect, re-runs convert_scanned_to_live_tournament
      to restore the exact pre-simulation team names, groups, fixtures, and regulations.
    - Otherwise, wipes all simulated match scores/finishes and resets knockout stage match team names back
      to stage placeholders while preserving all group team names intact.
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    scanned = ScannedTournament.objects.filter(converted_tournament=tournament).first()

    with transaction.atomic():
        if scanned:
            from tournament.services.scout_service import \
                convert_scanned_to_live_tournament
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
def engine_admin_toggle_publish(request: HttpRequest, tournament_id: int) -> JsonResponse:
    """
    Toggles tournament between Draft/Testing and Active/Published.
    - BLOCKS activation if Checklist contains ALERTS!
    - ALWAYS WIPES simulated test scores before activating!
    """
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    with transaction.atomic():
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
def engine_admin_preview_tournament(request: HttpRequest, tournament_id: int) -> HttpResponse:
    """Renders detailed structure preview (groups, standings, matches, knockouts) for tournament review."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    from tournament.models import ScannedTournament
    scanned = ScannedTournament.objects.filter(converted_tournament=tournament).first()
    adv_logic = scanned.payload.get('advancement_logic', {}) if scanned and scanned.payload else {}
    teams_adv = adv_logic.get('teams_per_group_advancing') or 2
    total_groups = tournament.tournament_groups.count()

    runners_up_adv = adv_logic.get('runners_up_advancing') or (total_groups if teams_adv >= 2 else 0)
    best_thirds_adv = adv_logic.get('best_third_placed_advancing') or (4 if (tournament.has_best_thirds_table or total_groups == 6) else 0)

    runners_up_table = tournament.get_runners_up_ranking_table()
    host_ranking_table = tournament.get_host_ranking_table()
    best_thirds_table = tournament.get_best_thirds_ranking_table()

    # Rule: If 2 or more teams per group advance directly, ALL runners-up advance directly. No runners-up ranking table is needed!
    if teams_adv >= 2 or (runners_up_adv > 0 and runners_up_adv >= total_groups):
        runners_up_table = None

    groups_data = []
    for group in tournament.tournament_groups.all():
        standings = group.get_standings()
        has_qual = (runners_up_table is not None or best_thirds_table is not None)
        for idx, row in enumerate(standings, start=1):
            row['is_last_advancing'] = (idx == teams_adv and has_qual)
            row['is_last_qualifying'] = (has_qual and idx == teams_adv + 1) or (not has_qual and idx == teams_adv)
            if idx <= teams_adv:
                row['advancement_status'] = 'ADVANCING'
            elif has_qual and idx == teams_adv + 1:
                row['advancement_status'] = 'QUALIFYING'
            else:
                row['advancement_status'] = 'OUT'
                
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

        # Separate Bronze match and Final match if present in the same final stage
        bronze_matches = [
            m for m in matches_list
            if 'loser' in str(m['home_info'].get('display_name', '')).lower()
            or 'loser' in str(m['away_info'].get('display_name', '')).lower()
            or 'brons' in stage.name.lower()
            or '3rd' in stage.name.lower()
            or 'tredje' in stage.name.lower()
        ]
        final_matches = [m for m in matches_list if m not in bronze_matches]

        if bronze_matches and final_matches:
            knockout_data.append({
                'stage_name': 'Bronsmatch',
                'is_bronze': True,
                'matches': bronze_matches,
            })
            knockout_data.append({
                'stage_name': stage.name or 'Final',
                'is_bronze': False,
                'matches': final_matches,
            })
        else:
            knockout_data.append({
                'stage_name': stage.name,
                'is_bronze': 'brons' in stage.name.lower() or '3:e' in stage.name.lower() or 'third' in stage.name.lower(),
                'matches': matches_list,
            })

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
        'runners_up_adv': runners_up_adv,
        'best_thirds_adv': best_thirds_adv,
    }
    return render(request, 'tournament/engine_admin_preview_modal.html', context)


@superuser_or_staff_required
@require_POST
def engine_admin_delete_tournament_view(request: HttpRequest, tournament_id: int) -> JsonResponse:
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
def engine_admin_tournament_details_view(request: HttpRequest, tournament_id: int) -> JsonResponse:
    """Returns full metadata JSON for a live Tournament."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    icon_url = tournament.icon_url
    backdrop_url = tournament.backdrop.url if tournament.backdrop else None
    
    return JsonResponse({
        'status': 'success',
        'tournament': {
            'id': tournament.id,
            'name': tournament.name,
            'sport': getattr(tournament, 'sport', 'Football') or 'Football',
            'start_date': str(tournament.start_date) if tournament.start_date else '',
            'end_date': str(tournament.end_date) if tournament.end_date else '',
            'host_country': tournament.host_country or '',
            'organizer': tournament.organizer or '',
            'official_rules': tournament.official_rules or '',
            'official_regulations_url': tournament.official_regulations_url or '',
            'tournament_summary': tournament.tournament_summary or '',
            'has_best_thirds_table': tournament.has_best_thirds_table,
            'has_runners_up_table': tournament.has_runners_up_table,
            'has_host_ranking_table': tournament.has_host_ranking_table,
            'icon_url': icon_url,
            'backdrop_url': backdrop_url,
            'is_active': tournament.is_active,
            'is_paused': tournament.is_paused,
            'groups_count': tournament.tournament_groups.count(),
            'teams_count': tournament.teams.count(),
            'matches_count': tournament.matches.count(),
        }
    })


@superuser_or_staff_required
@require_POST
def engine_admin_update_tournament(request: HttpRequest, tournament_id: int) -> HttpResponse:
    """Updates tournament details, rules, metadata, logotype (icon), and backdrop banner."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    name = request.POST.get('name', '').strip()
    if not name:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '') or request.POST.get('ajax') == '1':
            return JsonResponse({'status': 'error', 'message': 'Turneringsnamnet kan inte vara tomt.'}, status=400)
        messages.error(request, 'Turneringsnamnet kan inte vara tomt.')
        return redirect('/engine-admin/')

    tournament.name = name

    # Update metadata fields
    if 'sport' in request.POST:
        tournament.sport = request.POST.get('sport', '').strip() or 'Football'
    
    from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
    if 'start_date' in request.POST:
        raw_s = request.POST.get('start_date', '').strip()
        iso_s = LLMWikipediaScout._parse_date_string(raw_s) if raw_s else ''
        tournament.start_date = datetime.date.fromisoformat(iso_s) if iso_s else None

    if 'end_date' in request.POST:
        raw_e = request.POST.get('end_date', '').strip()
        iso_e = LLMWikipediaScout._parse_date_string(raw_e) if raw_e else ''
        tournament.end_date = datetime.date.fromisoformat(iso_e) if iso_e else None

    if 'host_country' in request.POST:
        tournament.host_country = request.POST.get('host_country', '').strip()

    if 'organizer' in request.POST:
        tournament.organizer = request.POST.get('organizer', '').strip()

    if 'official_rules' in request.POST:
        tournament.official_rules = request.POST.get('official_rules', '').strip()

    if 'official_regulations_url' in request.POST:
        tournament.official_regulations_url = request.POST.get('official_regulations_url', '').strip()

    if 'tournament_summary' in request.POST:
        tournament.tournament_summary = request.POST.get('tournament_summary', '').strip()

    if 'has_best_thirds_table' in request.POST:
        tournament.has_best_thirds_table = request.POST.get('has_best_thirds_table') in ['true', '1', 'on']

    if 'has_runners_up_table' in request.POST:
        tournament.has_runners_up_table = request.POST.get('has_runners_up_table') in ['true', '1', 'on']

    if 'has_host_ranking_table' in request.POST:
        tournament.has_host_ranking_table = request.POST.get('has_host_ranking_table') in ['true', '1', 'on']

    # Also update linked MasterEvent if exists
    if tournament.master_event:
        me = tournament.master_event
        me.name = tournament.name
        me.save()

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

    icon_url = tournament.icon_url
    backdrop_url = tournament.backdrop.url if tournament.backdrop else None

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '') or request.POST.get('ajax') == '1':
        return JsonResponse({
            'status': 'success',
            'message': f'Turneringen "{tournament.name}" har sparats!',
            'tournament': {
                'id': tournament.id,
                'name': tournament.name,
                'sport': tournament.sport,
                'start_date': str(tournament.start_date) if tournament.start_date else '',
                'end_date': str(tournament.end_date) if tournament.end_date else '',
                'host_country': tournament.host_country,
                'organizer': tournament.organizer,
                'icon_url': icon_url,
                'backdrop_url': backdrop_url,
            }
        })

    messages.success(request, f'Turneringen "{tournament.name}" har sparats!')
    return redirect('/engine-admin/')


@superuser_or_staff_required
def engine_admin_groups_teams_view(request: HttpRequest, tournament_id: int) -> JsonResponse:
    """Returns groups, team rosters, and match schedules for live editing."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    groups_list = []
    for g in tournament.tournament_groups.all().order_by('order', 'name'):
        teams_data = []
        for t in g.teams.all().order_by('name'):
            teams_data.append({
                'id': t.id,
                'name': t.name,
                'code': t.code,
                'flag_url': t.flag_url,
                'badge_url': t.badge_url,
                'emblem_url': t.emblem_url,
            })
        groups_list.append({
            'id': g.id,
            'name': g.name,
            'order': g.order,
            'teams': teams_data,
        })
        
    matches_list = []
    for m in tournament.matches.all().order_by('match_number', 'date_time'):
        matches_list.append({
            'id': m.id,
            'match_number': m.match_number,
            'stage_or_group': m.group.name if m.group else (m.stage.name if m.stage else 'Match'),
            'home_team': m.home_team,
            'away_team': m.away_team,
            'date_time': m.date_time.strftime('%Y-%m-%d %H:%M') if m.date_time else '',
            'venue': m.venue or '',
            'is_finished': m.is_finished,
            'home_goals': m.home_goals,
            'away_goals': m.away_goals,
        })
        
    return JsonResponse({
        'status': 'success',
        'tournament_id': tournament.id,
        'tournament_name': tournament.name,
        'groups': groups_list,
        'matches': matches_list,
    })


@superuser_or_staff_required
@require_POST
def engine_admin_save_team_view(request: HttpRequest, tournament_id: int) -> JsonResponse:
    """Updates team name, code, or emblem URL."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    team_id = request.POST.get('team_id')
    team = get_object_or_404(Team, id=team_id, tournament=tournament)
    
    name = request.POST.get('name', '').strip()
    code = request.POST.get('code', '').strip()
    emblem_url = request.POST.get('emblem_url', '').strip()
    
    if name:
        team.name = name
    if 'code' in request.POST:
        team.code = code
    if 'emblem_url' in request.POST:
        team.emblem_url = emblem_url
    team.save()
    invalidate_tournament_cache(tournament.id)
    
    return JsonResponse({
        'status': 'success',
        'message': f'Laget "{team.name}" uppdaterades!',
        'team': {
            'id': team.id,
            'name': team.name,
            'code': team.code,
            'badge_url': team.badge_url,
            'flag_url': team.flag_url,
        }
    })


@superuser_or_staff_required
@require_POST
def engine_admin_save_match_view(request: HttpRequest, tournament_id: int) -> JsonResponse:
    """Updates match fixture schedule (date_time, venue, home_team, away_team)."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    match_id = request.POST.get('match_id')
    match = get_object_or_404(Match, id=match_id, tournament=tournament)
    
    home_team = request.POST.get('home_team', '').strip()
    away_team = request.POST.get('away_team', '').strip()
    venue = request.POST.get('venue', '').strip()
    date_time_str = request.POST.get('date_time', '').strip()
    
    if home_team:
        match.home_team = home_team
    if away_team:
        match.away_team = away_team
    if 'venue' in request.POST:
        match.venue = venue
        
    if date_time_str:
        try:
            dt = datetime.datetime.fromisoformat(date_time_str.replace(' ', 'T'))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            match.date_time = dt
        except Exception:
            pass
            
    match.save()
    invalidate_tournament_cache(tournament.id)
    
    return JsonResponse({
        'status': 'success',
        'message': f'Match #{match.match_number} uppdaterades!',
        'match': {
            'id': match.id,
            'match_number': match.match_number,
            'home_team': match.home_team,
            'away_team': match.away_team,
            'venue': match.venue,
            'date_time': match.date_time.strftime('%Y-%m-%d %H:%M') if match.date_time else '',
        }
    })

