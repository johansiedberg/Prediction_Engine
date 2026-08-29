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
        
        group_completed = (total_group > 0 and group_preds >= total_group)
        group_started = (group_preds > 0)
        
        knockout_completed = (total_knockout > 0 and knockout_preds >= total_knockout)
        knockout_started = (knockout_preds > 0)
        
        sidebets_completed = (total_sidebets > 0 and sidebet_answers >= total_sidebets)
        sidebets_started = (sidebet_answers > 0)
        
        # Check if all available sections are fully predicted
        req_group_done = (total_group == 0 or group_completed)
        req_ko_done = (total_knockout == 0 or knockout_completed)
        req_sb_done = (total_sidebets == 0 or sidebets_completed)
        total_fixtures = total_group + total_knockout + total_sidebets
        
        is_tour_locked = tournament.is_locked_by_time
        is_sub_saved = (submission.is_saved if submission else False) or is_tour_locked
        is_sub_verified = (submission.is_verified if submission else False) or is_tour_locked

        if is_tour_locked:
            submission_status = 'verified'
            status_label = 'Låst (Mästerskapet startat)'
            overall_status = 'Completed'
        elif is_sub_verified:
            submission_status = 'verified'
            status_label = 'Låst'
            overall_status = 'Completed'
        elif is_sub_saved:
            submission_status = 'saved_pending'
            status_label = 'Sparad • Väntar på lås'
            overall_status = 'Saved'
        elif has_any_pred:
            submission_status = 'in_progress'
            status_label = 'Påbörjad'
            overall_status = 'In Progress'
        else:
            submission_status = 'not_started'
            status_label = 'Ej startad'
            overall_status = 'Not Started'
        
        players_data.append({
            'player': player,
            'member': member,
            'name': f"{player.first_name} {player.last_name}".strip() or player.email,
            'first_name': player.first_name.strip() or player.email.split('@')[0].capitalize(),
            'email': player.email,
            'date_joined': player.date_joined,
            'last_login': player.last_login,
            'is_verified': member.is_verified if member else True,
            'has_started': has_any_pred,
            'group_predicted': group_preds,
            'group_total': total_group,
            'group_stage_completed': group_completed,
            'group_stage_started': group_started,
            'has_group': total_group > 0,
            'knockout_predicted': knockout_preds,
            'knockout_total': total_knockout,
            'knockout_stage_completed': knockout_completed,
            'knockout_stage_started': knockout_started,
            'has_knockout': total_knockout > 0,
            'sidebets_answered': sidebet_answers,
            'sidebets_total': total_sidebets,
            'sidebets_completed': sidebets_completed,
            'sidebets_started': sidebets_started,
            'has_sidebets': total_sidebets > 0,
            'overall_status': overall_status,
            'submission_status': submission_status,
            'status_label': status_label,
            'is_saved_submission': is_sub_saved,
            'is_verified_submission': is_sub_verified,
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
