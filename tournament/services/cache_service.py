"""
High-Performance Caching & Batch Pre-fetching Service for Prediction Engine.
Provides sub-50ms data retrieval for Leaderboards, Standings, Match Analytics, and Insights.
"""

from django.core.cache import cache
from django.utils import timezone
from tournament.services.scoring import (
    calc_pred_points,
    calc_pred_points_detail,
    get_knockout_stage_point_value,
    get_third_place_qualifying_point_value,
    evaluate_knockout_prediction_match,
)
from tournament.services.analytics import generate_ai_match_analysis
from tournament.editorial_engine.compiler import load_player_personas, find_persona_for_player
from tournament.editorial_engine.static_generators import generate_static_insights
from tournament.editorial_engine.detectors import check_and_trigger_special_editions


CACHE_TTL_DEFAULT = 300  # 5 minutes fallback TTL


def get_tournament_cache_version(tournament_id):
    """Returns the current cache version key for this tournament."""
    v_key = f"t_version_{tournament_id}"
    version = cache.get(v_key)
    if version is None:
        version = int(timezone.now().timestamp())
        cache.set(v_key, version, timeout=86400 * 30)
    return version


def invalidate_tournament_cache(tournament_id):
    """
    Instantly invalidates all cached data for a tournament by bumping its version token.
    Fast, atomic, and thread-safe.
    """
    v_key = f"t_version_{tournament_id}"
    new_version = int(timezone.now().timestamp())
    cache.set(v_key, new_version, timeout=86400 * 30)
    return new_version


def get_or_set_leaderboards_and_analytics(tournament, point_system, players, all_groups, all_matches, all_submissions_dict, all_predictions_by_player, all_predictions_by_match, sidebet_answers_by_player):
    """
    Computes or retrieves cached Leaderboards (all categories) and Match Analytics in a single optimized pass.
    """
    version = get_tournament_cache_version(tournament.id)
    cache_key = f"t_data_bundle_{tournament.id}_{version}"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data

    leaderboard = []
    leaderboard_group_matches = []
    leaderboard_group_standings = []
    leaderboard_third_place = []
    leaderboard_knockout = []
    leaderboard_sidebets = []

    # Precompute base actual group standings once for all groups
    base_group_standings = {}
    for g in all_groups:
        base_group_standings[g.id] = {
            'matches': list(g.matches.all()),
            'standings': g.get_standings()
        }

    group_matches_list = [m for m in all_matches if m.group_id]
    is_all_groups_finished = len(group_matches_list) > 0 and all(
        m.home_goals is not None and m.away_goals is not None for m in group_matches_list
    )
    tournament_teams = list(tournament.teams.all())
    tournament_team_names = {t.name for t in tournament_teams}

    # Precompute knockout stages, actual stage qualifiers, and stage point values
    knockout_stages = list(tournament.knockout_stages.all().order_by('order', 'id'))
    actual_stage_qualifiers_by_stage = {}
    stage_point_values = {}
    for ks in knockout_stages:
        ks_matches = [m for m in all_matches if m.stage_id == ks.id]
        actual_qualifiers = set()
        for m in ks_matches:
            if m.is_finished or (m.home_goals is not None and m.away_goals is not None):
                h_info = m.get_home_team_info()
                a_info = m.get_away_team_info()
                h_name = h_info['name'] if (h_info and h_info['name'] != '-') else None
                a_name = a_info['name'] if (a_info and a_info['name'] != '-') else None
                if m.home_goals > m.away_goals and h_name:
                    actual_qualifiers.add(h_name)
                elif m.away_goals > m.home_goals and a_name:
                    actual_qualifiers.add(a_name)
                elif getattr(m, 'penalty_winner', None):
                    actual_qualifiers.add(m.penalty_winner)
        actual_stage_qualifiers_by_stage[ks.id] = actual_qualifiers
        stage_point_values[ks.id] = get_knockout_stage_point_value(ks.name, point_system)

    # Precompute third-place / qualifying actual teams
    is_qualifying = 'kval' in (tournament.name or '').lower() or 'qualif' in (tournament.name or '').lower()
    target_idx = 1 if is_qualifying else 2

    actual_third_place_teams = []
    for g in all_groups:
        g_data = base_group_standings[g.id]
        st = g_data['standings']
        if len(st) > target_idx:
            t_target = dict(st[target_idx])
            t_target['group_name'] = g.name
            actual_third_place_teams.append(t_target)

    actual_third_place_teams.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
    num_qualifying = 4 if len(all_groups) == 6 else (8 if len(all_groups) >= 12 else 4)
    actual_qual_names = {
        (t['team'].name if hasattr(t['team'], 'name') else str(t['team']))
        for rank_idx, t in enumerate(actual_third_place_teams, 1)
        if rank_idx <= num_qualifying
    }
    val_third_pts = get_third_place_qualifying_point_value(point_system)

    p_plac_val = point_system.group_correct_placement if point_system else 2
    p_lagp_val = point_system.group_correct_points if point_system else 1
    p_gd_val = point_system.group_correct_goal_diff if point_system else 1

    # 1. Fast Batch Leaderboards Calculation
    for p in players:
        p_sub = all_submissions_dict.get(p.id)
        p_preds = all_predictions_by_player.get(p.id, [])
        p_preds_by_match_id = {pred.match_id: pred for pred in p_preds}

        gm_pts = 0
        gm_fullpott = 0
        gm_ratt_mal = 0
        gm_ratt_tecken = 0

        ko_pts = 0
        ko_initial_pts = 0
        ko_actual_pts = 0
        ko_fullpott = 0
        ko_ratt_mal = 0
        ko_ratt_tecken = 0

        p_preds_dict = {}

        for pred in p_preds:
            m = pred.match
            if m.group_id:
                p_preds_dict[m.id] = pred
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

                    gm_pts += pts
                    if is_exact: gm_fullpott += 1
                    gm_ratt_mal += goals_matched
                    if is_correct_1x2: gm_ratt_tecken += 1
            else:
                # Knockout match evaluation (includes advancement bonus and matchup team validity check)
                ks_id = m.stage_id
                actual_stage_qual = actual_stage_qualifiers_by_stage.get(ks_id, set())
                val_stage_pts = stage_point_values.get(ks_id, 3)

                ko_eval = evaluate_knockout_prediction_match(
                    match=m,
                    pred=pred,
                    user_predictions_dict=p_preds_by_match_id,
                    actual_stage_qualifiers=actual_stage_qual,
                    val_stage_pts=val_stage_pts,
                    is_all_groups_finished=is_all_groups_finished,
                    tournament_team_names=tournament_team_names,
                    point_system=point_system
                )

                score_pts = ko_eval['score_pts']
                pts_stage_qual = ko_eval['pts_stage_qual']
                tot_m_ko_pts = score_pts + pts_stage_qual

                if pred.prediction_phase == 'ACTUAL_KNOCKOUT':
                    ko_actual_pts += tot_m_ko_pts
                else:
                    ko_initial_pts += tot_m_ko_pts
                ko_pts += tot_m_ko_pts

                if ko_eval['is_m_finished'] and ko_eval['both_teams_correct']:
                    if ko_eval['detail'].get('exact_score'):
                        ko_fullpott += 1
                    c_h = ko_eval['detail'].get('correct_home', False)
                    c_a = ko_eval['detail'].get('correct_away', False)
                    ko_ratt_mal += (1 if c_h else 0) + (1 if c_a else 0)
                    if ko_eval['detail'].get('correct_1x2', False):
                        ko_ratt_tecken += 1

        gs_pts = 0
        gs_ratt_placering = 0
        gs_ratt_lagpoang = 0
        gs_ratt_malskillnad = 0

        pred_third_place_teams = []

        for g in all_groups:
            g_data = base_group_standings[g.id]
            g_m_list = g_data['matches']
            is_g_finished = len(g_m_list) > 0 and all(m.home_goals is not None and m.away_goals is not None for m in g_m_list)
            
            st = g_data['standings']
            pred_dict = {
                (row['team'].name if hasattr(row['team'], 'name') else str(row['team'])): {
                    'team': row['team'], 'played': 0, 'won': 0, 'drawn': 0, 'lost': 0,
                    'gf': 0, 'ga': 0, 'gd': 0, 'points': 0
                } for row in st
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

            sorted_p_list = sorted(pred_dict.values(), key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
            
            # Third-place tracking
            if len(sorted_p_list) > target_idx:
                p_target = dict(sorted_p_list[target_idx])
                p_target['group_name'] = g.name
                pred_third_place_teams.append(p_target)

            if is_g_finished:
                p_rank_map = {}
                for r_idx, p_item in enumerate(sorted_p_list, 1):
                    t_k = p_item['team'].name if hasattr(p_item['team'], 'name') else str(p_item['team'])
                    p_rank_map[t_k] = {'pred_rank': r_idx, 'pred_points': p_item['points'], 'pred_gd': p_item['gd']}

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

        # Stage 3: Third place / qualifying ranking points
        pred_third_place_teams.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
        tp_pts = 0
        tp_ratt_lag = 0
        if is_all_groups_finished:
            for rank_idx, p_item in enumerate(pred_third_place_teams, 1):
                if rank_idx <= num_qualifying:
                    p_t_name = p_item['team'].name if hasattr(p_item['team'], 'name') else str(p_item['team'])
                    if p_t_name in actual_qual_names:
                        tp_pts += val_third_pts
                        tp_ratt_lag += 1

        sb_pts = 0
        sb_ratt_antal = 0
        p_sidebet_answers = sidebet_answers_by_player.get(p.id, [])
        for ans in p_sidebet_answers:
            if ans.sidebet.is_answer_correct(ans.answer):
                sb_pts += ans.sidebet.points
                sb_ratt_antal += 1

        tot_pts = gm_pts + gs_pts + tp_pts + ko_pts + sb_pts

        p_name = f"{p.first_name} {p.last_name}".strip() if p.first_name else p.email
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
            'initial_points': ko_initial_pts,
            'actual_points': ko_actual_pts,
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

    # 2. Fast Batch Match Analytics
    personas_list = load_player_personas()
    match_analytics_base = {}

    for m in all_matches:
        all_preds = all_predictions_by_match.get(m.id, [])
        total_preds = len(all_preds)

        is_reported = m.is_finished or (m.home_goals is not None and m.away_goals is not None)
        actual_score = f"{m.home_goals} - {m.away_goals}" if is_reported else "- : -"

        home_preds = []
        draw_preds = []
        away_preds = []

        for p_pred in all_preds:
            p_user = p_pred.player
            p_name = f"{p_user.first_name} {p_user.last_name}".strip() if p_user.first_name else p_user.email
            persona = find_persona_for_player(p_name, personas_list)
            u_nick = persona.get('nicknames', [p_name])[0] if persona else (p_user.first_name or p_user.email)
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

        match_analytics_base[m.id] = {
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
            'all_preds_list': home_preds + draw_preds + away_preds,
        }

    data_bundle = {
        'leaderboard': leaderboard,
        'leaderboard_group_matches': leaderboard_group_matches,
        'leaderboard_group_standings': leaderboard_group_standings,
        'leaderboard_third_place': leaderboard_third_place,
        'leaderboard_knockout': leaderboard_knockout,
        'leaderboard_sidebets': leaderboard_sidebets,
        'match_analytics_base': match_analytics_base,
        'base_group_standings': base_group_standings,
    }

    cache.set(cache_key, data_bundle, timeout=CACHE_TTL_DEFAULT)
    return data_bundle


def get_or_set_static_insights_cached(tournament):
    """Caches generated static insights."""
    version = get_tournament_cache_version(tournament.id)
    cache_key = f"t_static_insights_{tournament.id}_{version}"
    cached = cache.get(cache_key)
    if cached is None:
        cached = generate_static_insights(tournament)
        cache.set(cache_key, cached, timeout=CACHE_TTL_DEFAULT)
    return cached
