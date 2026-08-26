from django.contrib.auth.models import User
from django.utils import timezone
from tournament.models import League, LeagueMember, Tournament, Match, MatchPrediction, TournamentSubmission, Sidebet, SidebetAnswer

def get_player_progress_matrix(league, tournament):
    """Compute player progress monitoring matrix for Pool-Admin.
    Returns list of dicts with player info and prediction completion status."""
    players = tournament.players.all().distinct().order_by('first_name', 'last_name', 'email')
    players_data = []
    
    all_group_matches = Match.objects.filter(tournament=tournament, group__isnull=False)
    all_knockout_matches = Match.objects.filter(tournament=tournament, stage__isnull=False)
    all_sidebets = Sidebet.objects.filter(tournament=tournament)
    
    total_group = all_group_matches.count()
    total_knockout = all_knockout_matches.count()
    total_sidebets = all_sidebets.count()
    
    for player in players:
        member = LeagueMember.objects.filter(league=league, player=player).first()
        submission = TournamentSubmission.objects.filter(tournament=tournament, player=player).first()
        
        group_preds = MatchPrediction.objects.filter(match__in=all_group_matches, player=player).count()
        knockout_preds = MatchPrediction.objects.filter(match__in=all_knockout_matches, player=player).count()
        sidebet_answers = SidebetAnswer.objects.filter(sidebet__in=all_sidebets, player=player).count()
        
        has_any_pred = (group_preds + knockout_preds + sidebet_answers) > 0
        
        if total_group > 0 and group_preds >= total_group and total_knockout > 0 and knockout_preds >= total_knockout and total_sidebets > 0 and sidebet_answers >= total_sidebets:
            overall_status = 'Complete'
        elif has_any_pred:
            overall_status = 'In Progress'
        else:
            overall_status = 'Not Started'
        
        players_data.append({
            'player': player,
            'member': member,
            'name': f"{player.first_name} {player.last_name}".strip() or player.email,
            'email': player.email,
            'date_joined': player.date_joined,
            'last_login': player.last_login,
            'is_verified': member.is_verified if member else True,
            'has_started': has_any_pred,
            'group_predicted': group_preds,
            'group_total': total_group,
            'knockout_predicted': knockout_preds,
            'knockout_total': total_knockout,
            'sidebets_answered': sidebet_answers,
            'sidebets_total': total_sidebets,
            'overall_status': overall_status,
            'is_verified_submission': submission.is_verified if submission else False,
        })
    
    return players_data


def approve_pool_admin_request(pool_request, reviewed_by):
    """Approve a PoolAdminRequest: create League, auto-enroll user as verified member."""
    from tournament.models import PoolAdminRequest

    league = League.objects.create(
        master_event=pool_request.master_event,
        name=pool_request.pool_name,
        description=pool_request.description or '',
        admin=pool_request.user,
    )
    LeagueMember.objects.create(
        league=league,
        player=pool_request.user,
        is_verified=True,
    )

    pool_request.status = 'APPROVED'
    pool_request.reviewed_at = timezone.now()
    pool_request.reviewed_by = reviewed_by
    pool_request.league = league  # Link back so admin can navigate to the created league
    pool_request.save()

    return league


def reject_pool_admin_request(pool_request, reviewed_by, reason=''):
    """Reject a PoolAdminRequest with optional reason."""
    pool_request.status = 'REJECTED'
    pool_request.reviewed_at = timezone.now()
    pool_request.reviewed_by = reviewed_by
    pool_request.rejection_reason = reason
    pool_request.save()
