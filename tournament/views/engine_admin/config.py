import logging
import os

from django.conf import settings
from django.shortcuts import get_object_or_404, redirect

logger = logging.getLogger(__name__)
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from tournament.models import (PointSystem, PoolAdminRequest, Sidebet,
                               Tournament)
from tournament.services.pool_admin_service import (approve_pool_admin_request,
                                                    reject_pool_admin_request)
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
def engine_admin_pool_requests_view(request: HttpRequest) -> JsonResponse:
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
def engine_admin_approve_pool_request_view(request: HttpRequest, request_id: int) -> JsonResponse:
    pool_request = get_object_or_404(PoolAdminRequest, id=request_id)
    try:
        approve_pool_admin_request(pool_request, request.user)
        return JsonResponse({'status': 'success', 'message': 'Förfrågan godkänd.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@superuser_or_staff_required
@require_POST
def engine_admin_reject_pool_request_view(request: HttpRequest, request_id: int) -> JsonResponse:
    pool_request = get_object_or_404(PoolAdminRequest, id=request_id)
    rejection_reason = request.POST.get('rejection_reason', '')
    try:
        reject_pool_admin_request(pool_request, request.user, rejection_reason)
        return JsonResponse({'status': 'success', 'message': 'Förfrågan avvisad.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@superuser_or_staff_required
def tournament_points_sidebets_get_view(request: HttpRequest, tournament_id: int) -> JsonResponse:
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
def tournament_points_save_view(request: HttpRequest, tournament_id: int) -> JsonResponse:
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
def tournament_sidebet_save_view(request: HttpRequest, tournament_id: int) -> JsonResponse:
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
def tournament_sidebet_delete_view(request: HttpRequest, tournament_id: int, sidebet_id: int) -> JsonResponse:
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
def save_gemini_api_key_view(request: HttpRequest) -> HttpResponse:
    """
    Saves or updates GEMINI_API_KEY in the project's .env file and live os.environ.
    Called from Engine Admin Scout UI.
    """
    api_key = request.POST.get('gemini_api_key', '').strip()
    if not api_key:
        messages.error(request, "Ingen API-nyckel angavs.")
        return redirect('/admin-engine/#scout-pane')

    import re
    if not re.match(r'^[A-Za-z0-9_\-]+$', api_key):
        messages.error(request, "Ogiltigt format på API-nyckel. Endast bokstäver, siffror, understreck och bindestreck är tillåtna.")
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

