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
