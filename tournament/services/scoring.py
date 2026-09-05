def calc_pred_points_detail(pred, match, point_system=None):
    if not pred or not match or match.home_goals is None or match.away_goals is None:
        return {
            'total': 0, 'correct_1x2': False, 'pts_1x2': 0,
            'correct_home': False, 'pts_home': 0,
            'correct_away': False, 'pts_away': 0,
            'correct_tot_goals': False, 'pts_tot_goals': 0,
            'exact_score': False,
            'sign_str': '-',
            'pred_sign_str': '-',
            'diff_margin': 0,
            'pred_diff_margin': 0,
            'correct_diff_margin': False,
        }
    
    pts_1x2_val = point_system.match_correct_1x2 if point_system else 3
    pts_team_val = point_system.match_correct_goals_per_team if point_system else 3
    pts_tot_val = point_system.match_correct_total_goals if point_system else 1

    p_home, p_away = pred.home_goals, pred.away_goals
    m_home, m_away = match.home_goals, match.away_goals

    p_res = '1' if p_home > p_away else ('X' if p_home == p_away else '2')
    m_res = '1' if m_home > m_away else ('X' if m_home == m_away else '2')

    c_1x2 = (p_res == m_res)
    c_home = (p_home == m_home)
    c_away = (p_away == m_away)
    c_tot = ((p_home + p_away) == (m_home + m_away))
    exact = (c_home and c_away)

    pts_1x2 = pts_1x2_val if c_1x2 else 0
    pts_home = pts_team_val if c_home else 0
    pts_away = pts_team_val if c_away else 0
    pts_tot_goals = pts_tot_val if c_tot else 0

    total = pts_1x2 + pts_home + pts_away + pts_tot_goals

    return {
        'total': total,
        'correct_1x2': c_1x2,
        'pts_1x2': pts_1x2,
        'correct_home': c_home,
        'pts_home': pts_home,
        'correct_away': c_away,
        'pts_away': pts_away,
        'correct_tot_goals': c_tot,
        'pts_tot_goals': pts_tot_goals,
        'exact_score': exact,
        'sign_str': m_res,
        'pred_sign_str': p_res,
        'diff_margin': m_home - m_away,
        'pred_diff_margin': p_home - p_away,
        'correct_diff_margin': (m_home - m_away) == (p_home - p_away)
    }

def calc_pred_points(pred, match, point_system=None):
    if not pred or not match or match.home_goals is None or match.away_goals is None:
        return 0
    pts_1x2 = point_system.match_correct_1x2 if point_system else 3
    pts_team = point_system.match_correct_goals_per_team if point_system else 3
    pts_tot = point_system.match_correct_total_goals if point_system else 1

    total = 0
    p_home, p_away = pred.home_goals, pred.away_goals
    m_home, m_away = match.home_goals, match.away_goals

    p_res = 1 if p_home > p_away else ('X' if p_home == p_away else 2)
    m_res = 1 if m_home > m_away else ('X' if m_home == m_away else 2)
    if p_res == m_res:
        total += pts_1x2
    if p_home == m_home:
        total += pts_team
    if p_away == m_away:
        total += pts_team
    if (p_home + p_away) == (m_home + m_away):
        total += pts_tot
    return total


def get_knockout_stage_point_value(stage_name: str, point_system=None) -> int:
    """Returns the point value for correctly predicting a team qualifying through a knockout stage."""
    if not stage_name:
        return 3
    s_lower = stage_name.lower()
    if 'bronze' in s_lower or 'brons' in s_lower or '3' in s_lower or 'tredje' in s_lower:
        return point_system.knockout_bronze_match if point_system else 10
    elif '8' in s_lower or 'åttondel' in s_lower or '16' in s_lower:
        return point_system.knockout_round_of_16 if point_system else 3
    elif '32' in s_lower or 'sextondel' in s_lower:
        return getattr(point_system, 'knockout_round_of_32', 2) if point_system else 2
    elif 'kvart' in s_lower or 'quarter' in s_lower or '4' in s_lower:
        return point_system.knockout_quarterfinal if point_system else 4
    elif 'semi' in s_lower:
        return point_system.knockout_semifinal if point_system else 5
    elif 'final' in s_lower or 'guld' in s_lower:
        return point_system.knockout_final if point_system else 8
    return 3


def get_third_place_qualifying_point_value(point_system=None) -> int:
    """Returns the point value for correctly predicting a team qualifying from third-place / runner-up ranking tables."""
    if point_system and hasattr(point_system, 'qualifying_table_team_qualified') and point_system.qualifying_table_team_qualified > 0:
        return point_system.qualifying_table_team_qualified
    return point_system.knockout_qualified_third if point_system else 2


def evaluate_knockout_prediction_match(
    match,
    pred,
    user_predictions_dict,
    actual_stage_qualifiers,
    val_stage_pts,
    is_all_groups_finished,
    tournament_team_names,
    point_system=None
):
    """
    Evaluates a knockout match prediction for a player:
    1. Determines whether the matchup is defined and whether both teams predicted match the actual teams.
    2. Computes the match score prediction points (zeroed if wrong teams played in the matchup).
    3. Evaluates stage advancement bonus points if the predicted winner is among the actual stage qualifiers.
    Returns a dict with breakdown and total points.
    """
    act_home = match.get_home_team_info()
    act_away = match.get_away_team_info()
    act_home_name = act_home['name'] if (act_home and act_home['name'] != '-') else None
    act_away_name = act_away['name'] if (act_away and act_away['name'] != '-') else None

    pred_home = match.get_home_team_info(user_predictions_dict)
    pred_away = match.get_away_team_info(user_predictions_dict)
    pred_home_name = pred_home['name'] if (pred_home and pred_home['name'] != '-') else None
    pred_away_name = pred_away['name'] if (pred_away and pred_away['name'] != '-') else None

    # Matchup check can only be performed once all group matches are done AND both actual teams are determined
    is_actual_home_defined = bool(act_home_name and act_home_name in tournament_team_names)
    is_actual_away_defined = bool(act_away_name and act_away_name in tournament_team_names)
    is_matchup_defined = bool(is_all_groups_finished and is_actual_home_defined and is_actual_away_defined)

    if is_matchup_defined:
        home_team_correct = bool(act_home_name and pred_home_name and act_home_name == pred_home_name)
        away_team_correct = bool(act_away_name and pred_away_name and act_away_name == pred_away_name)
        both_teams_correct = home_team_correct and away_team_correct
    else:
        home_team_correct = False
        away_team_correct = False
        both_teams_correct = False

    raw_detail = calc_pred_points_detail(pred, match, point_system)
    if is_matchup_defined and not both_teams_correct:
        detail = {
            'total': 0, 'correct_1x2': False, 'pts_1x2': 0,
            'correct_home': False, 'pts_home': 0,
            'correct_away': False, 'pts_away': 0,
            'correct_tot_goals': False, 'pts_tot_goals': 0,
            'exact_score': False, 'sign_str': raw_detail.get('sign_str', '-'),
            'pred_sign_str': raw_detail.get('pred_sign_str', '-'),
            'diff_margin': raw_detail.get('diff_margin', 0),
            'pred_diff_margin': raw_detail.get('pred_diff_margin', 0),
            'correct_diff_margin': False,
        }
        score_pts = 0
    else:
        detail = raw_detail
        score_pts = raw_detail['total']

    # Determine predicted winner
    pred_winner_name = None
    if pred and pred.home_goals is not None and pred.away_goals is not None:
        if pred.home_goals > pred.away_goals:
            pred_winner_name = pred_home_name
        elif pred.away_goals > pred.home_goals:
            pred_winner_name = pred_away_name
        else:
            pred_winner_name = pred.penalty_winner if getattr(pred, 'penalty_winner', None) else pred_home_name

    is_m_finished = match.is_finished or (match.home_goals is not None and match.away_goals is not None)
    is_correct_stage_qualifier = bool(
        is_m_finished and pred_winner_name and actual_stage_qualifiers and (pred_winner_name in actual_stage_qualifiers)
    )
    pts_stage_qual = val_stage_pts if is_correct_stage_qualifier else 0

    return {
        'score_pts': score_pts,
        'pts_stage_qual': pts_stage_qual,
        'total_m_pts': score_pts + pts_stage_qual,
        'detail': detail,
        'pred_home_name': pred_home_name,
        'pred_away_name': pred_away_name,
        'act_home_name': act_home_name,
        'act_away_name': act_away_name,
        'is_matchup_defined': is_matchup_defined,
        'both_teams_correct': both_teams_correct,
        'home_team_correct': home_team_correct,
        'away_team_correct': away_team_correct,
        'pred_winner_name': pred_winner_name,
        'is_correct_stage_qualifier': is_correct_stage_qualifier,
        'is_m_finished': is_m_finished,
    }

