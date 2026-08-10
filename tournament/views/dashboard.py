# Dashboard and Hub views - main player-facing pages
import json
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404

from tournament.models import (
    Tournament, Match, MatchPrediction, TournamentSubmission, Sidebet, SidebetAnswer,
    Group, Team, StaticInsight, DailyGazette, UserProfile, League, LeagueMember
)
from tournament.services.scoring import calc_pred_points, calc_pred_points_detail
from tournament.services.analytics import generate_ai_match_analysis
from tournament.editorial_engine.static_generators import generate_static_insights
from tournament.editorial_engine.compiler import load_player_personas, find_persona_for_player


@login_required(login_url='/')
def dashboard_view(request):
    active_tournaments = list(Tournament.objects.filter(is_active=True))
    if not active_tournaments:
        return render(request, 'tournament/no_active.html')

    # Resolve selected tournament (from GET parameter, session, or user profile)
    selected_t_id = request.GET.get('tournament_id')
    if selected_t_id and selected_t_id.isdigit():
        target_t = Tournament.objects.filter(id=int(selected_t_id), is_active=True).first()
        if target_t:
            active_tournament = target_t
            request.session['selected_tournament_id'] = active_tournament.id
            if hasattr(request.user, 'profile'):
                request.user.profile.last_selected_tournament = active_tournament
                request.user.profile.save()
        else:
            active_tournament = active_tournaments[0]
    else:
        session_t_id = request.session.get('selected_tournament_id')
        user_prof_t = getattr(request.user, 'profile', None)
        prof_t = user_prof_t.last_selected_tournament if (user_prof_t and user_prof_t.last_selected_tournament and user_prof_t.last_selected_tournament.is_active) else None

        if session_t_id and any(t.id == session_t_id for t in active_tournaments):
            active_tournament = next(t for t in active_tournaments if t.id == session_t_id)
        elif prof_t:
            active_tournament = prof_t
            request.session['selected_tournament_id'] = active_tournament.id
        else:
            active_tournament = active_tournaments[0]
            request.session['selected_tournament_id'] = active_tournament.id

    is_player = False

    is_admin = False
    submission = None
    all_matches = []
    upcoming_matches = []
    finished_matches = []
    next_match = None
    last_finished_match = None
    last_finished_user_points = 0
    user_predictions = {}
    leaderboard = []
    match_analytics = {}
    point_system = getattr(active_tournament, 'point_system', None) if active_tournament else None

    # Resolve User Joined Leagues for Multi-Pool Switcher
    user_memberships = list(LeagueMember.objects.filter(player=request.user, league__is_active=True).select_related('league')) if request.user.is_authenticated else []
    user_leagues = [m.league for m in user_memberships]
    
    session_league_id = request.session.get('active_league_id')
    active_league = None
    if session_league_id:
        active_league = next((l for l in user_leagues if l.id == session_league_id), None)
    if not active_league and user_leagues:
        active_league = user_leagues[0]
    if not active_league:
        active_league = League.objects.filter(is_active=True).first()

    # Prediction Data for Main Frame Tab
    groups = active_tournament.tournament_groups.prefetch_related('teams', 'matches')
    knockout_stages = list(active_tournament.knockout_stages.prefetch_related('matches'))
    knockout_stages.sort(key=lambda s: s.matches.order_by('match_number').first().match_number if s.matches.exists() else 999)

    groups_data = {}
    group_matches = {}
    for group in groups:
        groups_data[str(group.id)] = [team.name for team in group.teams.all()]
        group_matches[str(group.id)] = [
            {
                'id': str(match.id),
                'home': match.get_home_team_info()['name'],
                'away': match.get_away_team_info()['name']
            }
            for match in group.matches.all()
        ]

    sidebets = active_tournament.sidebets.all()
    tournament_teams = active_tournament.teams.all().order_by('name')
    user_sidebet_answers = {
        a.sidebet_id: a.answer for a in SidebetAnswer.objects.filter(sidebet__tournament=active_tournament, player=request.user)
    }
    active_tab = request.GET.get('active_tab', '')
    active_tab_name = request.GET.get('tab', 'home')

    # Handle Prediction POST submission directly within dashboard main frame
    if request.method == 'POST':
        for key, value in request.POST.items():
            if key.startswith('home_'):
                match_id = key.split('_')[1]
                home_val = value
                away_val = request.POST.get(f'away_{match_id}', '')
                if home_val != '' and away_val != '':
                    match_obj = get_object_or_404(Match, id=match_id, tournament=active_tournament)
                    pen_winner = request.POST.get(f'penalty_winner_{match_id}', '').strip()
                    pred_phase = 'ACTUAL_KNOCKOUT' if (active_tournament.is_actual_knockout_open and match_obj.stage) else 'INITIAL_BRACKET'
                    MatchPrediction.objects.update_or_create(
                        match=match_obj,
                        player=request.user,
                        defaults={
                            'home_goals': int(home_val),
                            'away_goals': int(away_val),
                            'penalty_winner': pen_winner if pen_winner else None,
                            'prediction_phase': pred_phase
                        }
                    )
            elif key.startswith('sidebet_'):
                sidebet_id = key.split('_')[1]
                ans_val = value.strip()
                if ans_val != '':
                    sidebet_obj = get_object_or_404(Sidebet, id=sidebet_id, tournament=active_tournament)
                    SidebetAnswer.objects.update_or_create(
                        sidebet=sidebet_obj,
                        player=request.user,
                        defaults={'answer': ans_val}
                    )

        TournamentSubmission.objects.update_or_create(
            tournament=active_tournament,
            player=request.user,
            defaults={'is_saved': True}
        )
        post_active_tab = request.POST.get('active_tab', '').strip()
        if post_active_tab:
            return redirect(f'/dashboard/?tab=predictions&active_tab={post_active_tab}')
        return redirect('/dashboard/?tab=predictions')

    if active_tournament:
        is_player = active_tournament.players.filter(id=request.user.id, is_staff=False, is_superuser=False).exists() and not (request.user.is_staff or request.user.is_superuser)
        submission = TournamentSubmission.objects.filter(tournament=active_tournament, player=request.user).first()
        
        now = timezone.now()
        matches_qs = Match.objects.filter(tournament=active_tournament).order_by('date_time', 'match_number')
        all_matches = list(matches_qs)
        
        finished_matches = [m for m in all_matches if m.is_finished or (m.home_goals is not None and m.away_goals is not None)]
        
        # 1. Look for unplayed matches scheduled for the future (date_time > now)
        future_unplayed = [m for m in all_matches if not m.is_finished and (m.home_goals is None or m.away_goals is None) and m.date_time and m.date_time >= now]
        
        # 2. Look for any unplayed match (in case time is slightly past but score not yet entered)
        all_unplayed = [m for m in all_matches if not m.is_finished and (m.home_goals is None or m.away_goals is None)]
        
        if future_unplayed:
            next_match = future_unplayed[0]
        elif all_unplayed:
            next_match = all_unplayed[0]
        else:
            next_match = all_matches[0] if all_matches else None
            
        upcoming_matches = future_unplayed if future_unplayed else all_unplayed
        last_finished_match = finished_matches[-1] if finished_matches else (all_matches[0] if all_matches else None)

        user_preds_qs = MatchPrediction.objects.filter(match__tournament=active_tournament, player=request.user)
        user_predictions = {p.match_id: p for p in user_preds_qs}

        if last_finished_match:
            u_pred = user_predictions.get(last_finished_match.id)
            last_finished_user_points = calc_pred_points(u_pred, last_finished_match, point_system)

        # Build Stage Breakdown Leaderboards (Excluding Admin/Staff users)
        players = list(active_tournament.players.filter(is_staff=False, is_superuser=False))

        leaderboard = []
        leaderboard_group_matches = []
        leaderboard_group_standings = []
        leaderboard_third_place = []
        leaderboard_knockout = []
        leaderboard_sidebets = []

        all_groups = list(active_tournament.tournament_groups.prefetch_related('teams', 'matches').all())

        for p in players:
            p_sub = TournamentSubmission.objects.filter(tournament=active_tournament, player=p).first()
            p_preds = MatchPrediction.objects.filter(match__tournament=active_tournament, player=p).select_related('match')

            gm_pts = 0
            gm_fullpott = 0
            gm_ratt_mal = 0
            gm_ratt_tecken = 0

            ko_pts = 0
            ko_fullpott = 0
            ko_ratt_mal = 0
            ko_ratt_tecken = 0

            for pred in p_preds:
                m = pred.match
                pts = calc_pred_points(pred, m, point_system)
                is_finished = m.is_finished or (m.home_goals is not None and m.away_goals is not None)

                if is_finished:
                    is_exact = (pred.home_goals == m.home_goals and pred.away_goals == m.away_goals)
                    correct_home_g = (pred.home_goals == m.home_goals)
                    correct_away_g = (pred.away_goals == m.away_goals)
                    goals_matched = (1 if correct_home_g else 0) + (1 if correct_away_g else 0)

                    actual_1x2 = '1' if m.home_goals > m.away_goals else ('2' if m.away_goals > m.home_goals else 'X')
                    pred_1x2 = '1' if pred.home_goals > pred.away_goals else ('2' if pred.away_goals > pred.home_goals else 'X')
                    is_correct_1x2 = (actual_1x2 == pred_1x2)

                    if m.group_id:
                        gm_pts += pts
                        if is_exact: gm_fullpott += 1
                        gm_ratt_mal += goals_matched
                        if is_correct_1x2: gm_ratt_tecken += 1
                    else:
                        ko_pts += pts
                        if is_exact: ko_fullpott += 1
                        ko_ratt_mal += goals_matched
                        if is_correct_1x2: ko_ratt_tecken += 1

            gs_pts = 0
            gs_ratt_placering = 0
            gs_ratt_lagpoang = 0
            gs_ratt_malskillnad = 0

            p_preds_dict = {pred.match_id: pred for pred in p_preds}

            for g in all_groups:
                g_m_list = list(g.matches.all())
                is_g_finished = len(g_m_list) > 0 and all(m.home_goals is not None and m.away_goals is not None for m in g_m_list)
                if is_g_finished:
                    st = g.get_standings()
                    pred_dict = {}
                    for row in st:
                        t_name = row['team'].name if hasattr(row['team'], 'name') else str(row['team'])
                        pred_dict[t_name] = {
                            'team': row['team'], 'played': 0, 'won': 0, 'drawn': 0, 'lost': 0,
                            'gf': 0, 'ga': 0, 'gd': 0, 'points': 0
                        }
                    for m in g_m_list:
                        u_p = p_preds_dict.get(m.id)
                        if u_p is not None and m.home_team and m.away_team:
                            ht, at = m.home_team.strip(), m.away_team.strip()
                            if ht in pred_dict and at in pred_dict:
                                hg, ag = u_p.home_goals, u_p.away_goals
                                pred_dict[ht]['played'] += 1
                                pred_dict[at]['played'] += 1
                                pred_dict[ht]['gf'] += hg
                                pred_dict[ht]['ga'] += ag
                                pred_dict[at]['gf'] += ag
                                pred_dict[at]['ga'] += hg
                                pred_dict[ht]['gd'] += (hg - ag)
                                pred_dict[at]['gd'] += (ag - hg)
                                if hg > ag:
                                    pred_dict[ht]['won'] += 1
                                    pred_dict[ht]['points'] += 3
                                    pred_dict[at]['lost'] += 1
                                elif hg < ag:
                                    pred_dict[at]['won'] += 1
                                    pred_dict[at]['points'] += 3
                                    pred_dict[ht]['lost'] += 1
                                else:
                                    pred_dict[ht]['drawn'] += 1
                                    pred_dict[at]['drawn'] += 1
                                    pred_dict[ht]['points'] += 1
                                    pred_dict[at]['points'] += 1

                    sorted_p_list = list(pred_dict.values())
                    sorted_p_list.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
                    p_rank_map = {}
                    for r_idx, p_item in enumerate(sorted_p_list, 1):
                        t_k = p_item['team'].name if hasattr(p_item['team'], 'name') else str(p_item['team'])
                        p_rank_map[t_k] = {'pred_rank': r_idx, 'pred_points': p_item['points'], 'pred_gd': p_item['gd']}

                    p_plac_val = point_system.group_correct_placement if point_system else 2
                    p_lagp_val = point_system.group_correct_points if point_system else 1
                    p_gd_val = point_system.group_correct_goal_diff if point_system else 1

                    for rank_idx, row in enumerate(st, 1):
                        t_k = row['team'].name if hasattr(row['team'], 'name') else str(row['team'])
                        p_info = p_rank_map.get(t_k, {'pred_rank': '-', 'pred_points': 0, 'pred_gd': 0})
                        c_plac = (rank_idx == p_info['pred_rank'])
                        c_lagp = (row['points'] == p_info['pred_points'])
                        c_gd = (row['gd'] == p_info['pred_gd'])

                        if c_plac:
                            gs_ratt_placering += 1
                            gs_pts += p_plac_val
                        if c_lagp:
                            gs_ratt_lagpoang += 1
                            gs_pts += p_lagp_val
                        if c_gd:
                            gs_ratt_malskillnad += 1
                            gs_pts += p_gd_val

            tp_pts = 0
            tp_ratt_lag = 0

            sb_pts = 0
            sb_ratt_antal = 0
            p_sidebet_answers = SidebetAnswer.objects.filter(sidebet__tournament=active_tournament, player=p).select_related('sidebet')
            for ans in p_sidebet_answers:
                if ans.sidebet.is_answer_correct(ans.answer):
                    sb_pts += ans.sidebet.points
                    sb_ratt_antal += 1

            tot_pts = gm_pts + gs_pts + tp_pts + ko_pts + sb_pts

            p_name = f"{p.first_name} {p.last_name}".strip() if p.first_name else p.username
            p_verified = p_sub.is_verified if p_sub else False

            leaderboard.append({
                'player': p,
                'name': p_name,
                'points': tot_pts,
                'trend': 0,
                'is_verified': p_verified
            })
            leaderboard_group_matches.append({
                'player': p,
                'name': p_name,
                'points': gm_pts,
                'fullpott': gm_fullpott,
                'ratt_mal': gm_ratt_mal,
                'ratt_tecken': gm_ratt_tecken,
                'is_verified': p_verified
            })
            leaderboard_group_standings.append({
                'player': p,
                'name': p_name,
                'points': gs_pts,
                'ratt_placering': gs_ratt_placering,
                'ratt_lagpoang': gs_ratt_lagpoang,
                'ratt_malskillnad': gs_ratt_malskillnad,
                'is_verified': p_verified
            })
            leaderboard_third_place.append({
                'player': p,
                'name': p_name,
                'points': tp_pts,
                'ratt_lag': tp_ratt_lag,
                'is_verified': p_verified
            })
            leaderboard_knockout.append({
                'player': p,
                'name': p_name,
                'points': ko_pts,
                'fullpott': ko_fullpott,
                'ratt_mal': ko_ratt_mal,
                'ratt_tecken': ko_ratt_tecken,
                'is_verified': p_verified
            })
            leaderboard_sidebets.append({
                'player': p,
                'name': p_name,
                'points': sb_pts,
                'ratt_antal': sb_ratt_antal,
                'is_verified': p_verified
            })

        leaderboard.sort(key=lambda x: x['points'], reverse=True)
        leaderboard_group_matches.sort(key=lambda x: (x['points'], x['fullpott'], x['ratt_tecken']), reverse=True)
        leaderboard_group_standings.sort(key=lambda x: (x['points'], x['ratt_placering'], x['ratt_lagpoang'], x['ratt_malskillnad']), reverse=True)
        leaderboard_third_place.sort(key=lambda x: (x['points'], x['ratt_lag']), reverse=True)
        leaderboard_knockout.sort(key=lambda x: (x['points'], x['fullpott'], x['ratt_tecken']), reverse=True)
        leaderboard_sidebets.sort(key=lambda x: (x['points'], x['ratt_antal']), reverse=True)

        personas_list = load_player_personas()
        # Build Match Analytics for all matches
        for m in all_matches:
            all_preds = list(MatchPrediction.objects.filter(match=m).select_related('player'))
            total_preds = len(all_preds)

            is_reported = m.is_finished or (m.home_goals is not None and m.away_goals is not None)
            actual_score = f"{m.home_goals} - {m.away_goals}" if is_reported else "- : -"

            home_preds = []
            draw_preds = []
            away_preds = []

            for p_pred in all_preds:
                p_user = p_pred.player
                p_name = f"{p_user.first_name} {p_user.last_name}".strip() if p_user.first_name else p_user.username
                persona = find_persona_for_player(p_name, personas_list)
                u_nick = persona.get('nicknames', [p_name])[0] if persona else (p_user.first_name or p_user.username)
                item = {
                    'username': u_nick,
                    'home_goals': p_pred.home_goals,
                    'away_goals': p_pred.away_goals,
                    'penalty_winner': p_pred.penalty_winner,
                }
                if p_pred.home_goals > p_pred.away_goals:
                    home_preds.append(item)
                elif p_pred.home_goals == p_pred.away_goals:
                    draw_preds.append(item)
                else:
                    away_preds.append(item)

            home_preds.sort(key=lambda x: (x['home_goals'], x['home_goals'] + x['away_goals']), reverse=True)
            draw_preds.sort(key=lambda x: (x['home_goals'] + x['away_goals']), reverse=True)
            away_preds.sort(key=lambda x: (x['away_goals'], x['home_goals'] + x['away_goals']), reverse=True)

            h_cnt = len(home_preds)
            d_cnt = len(draw_preds)
            a_cnt = len(away_preds)

            h_pct = round((h_cnt / total_preds * 100)) if total_preds > 0 else 0
            d_pct = round((d_cnt / total_preds * 100)) if total_preds > 0 else 0
            a_pct = round((a_cnt / total_preds * 100)) if total_preds > 0 else 0

            user_p = user_predictions.get(m.id)
            ai_analysis = generate_ai_match_analysis(user_p, m, home_preds + draw_preds + away_preds, h_cnt, d_cnt, a_cnt, total_preds)

            match_analytics[m.id] = {
                'total_preds': total_preds,
                'is_reported': is_reported,
                'actual_score': actual_score,
                'home_cnt': h_cnt,
                'draw_cnt': d_cnt,
                'away_cnt': a_cnt,
                'home_pct': h_pct,
                'draw_pct': d_pct,
                'away_pct': a_pct,
                'home_preds': home_preds,
                'draw_preds': draw_preds,
                'away_preds': away_preds,
                'ai_analysis': ai_analysis,
                'user_detail': calc_pred_points_detail(user_p, m, point_system),
            }
    
    is_admin = request.user.is_staff or request.user.is_superuser
    point_system = getattr(active_tournament, 'point_system', None) if active_tournament else None

    # Group Tables, Group Stage Full Data & Third Place Standings calculation
    is_qualifying = bool(active_tournament and ('qualifying' in active_tournament.name.lower() or len(all_groups) >= 10))

    group_stage_full_data = []
    group_tables_data = []
    third_place_teams = []
    pred_third_place_teams = []

    for g in all_groups:
        st = g.get_standings()
        group_tables_data.append({
            'group': g,
            'standings': st
        })
        
        # Extract target team for cross-group ranking: Runner-up (2nd place) for Qualifier, 3rd place for Final Tournament
        target_idx = 1 if is_qualifying else 2
        if len(st) > target_idx:
            t_target = dict(st[target_idx])
            t_target['group_name'] = g.name
            
            # If Qualifier and group has 5 teams, discard matches against 5th team for fair 8-match comparison
            if is_qualifying and len(st) >= 5:
                fifth_team_name = st[4]['team'].name if hasattr(st[4]['team'], 'name') else str(st[4]['team'])
                target_team_name = t_target['team'].name if hasattr(t_target['team'], 'name') else str(t_target['team'])
                
                g_matches_ex_5th = [m for m in all_matches if m.group_id == g.id and fifth_team_name not in (m.home_team, m.away_team)]
                p_pts, p_gf, p_ga, p_won = 0, 0, 0, 0
                for m in g_matches_ex_5th:
                    if m.is_finished and m.home_goals is not None and m.away_goals is not None:
                        ht, at = m.home_team.strip(), m.away_team.strip()
                        if target_team_name in (ht, at):
                            hg, ag = (m.home_goals, m.away_goals) if ht == target_team_name else (m.away_goals, m.home_goals)
                            p_gf += hg
                            p_ga += ag
                            if hg > ag:
                                p_pts += 3
                                p_won += 1
                            elif hg == ag:
                                p_pts += 1
                t_target['points'] = p_pts
                t_target['gf'] = p_gf
                t_target['ga'] = p_ga
                t_target['gd'] = p_gf - p_ga
                t_target['won'] = p_won
                t_target['played'] = len([m for m in g_matches_ex_5th if m.is_finished and m.home_goals is not None and target_team_name in (m.home_team, m.away_team)])
                
            third_place_teams.append(t_target)

        g_matches = [m for m in all_matches if m.group_id == g.id]
        g_matches_with_detail = []
        tot_g_pts = 0
        for m in g_matches:
            u_p = user_predictions.get(m.id)
            u_d = match_analytics[m.id]['user_detail'] if m.id in match_analytics else calc_pred_points_detail(u_p, m, point_system)
            tot_g_pts += u_d['total']
            g_matches_with_detail.append({
                'match': m,
                'home': m.get_home_team_info(),
                'away': m.get_away_team_info(),
                'analytics': match_analytics.get(m.id),
                'pred': u_p,
                'detail': u_d,
            })

        # Calculate User Predicted Standings for this group
        pred_standings_dict = {}
        for row in st:
            t_name = row['team'].name if hasattr(row['team'], 'name') else str(row['team'])
            pred_standings_dict[t_name] = {
                'team': row['team'], 'played': 0, 'won': 0, 'drawn': 0, 'lost': 0,
                'gf': 0, 'ga': 0, 'gd': 0, 'points': 0
            }
        
        for m in g_matches:
            u_p = user_predictions.get(m.id)
            if u_p is not None and m.home_team and m.away_team:
                ht, at = m.home_team.strip(), m.away_team.strip()
                if ht in pred_standings_dict and at in pred_standings_dict:
                    hg, ag = u_p.home_goals, u_p.away_goals
                    pred_standings_dict[ht]['played'] += 1
                    pred_standings_dict[at]['played'] += 1
                    pred_standings_dict[ht]['gf'] += hg
                    pred_standings_dict[ht]['ga'] += ag
                    pred_standings_dict[at]['gf'] += ag
                    pred_standings_dict[at]['ga'] += hg
                    pred_standings_dict[ht]['gd'] += (hg - ag)
                    pred_standings_dict[at]['gd'] += (ag - hg)
                    if hg > ag:
                        pred_standings_dict[ht]['won'] += 1
                        pred_standings_dict[ht]['points'] += 3
                        pred_standings_dict[at]['lost'] += 1
                    elif hg < ag:
                        pred_standings_dict[at]['won'] += 1
                        pred_standings_dict[at]['points'] += 3
                        pred_standings_dict[ht]['lost'] += 1
                    else:
                        pred_standings_dict[ht]['drawn'] += 1
                        pred_standings_dict[at]['drawn'] += 1
                        pred_standings_dict[ht]['points'] += 1
                        pred_standings_dict[at]['points'] += 1

        pred_rank_map = {}
        sorted_pred = list(pred_standings_dict.values())
        sorted_pred.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
        if len(sorted_pred) > target_idx:
            p_target = dict(sorted_pred[target_idx])
            p_target['group_name'] = g.name
            
            # Recalculate predicted stats excluding 5th team if qualifier & 5-team group
            if is_qualifying and len(sorted_pred) >= 5:
                pred_5th_name = sorted_pred[4]['team'].name if hasattr(sorted_pred[4]['team'], 'name') else str(sorted_pred[4]['team'])
                p_target_name = p_target['team'].name if hasattr(p_target['team'], 'name') else str(p_target['team'])
                
                p_pts, p_gf, p_ga, p_won = 0, 0, 0, 0
                p_played = 0
                for m in g_matches:
                    u_p = user_predictions.get(m.id)
                    if u_p is not None and m.home_team and m.away_team:
                        ht, at = m.home_team.strip(), m.away_team.strip()
                        if pred_5th_name not in (ht, at) and p_target_name in (ht, at):
                            hg, ag = (u_p.home_goals, u_p.away_goals) if ht == p_target_name else (u_p.away_goals, u_p.home_goals)
                            p_played += 1
                            p_gf += hg
                            p_ga += ag
                            if hg > ag:
                                p_pts += 3
                                p_won += 1
                            elif hg == ag:
                                p_pts += 1
                p_target['points'] = p_pts
                p_target['gf'] = p_gf
                p_target['ga'] = p_ga
                p_target['gd'] = p_gf - p_ga
                p_target['won'] = p_won
                p_target['played'] = p_played

            pred_third_place_teams.append(p_target)


        for r_idx, p_item in enumerate(sorted_pred, 1):
            t_key = p_item['team'].name if hasattr(p_item['team'], 'name') else str(p_item['team'])
            pred_rank_map[t_key] = {
                'pred_rank': r_idx,
                'pred_points': p_item['points'],
                'pred_gd': p_item['gd'],
                'pred_gf': p_item['gf'],
                'pred_ga': p_item['ga'],
            }

        is_g_finished = len(g_matches) > 0 and all(m.home_goals is not None and m.away_goals is not None for m in g_matches)
        p_plac_val = point_system.group_correct_placement if point_system else 2
        p_lagp_val = point_system.group_correct_points if point_system else 1
        p_gm_val = point_system.group_correct_goals_scored if point_system else 1
        p_im_val = point_system.group_correct_goals_conceded if point_system else 1
        p_gd_val = point_system.group_correct_goal_diff if point_system else 1

        enhanced_standings = []
        tot_table_pts = 0
        for rank_idx, row in enumerate(st, 1):
            t_key = row['team'].name if hasattr(row['team'], 'name') else str(row['team'])
            p_info = pred_rank_map.get(t_key, {'pred_rank': '-', 'pred_points': 0, 'pred_gd': 0, 'pred_gf': 0, 'pred_ga': 0})
            
            c_plac = is_g_finished and (rank_idx == p_info['pred_rank'])
            c_lagp = is_g_finished and (row['points'] == p_info['pred_points'])
            c_gm = is_g_finished and (row['gf'] == p_info['pred_gf'])
            c_im = is_g_finished and (row['ga'] == p_info['pred_ga'])
            c_gd = is_g_finished and (row['gd'] == p_info['pred_gd'])

            pts_plac = p_plac_val if c_plac else 0
            pts_lagp = p_lagp_val if c_lagp else 0
            pts_gm = p_gm_val if c_gm else 0
            pts_im = p_im_val if c_im else 0
            pts_gd = p_gd_val if c_gd else 0
            
            tot_row_pts = pts_plac + pts_lagp + pts_gm + pts_im + pts_gd
            tot_table_pts += tot_row_pts

            pred_at_rank = sorted_pred[rank_idx - 1] if (rank_idx - 1) < len(sorted_pred) else None

            enhanced_standings.append({
                'actual_rank': rank_idx,
                'team': row['team'],
                'played': row['played'],
                'gf': row['gf'],
                'ga': row['ga'],
                'gd': row['gd'],
                'points': row['points'],
                'pred_rank': p_info['pred_rank'],
                'pred_points': p_info['pred_points'],
                'pred_gd': p_info['pred_gd'],
                'pred_gf': p_info['pred_gf'],
                'pred_ga': p_info['pred_ga'],
                'pred_row_team': pred_at_rank['team'] if pred_at_rank else None,
                'pred_row_gf': pred_at_rank['gf'] if pred_at_rank else 0,
                'pred_row_ga': pred_at_rank['ga'] if pred_at_rank else 0,
                'pred_row_gd': pred_at_rank['gd'] if pred_at_rank else 0,
                'pred_row_points': pred_at_rank['points'] if pred_at_rank else 0,
                'is_group_finished': is_g_finished,
                'pts_plac': pts_plac,
                'pts_lagp': pts_lagp,
                'pts_gm': pts_gm,
                'pts_im': pts_im,
                'pts_gd': pts_gd,
                'tot_row_pts': tot_row_pts,
            })

        group_stage_full_data.append({
            'group': g,
            'matches': g_matches_with_detail,
            'standings': enhanced_standings,
            'total_match_pts': tot_g_pts,
            'total_table_pts': tot_table_pts,
        })

    # Pre-calculate group stage completion for knockout matchup validation
    is_all_groups_finished = len(all_groups) > 0 and all(
        g.matches.filter(home_goals__isnull=False, away_goals__isnull=False).count() == g.matches.count() and g.matches.count() > 0
        for g in all_groups
    )

    # Knockout Stage Full Data calculation for Resultat tab
    knockout_stage_full_data = []
    for ks in knockout_stages:
        ks_matches = list(ks.matches.all().order_by('match_number'))
        
        # 1. Determine actual qualifiers from this stage
        actual_stage_qualifiers = set()
        for m in ks_matches:
            if m.is_finished or (m.home_goals is not None and m.away_goals is not None):
                h_info = m.get_home_team_info()
                a_info = m.get_away_team_info()
                h_name = h_info['name'] if (h_info and h_info['name'] != '-') else None
                a_name = a_info['name'] if (a_info and a_info['name'] != '-') else None
                if m.home_goals > m.away_goals and h_name:
                    actual_stage_qualifiers.add(h_name)
                elif m.away_goals > m.home_goals and a_name:
                    actual_stage_qualifiers.add(a_name)
                elif getattr(m, 'penalty_winner', None):
                    actual_stage_qualifiers.add(m.penalty_winner)

        # 2. Stage qualification point value
        ks_name_lower = ks.name.lower()
        if '8' in ks_name_lower or 'åttondel' in ks_name_lower or '16' in ks_name_lower:
            val_stage_pts = point_system.knockout_round_of_16 if point_system else 3
        elif 'kvart' in ks_name_lower or 'quarter' in ks_name_lower or '4' in ks_name_lower:
            val_stage_pts = point_system.knockout_quarterfinal if point_system else 4
        elif 'semi' in ks_name_lower:
            val_stage_pts = point_system.knockout_semifinal if point_system else 5
        elif 'final' in ks_name_lower:
            val_stage_pts = point_system.knockout_final if point_system else 8
        else:
            val_stage_pts = 3

        ks_matches_with_detail = []
        tot_ks_pts = 0
        for m in ks_matches:
            act_home = m.get_home_team_info()
            act_away = m.get_away_team_info()
            act_home_name = act_home['name'] if (act_home and act_home['name'] != '-') else None
            act_away_name = act_away['name'] if (act_away and act_away['name'] != '-') else None

            pred_home = m.get_home_team_info(user_predictions)
            pred_away = m.get_away_team_info(user_predictions)
            pred_home_name = pred_home['name'] if (pred_home and pred_home['name'] != '-') else None
            pred_away_name = pred_away['name'] if (pred_away and pred_away['name'] != '-') else None

            # Matchup check can only be logically performed once all group stage matches are finished
            is_matchup_known = is_all_groups_finished

            if is_matchup_known:
                home_team_correct = bool(act_home_name and pred_home_name and act_home_name == pred_home_name)
                away_team_correct = bool(act_away_name and pred_away_name and act_away_name == pred_away_name)
                both_teams_correct = home_team_correct and away_team_correct
            else:
                home_team_correct = False
                away_team_correct = False
                both_teams_correct = False

            u_p = user_predictions.get(m.id)
            raw_u_d = match_analytics[m.id]['user_detail'] if m.id in match_analytics else calc_pred_points_detail(u_p, m, point_system)

            if is_matchup_known and not both_teams_correct:
                u_d = {
                    'pts_home': 0, 'pts_away': 0, 'pts_tot_goals': 0, 'pts_1x2': 0,
                    'exact_score': False, 'total': 0
                }
            else:
                u_d = raw_u_d

            # Determine predicted winner
            pred_winner_name = None
            if u_p and u_p.home_goals is not None and u_p.away_goals is not None:
                if u_p.home_goals > u_p.away_goals:
                    pred_winner_name = pred_home_name
                elif u_p.away_goals > u_p.home_goals:
                    pred_winner_name = pred_away_name
                else:
                    pred_winner_name = u_p.penalty_winner if u_p.penalty_winner else pred_home_name

            is_m_finished = m.is_finished or (m.home_goals is not None and m.away_goals is not None)
            is_correct_stage_qualifier = bool(is_m_finished and pred_winner_name and (pred_winner_name in actual_stage_qualifiers))
            pts_stage_qual = val_stage_pts if is_correct_stage_qualifier else 0

            tot_m_pts = u_d['total'] + pts_stage_qual
            tot_ks_pts += tot_m_pts

            ks_matches_with_detail.append({
                'match': m,
                'home': act_home,
                'away': act_away,
                'pred_home': pred_home,
                'pred_away': pred_away,
                'is_all_groups_finished': is_all_groups_finished,
                'is_matchup_known': is_matchup_known,
                'home_team_correct': home_team_correct,
                'away_team_correct': away_team_correct,
                'both_teams_correct': both_teams_correct,
                'analytics': match_analytics.get(m.id),
                'pred': u_p,
                'detail': u_d,
                'pred_winner_name': pred_winner_name,
                'is_correct_stage_qualifier': is_correct_stage_qualifier,
                'pts_stage_qual': pts_stage_qual,
                'total_row_pts': tot_m_pts,
                'is_m_finished': is_m_finished,
            })
        knockout_stage_full_data.append({
            'stage': ks,
            'matches': ks_matches_with_detail,
            'total_match_pts': tot_ks_pts,
        })

    third_place_teams.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
    pred_third_place_teams.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)

    num_qualifying = 4 if len(all_groups) == 6 else (8 if len(all_groups) >= 12 else 4)
    for rank_idx, t_data in enumerate(third_place_teams, 1):
        t_data['rank'] = rank_idx
        t_data['is_qualified'] = rank_idx <= num_qualifying

    for rank_idx, t_data in enumerate(pred_third_place_teams, 1):
        t_data['rank'] = rank_idx
        t_data['is_qualified'] = rank_idx <= num_qualifying

    actual_qual_names = { (t['team'].name if hasattr(t['team'], 'name') else str(t['team'])) for t in third_place_teams if t.get('is_qualified') }
    pred_qual_names = { (t['team'].name if hasattr(t['team'], 'name') else str(t['team'])) for t in pred_third_place_teams if t.get('is_qualified') }

    is_all_groups_finished = len(all_groups) > 0 and all(
        g.matches.filter(home_goals__isnull=False, away_goals__isnull=False).count() == g.matches.count() and g.matches.count() > 0
        for g in all_groups
    )

    enhanced_third_place_data = []
    max_len = max(len(third_place_teams), len(pred_third_place_teams))
    val_third_pts = point_system.knockout_qualified_third if point_system else 2

    for r_idx in range(1, max_len + 1):
        act_row = third_place_teams[r_idx - 1] if r_idx - 1 < len(third_place_teams) else None
        pred_row = pred_third_place_teams[r_idx - 1] if r_idx - 1 < len(pred_third_place_teams) else None
        
        act_name = (act_row['team'].name if hasattr(act_row['team'], 'name') else str(act_row['team'])) if act_row else None
        is_qual_match = bool(act_name and (act_name in actual_qual_names) and (act_name in pred_qual_names))
        qual_pts = val_third_pts if (is_all_groups_finished and is_qual_match) else 0

        enhanced_third_place_data.append({
            'rank': r_idx,
            'act': act_row,
            'pred': pred_row,
            'is_qual_match': is_qual_match,
            'qual_pts': qual_pts,
            'is_all_groups_finished': is_all_groups_finished,
        })

    # Calculate Host Nations Ranking (England, Republic of Ireland, Scotland, Wales)
    host_ranking_data = []
    if is_qualifying:
        host_patterns = ['england', 'ireland', 'scotland', 'wales', 'a1', 'b1', 'c1', 'd1']
        all_t_objs = list(Team.objects.filter(tournament=active_tournament))
        h_objs = [t for t in all_t_objs if any(hp in t.name.lower() for hp in host_patterns)]
        for ht in h_objs:
            grp = ht.group
            if not grp: continue
            st = grp.get_standings()
            fifth_n = st[4]['team'].name if len(st) >= 5 and hasattr(st[4]['team'], 'name') else None
            h_m_list = [m for m in all_matches if m.group_id == grp.id and ht.name in (m.home_team, m.away_team)]
            if fifth_n:
                h_m_list = [m for m in h_m_list if fifth_n not in (m.home_team, m.away_team)]
            pld, w, d, l, gf, ga, pts = 0, 0, 0, 0, 0, 0, 0
            for m in h_m_list:
                if m.is_finished and m.home_goals is not None and m.away_goals is not None:
                    is_h = (m.home_team.strip() == ht.name)
                    hg, ag = (m.home_goals, m.away_goals) if is_h else (m.away_goals, m.home_goals)
                    pld += 1; gf += hg; ga += ag
                    if hg > ag: w += 1; pts += 3
                    elif hg == ag: d += 1; pts += 1
                    else: l += 1
            host_ranking_data.append({
                'team': ht, 'group': grp, 'played': pld, 'won': w, 'drawn': d, 'lost': l,
                'gf': gf, 'ga': ga, 'gd': gf - ga, 'points': pts
            })
        host_ranking_data.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
        for r_idx, h_item in enumerate(host_ranking_data, 1):
            h_item['rank'] = r_idx
            h_item['is_reserved_slot'] = (r_idx <= 2)


    # User Rank in Leaderboard
    user_rank = None
    user_total_points = 0
    for idx, entry in enumerate(leaderboard, 1):
        if entry['player'].id == request.user.id:
            user_rank = idx
            user_total_points = entry['points']
            break

    # Overall Tournament Insights Calculation (Comparing total, individual, avg & historical data)
    all_predictions = list(MatchPrediction.objects.filter(match__tournament=active_tournament))
    total_preds_count = len(all_predictions)

    if total_preds_count > 0:
        tot_goals = sum(p.home_goals + p.away_goals for p in all_predictions)
        avg_goals_per_match = round(tot_goals / total_preds_count, 2)
        diff_vs_euro2020 = round(((avg_goals_per_match - 2.78) / 2.78) * 100, 1)
    else:
        tot_goals = 0
        avg_goals_per_match = 0.0
        diff_vs_euro2020 = 0.0

    player_goal_stats = []
    for p in players:
        p_preds_list = [pred for pred in all_predictions if pred.player_id == p.id]
        if p_preds_list:
            p_tot_g = sum(pred.home_goals + pred.away_goals for pred in p_preds_list)
            p_avg_g = round(p_tot_g / len(p_preds_list), 2)
            p_name = f"{p.first_name} {p.last_name}".strip() if p.first_name else p.username
            player_goal_stats.append({'name': p_name, 'avg_goals': p_avg_g, 'total_goals': p_tot_g})

    player_goal_stats.sort(key=lambda x: x['avg_goals'], reverse=True)
    biggest_optimist = player_goal_stats[0] if player_goal_stats else {'name': '-', 'avg_goals': 0}
    biggest_pessimist = player_goal_stats[-1] if player_goal_stats else {'name': '-', 'avg_goals': 0}

    match_avg_goals = []
    for m in all_matches:
        m_preds = [pred for pred in all_predictions if pred.match_id == m.id]
        if m_preds:
            m_tot_g = sum(pred.home_goals + pred.away_goals for pred in m_preds)
            m_avg_g = round(m_tot_g / len(m_preds), 2)
            home_n = m.get_home_team_info()['name']
            away_n = m.get_away_team_info()['name']
            match_avg_goals.append({'match_name': f"{home_n} vs. {away_n}", 'avg_goals': m_avg_g})

    match_avg_goals.sort(key=lambda x: x['avg_goals'], reverse=True)
    highest_scoring_match = match_avg_goals[0] if match_avg_goals else {'match_name': '-', 'avg_goals': 0}

    england_matches = [m for m in all_matches if 'england' in (m.home_team or '').lower() or 'england' in (m.away_team or '').lower()]
    england_draw_pct = 0
    if england_matches:
        eng_preds = [p for p in all_predictions if p.match_id in [m.id for m in england_matches]]
        if eng_preds:
            draws = [p for p in eng_preds if p.home_goals == p.away_goals]
            england_draw_pct = round((len(draws) / len(eng_preds)) * 100)

    insights_summary = {
        'tot_goals': tot_goals,
        'avg_goals': avg_goals_per_match,
        'diff_vs_euro2020': diff_vs_euro2020,
        'historical_euro2020': 2.78,
        'historical_euro2024': 2.29,
        'england_draw_pct': england_draw_pct,
        'england_exit_stage': "Straffläggning i Kvartsfinalen",
        'highest_scoring_match': highest_scoring_match,
        'biggest_optimist': biggest_optimist,
        'biggest_pessimist': biggest_pessimist,
    }

    is_saved = submission.is_saved if submission else False
    is_verified = submission.is_verified if submission else False

    user_sidebet_correct = {
        sb.id: sb.is_answer_correct(user_sidebet_answers.get(sb.id, ''))
        for sb in sidebets
    }

    context = {
        'active_tournament': active_tournament,
        'is_player': is_player,
        'is_admin': is_admin,
        'is_saved': is_saved,
        'is_verified': is_verified,
        'submission': submission,
        'all_matches': all_matches,
        'upcoming_matches': upcoming_matches,
        'finished_matches': finished_matches,
        'next_match': next_match,
        'last_finished_match': last_finished_match,
        'last_finished_user_points': last_finished_user_points,
        'user_predictions': user_predictions,
        'leaderboard': leaderboard,
        'user_rank': user_rank,
        'user_points': user_total_points,
        'point_system': point_system,
        'leaderboard_group_matches': leaderboard_group_matches,
        'leaderboard_group_standings': leaderboard_group_standings,
        'leaderboard_third_place': leaderboard_third_place,
        'leaderboard_knockout': leaderboard_knockout,
        'leaderboard_sidebets': leaderboard_sidebets,
        'match_analytics': match_analytics,
        'group_tables_data': group_tables_data,
        'group_stage_full_data': group_stage_full_data,
        'knockout_stage_full_data': knockout_stage_full_data,
        'is_qualifying': is_qualifying,
        'host_ranking_data': host_ranking_data,
        'third_place_teams': third_place_teams,
        'enhanced_third_place_data': enhanced_third_place_data,

        'tot_third_place_pts': sum(item['qual_pts'] for item in enhanced_third_place_data),

        'tot_sidebets_pts': sum(sb.points for sb in sidebets if user_sidebet_correct.get(sb.id)),
        'is_all_groups_finished': is_all_groups_finished,
        'insights_summary': insights_summary,
        # Prediction Tab Data
        'groups': groups,
        'knockout_stages': knockout_stages,
        'sidebets': sidebets,
        'tournament_teams': tournament_teams,
        'user_sidebet_answers': user_sidebet_answers,
        'user_sidebet_correct': user_sidebet_correct,
        'groups_data_json': json.dumps(groups_data),
        'group_matches_json': json.dumps(group_matches),
        'static_insights': generate_static_insights(active_tournament),
    }

    # Build active tournaments summary for multi-tournament switcher modal
    active_tournaments_summary = []
    has_multiple_tournaments = len(active_tournaments) > 1

    for t in active_tournaments:
        t_sub = TournamentSubmission.objects.filter(tournament=t, player=request.user).first()
        m_count = Match.objects.filter(tournament=t).count()
        p_count = MatchPrediction.objects.filter(match__tournament=t, player=request.user).count()

        if m_count == 0:
            status_text = "Ej aktiverad"
            status_type = "GREY"
            badge_class = "bg-secondary bg-opacity-25 text-secondary border-secondary"
        elif p_count == 0:
            status_text = f"Ej påbörjad (0/{m_count})"
            status_type = "RED"
            badge_class = "bg-danger bg-opacity-25 text-danger border-danger"
        elif p_count < m_count:
            status_text = f"Ofullständig ({p_count}/{m_count})"
            status_type = "YELLOW"
            badge_class = "bg-warning bg-opacity-25 text-warning border-warning"
        elif t_sub and t_sub.is_verified:
            status_text = "Godkänd & Verifierad"
            status_type = "GREEN"
            badge_class = "bg-success bg-opacity-25 text-success border-success"
        else:
            status_text = "Sparad & Väntar Verifiering"
            status_type = "GREEN"
            badge_class = "bg-success bg-opacity-25 text-success border-success"

        icon_url = t.icon.url if (t.icon and hasattr(t.icon, 'url')) else None


        active_tournaments_summary.append({
            'tournament': t,
            'id': t.id,
            'name': t.name,
            'icon_url': icon_url,
            'is_current': (t.id == active_tournament.id),
            'status_text': status_text,
            'status_type': status_type,
            'badge_class': badge_class,
            'players_count': t.players.count(),
        })


    context['active_tournaments_summary'] = active_tournaments_summary
    context['has_multiple_tournaments'] = has_multiple_tournaments

    # Automatically check and trigger Gazzetta Special Editions for completed round milestones
    from tournament.editorial_engine.detectors import check_and_trigger_special_editions
    check_and_trigger_special_editions(active_tournament)

    context['daily_gazettes'] = DailyGazette.objects.filter(tournament=active_tournament).order_by('-publish_date', '-created_at')
    context['active_tab'] = active_tab
    context['active_tab_name'] = active_tab_name

    return render(request, 'tournament/index.html', context)

@login_required
def hub_view(request):
    """Startsida for Prediction Engine users after login."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    full_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
    persona = find_persona_for_player(full_name)
    if persona and persona.get('nicknames'):
        user_nickname = persona['nicknames'][0]
    else:
        user_nickname = request.user.first_name or request.user.username

    # Leagues where user is admin (for Pool-Admin card shortcut links)
    user_admin_leagues = list(League.objects.filter(admin=request.user, is_active=True))

    context = {
        'profile': profile,
        'user': request.user,
        'user_nickname': user_nickname,
        'user_leagues': user_admin_leagues,
    }
    return render(request, 'tournament/hub.html', context)
