"""
static_generators.py
--------------------
Generator for Section 1 ("Gängets Tipsanalys & Almanackan").
Analyzes placed predictions BEFORE match results, comparing player macro bracket choices,
Knockout Stage advancements, England / Heavyweight barometers, Dream Finals,
Split decisions, Goal extremes, Decisive vs Draw philosophies, and Sidebets.

Produces clean dynamic structured topic boxes for any tournament with bold popping player names.
"""
from collections import Counter, defaultdict
import itertools
import math
from django.db.models import Count
from tournament.models import (
    Tournament, Match, MatchPrediction, Sidebet, SidebetAnswer, StaticInsight, TournamentSubmission
)
from tournament.editorial_engine.compiler import load_player_personas, find_persona_for_player


COUNTRY_FLAG_MAP = {
    'austria': '🇦🇹', 'österrike': '🇦🇹',
    'hungary': '🇭🇺', 'ungern': '🇭🇺',
    'croatia': '🇭🇷', 'kroatien': '🇭🇷',
    'sweden': '🇸🇪', 'sverige': '🇸🇪',
    'denmark': '🇩🇰', 'danmark': '🇩🇰',
    'germany': '🇩🇪', 'tyskland': '🇩🇪',
    'france': '🇫🇷', 'frankrike': '🇫🇷',
    'norway': '🇳🇴', 'norge': '🇳🇴',
    'spain': '🇪🇸', 'spanien': '🇪🇸',
    'montenegro': '🇲🇪',
    'slovenia': '🇸🇮', 'slovenien': '🇸🇮',
    'north macedonia': '🇲🇰', 'nordmakedonien': '🇲🇰',
    'turkey': '🇹🇷', 'turkiet': '🇹🇷',
    'greece': '🇬🇷', 'grekland': '🇬🇷',
    'serbia': '🇷🇸', 'serbien': '🇷🇸',
    'iceland': '🇮🇸', 'island': '🇮🇸',
    'czech republic': '🇨🇿', 'tjeckien': '🇨🇿',
    'poland': '🇵🇱', 'polen': '🇵🇱',
    'switzerland': '🇨🇭', 'schweiz': '🇨🇭',
    'romania': '🇷🇴', 'rumänien': '🇷🇴',
    'netherlands': '🇳🇱', 'nederländerna': '🇳🇱',
    'ukraine': '🇺🇦',
    'slovakia': '🇸🇰', 'slovakien': '🇸🇰',
    'faroe islands': '🇫🇴', 'färöarna': '🇫🇴',
    'england': '🏴󠁧󠁢󠁥󠁮󠁧󠁿',
    'oman': '🇴🇲',
    'jordan': '🇯🇴', 'jordanien': '🇯🇴',
    'saudi arabia': '🇸🇦', 'saudiarabien': '🇸🇦',
    'kuwait': '🇰🇼',
    'japan': '🇯🇵',
    'bahrain': '🇧🇭',
    'north korea': '🇰🇵', 'nordkorea': '🇰🇵',
    'south korea': '🇰🇷', 'sydkorea': '🇰🇷',
    'palestine': '🇵🇸', 'palestina': '🇵🇸',
    'syria': '🇸🇾', 'syrien': '🇸🇾',
    'united arab emirates': '🇦🇪', 'uae': '🇦🇪',
    'yemen': '🇾🇪',
    'australia': '🇦🇺', 'australien': '🇦🇺',
    'thailand': '🇹🇭',
    'indonesia': '🇮🇩', 'indonesien': '🇮🇩',
    'china': '🇨🇳', 'kina': '🇨🇳',
    'brazil': '🇧🇷', 'brasilien': '🇧🇷',
    'argentina': '🇦🇷',
}


def get_country_flag(team_name: str) -> str:
    """Returns flag emoji for a country name, or empty string if not found."""
    if not team_name:
        return ''
    return COUNTRY_FLAG_MAP.get(team_name.lower().strip(), '')


def is_toarps_herrklubb_tournament(tournament: Tournament) -> bool:
    """Checks if the tournament belongs to or is named Toarps Herrklubb."""
    if not tournament:
        return False
    t_name = getattr(tournament, 'name', '').lower()
    if "toarp" in t_name:
        return True
    if hasattr(tournament, 'leagues') and tournament.leagues.filter(name__icontains='toarp').exists():
        return True
    return False


def get_player_nick_or_name(player, personas_list=None, is_toarp=False) -> str:
    """
    Returns persona nickname ONLY if the pool/tournament is Toarps Herrklubb.
    For all other generic tournaments and pools, strictly returns the player's real name/first name.
    """
    if not player:
        return "Tipparen"
    p_name = player.get_full_name() if hasattr(player, 'get_full_name') and player.get_full_name() else (
        f"{player.first_name} {player.last_name}".strip() if getattr(player, 'first_name', '') else getattr(player, 'email', 'Spelare')
    )
    first_or_full = p_name.split()[0] if ' ' in p_name else p_name
    if is_toarp and personas_list:
        p_match = find_persona_for_player(p_name, personas_list)
        if p_match:
            nicks = p_match.get('nicknames', [])
            if nicks and nicks[0]:
                return nicks[0]
    return first_or_full


def generate_static_insights(tournament: Tournament):
    """
    Computes pre-tournament & macro bracket insights across all participants with locked predictions.
    Guarantees clean 9 structured cards:
      Row 1: 1. 🏆 CHAMPION_CONSENSUS   | 2. 🏴󠁧󠁢󠁥󠁮󠁧󠁿 ENGLAND_BAROMETER | 3. ⚔️ DREAM_FINAL
      Row 2: 4. ⚡ DELUSION_INDEX       | 5. 🐺 LONE_WOLF          | 6. ⚽ GOAL_DELUSION
      Row 3: 7. 🎯 SIGN_DECISIVE        | 8. 👟 GOLDEN_BOOT        | 9. 🔮 BANKER_CONSENSUS
    """
    insights_created = []
    
    # Nicknames & personas are strictly restricted to Toarps Herrklubb
    is_toarp = is_toarps_herrklubb_tournament(tournament)
    personas_list = load_player_personas() if is_toarp else []

    # Clear previously generated dynamic static insights for this tournament
    StaticInsight.objects.filter(tournament=tournament).delete()

    # -------------------------------------------------------------------------
    # 0. Filter Participants by Locked Status
    # -------------------------------------------------------------------------
    is_time_locked = getattr(tournament, 'is_locked_by_time', False)
    all_players_qs = list(tournament.players.filter(is_staff=False, is_superuser=False))
    
    if not all_players_qs:
        from django.contrib.auth.models import User
        pred_player_ids = MatchPrediction.objects.filter(
            match__tournament=tournament
        ).values_list('player_id', flat=True).distinct()
        all_players_qs = list(User.objects.filter(id__in=pred_player_ids))

    if not all_players_qs:
        return []

    # Check verified submissions
    verified_player_ids = set(
        TournamentSubmission.objects.filter(
            tournament=tournament, is_verified=True
        ).values_list('player_id', flat=True)
    )

    if is_time_locked:
        # Once tournament starts, ALL participant predictions are permanently locked & verified
        locked_players = all_players_qs
    elif verified_player_ids:
        # Pre-tournament: calculate metrics ONLY from verified/locked coupons
        locked_players = [p for p in all_players_qs if p.id in verified_player_ids]
    else:
        # Fallback if no verified yet (e.g. dev/staging preview): use saved or all
        saved_player_ids = set(
            TournamentSubmission.objects.filter(
                tournament=tournament, is_saved=True
            ).values_list('player_id', flat=True)
        )
        locked_players = [p for p in all_players_qs if p.id in saved_player_ids] if saved_player_ids else all_players_qs

    if not locked_players:
        return []

    locked_player_ids = {p.id for p in locked_players}
    all_tournament_matches = list(Match.objects.filter(tournament=tournament).order_by('match_number', 'date_time'))
    
    # Static insights are STRICTLY and EXCLUSIVELY calculated from the pre-tournament INITIAL_BRACKET coupon.
    # Mid-tournament ACTUAL_KNOCKOUT re-predictions are intentionally excluded so the pre-tournament prophecy remains constant.
    all_preds_qs = list(
        MatchPrediction.objects.filter(
            match__tournament=tournament,
            player_id__in=locked_player_ids,
            prediction_phase='INITIAL_BRACKET'
        ).select_related('match', 'player')
    )

    # Pre-calculate player goal & sign metrics
    goal_stats = []
    tot_all_goals = 0
    tot_all_matches = 0

    for p in locked_players:
        p_name = p.get_full_name() if p.get_full_name() else (
            f"{p.first_name} {p.last_name}".strip() if p.first_name else p.email
        )
        p_nick = get_player_nick_or_name(p, personas_list, is_toarp=is_toarp)
        p_preds = [pred for pred in all_preds_qs if pred.player_id == p.id]
        total_matches = len(p_preds)
        if total_matches > 0:
            total_goals = sum(pred.home_goals + pred.away_goals for pred in p_preds)
            avg_goals = total_goals / total_matches
            tot_all_goals += total_goals
            tot_all_matches += total_matches

            draws = sum(1 for pred in p_preds if pred.home_goals == pred.away_goals)
            decisive = sum(1 for pred in p_preds if pred.home_goals != pred.away_goals)
            home_wins = sum(1 for pred in p_preds if pred.home_goals > pred.away_goals)
            away_wins = sum(1 for pred in p_preds if pred.home_goals < pred.away_goals)

            goal_stats.append({
                'player': p,
                'player_name': p_name,
                'p_nick': p_nick,
                'total_goals': total_goals,
                'avg_goals': avg_goals,
                'matches': total_matches,
                'draws': draws,
                'decisive': decisive,
                'home_wins': home_wins,
                'away_wins': away_wins,
                'draw_pct': (draws / total_matches) * 100.0,
                'decisive_pct': (decisive / total_matches) * 100.0,
            })

    # =========================================================================
    # CARD 1: 🏆 CHAMPION_CONSENSUS (Mästardrömmar & Guldfavoriter)
    # =========================================================================
    sidebets = list(Sidebet.objects.filter(tournament=tournament))
    champ_sb = next((sb for sb in sidebets if any(k in sb.question.lower() for k in ["vinner", "mästare", "champion", "guld", "segrare"])), None)
    final_match = next((m for m in all_tournament_matches if m.stage and any(k in str(m.stage).lower() for k in ["final", "101", "85", "82", "93"])), all_tournament_matches[-1] if all_tournament_matches else None)

    player_champ_map = {}
    if champ_sb:
        answers = list(SidebetAnswer.objects.filter(sidebet=champ_sb, player_id__in=locked_player_ids))
        for a in answers:
            if a.answer.strip():
                player_champ_map[a.player_id] = a.answer.strip()
                
    if not player_champ_map and final_match:
        for p in locked_players:
            p_preds_dict = {pred.match_id: pred for pred in all_preds_qs if pred.player_id == p.id}
            h_info = final_match.get_home_team_info(user_predictions=p_preds_dict)
            a_info = final_match.get_away_team_info(user_predictions=p_preds_dict)
            h_name = h_info.get('name', '')
            a_name = a_info.get('name', '')
            final_p = p_preds_dict.get(final_match.id)
            if final_p:
                if final_p.home_goals > final_p.away_goals or (final_p.penalty_winner and 'home' in str(final_p.penalty_winner).lower()):
                    champ_n = h_name
                elif final_p.away_goals > final_p.home_goals or (final_p.penalty_winner and 'away' in str(final_p.penalty_winner).lower()):
                    champ_n = a_name
                else:
                    champ_n = h_name
                if champ_n and 'winner match' not in champ_n.lower() and 'lag #' not in champ_n.lower():
                    player_champ_map[p.id] = champ_n

    champ_name = "Favorit saknas"
    top_pct_str = "27% Konsensus"
    frame_main = "👥:::Inga mästartips registrerade ännu"

    if player_champ_map:
        counts = Counter(player_champ_map.values())
        if counts:
            top_ans, top_cnt = counts.most_common(1)[0]
            champ_name = top_ans
            pct_val = int((top_cnt / len(player_champ_map)) * 100)
            top_pct_str = f"{pct_val}% Konsensus"
            
            flag_top = get_country_flag(top_ans)
            flag_prefix = f"{flag_top} " if flag_top else ""
            
            backers = [
                get_player_nick_or_name(p, personas_list, is_toarp=is_toarp)
                for p in locked_players if player_champ_map.get(p.id) == top_ans
            ]
            backers_bullets = "<br>".join([f"• <span class=\"player-name-pop\">{b}</span>" for b in backers])
            frame_main = f"👥:::{flag_prefix}{top_ans} ({top_cnt} av {len(player_champ_map)} deltagare)<br>{backers_bullets}"

    flag_top = get_country_flag(champ_name)
    flag_str = f"{flag_top} " if flag_top else ""
    data_point_champ = f"{top_pct_str} || {flag_str}{champ_name}"
    champ_roast = f"{frame_main} || Baserat på deltagarnas låsta guld- och mästartips."

    insight_1 = StaticInsight.objects.create(
        tournament=tournament,
        category='CHAMPION_CONSENSUS',
        player_name=champ_name,
        data_point=data_point_champ,
        llm_roast=champ_roast,
        is_published=True
    )
    insights_created.append(insight_1)

    # =========================================================================
    # CARD 2: 🏴󠁧󠁢󠁥󠁮󠁧󠁿 ENGLAND_BAROMETER ("It's Never Coming Home" / England Banter)
    # =========================================================================
    teams_list = list(tournament.teams.values_list('name', flat=True))
    england_name = next((tm for tm in teams_list if 'england' in tm.lower()), None)
    
    if england_name:
        target_team = england_name
        
        team_matches = [
            m for m in all_tournament_matches
            if m.get_home_team_info()['name'] == target_team or m.get_away_team_info()['name'] == target_team
        ]
        
        optimists = []
        for p in locked_players:
            p_nick = get_player_nick_or_name(p, personas_list, is_toarp=is_toarp)
            p_team_preds = [pred for pred in all_preds_qs if pred.player_id == p.id and pred.match in team_matches]
            wins = sum(
                1 for pred in p_team_preds
                if (pred.match.get_home_team_info()['name'] == target_team and pred.home_goals > pred.away_goals)
                or (pred.match.get_away_team_info()['name'] == target_team and pred.away_goals > pred.home_goals)
            )
            if wins >= 2:
                optimists.append((p_nick, wins))

        optimists.sort(key=lambda x: x[1], reverse=True)
        data_point_baro = f"Respass i Slutspelet || \"It's Never Coming Home\""
        if optimists:
            opt_bullets = "<br>".join([f"• <span class=\"player-name-pop\">{name}</span> spår avancemang ({w} segrar)" for name, w in optimists])
            frame_main = f"🇬🇧:::England-optimisterna:<br>{opt_bullets}"
        else:
            frame_main = "🇬🇧:::England-optimisterna:<br>• Noll deltagare har vågat chansa på England."
        baro_footer = "Den heliga Toarp-sanningen om England sätts på prov."
    else:
        data_point_baro = "Kvalfiasko || \"It's Never Coming Home\""
        frame_main = "🏴󠁧󠁢󠁥󠁮󠁧󠁿:::England Lyser Med Sin Frånvaro:<br>• England lyckades inte ens kvalificera sig till mästerskapet.<br>• \"It's Never Coming Home\" – noll risk för smutsiga England-poäng i tipset."
        baro_footer = "Det bästa mästerskapet är ett mästerskap helt utan England."

    insight_2 = StaticInsight.objects.create(
        tournament=tournament,
        category='ENGLAND_BAROMETER',
        player_name="England-Barometern",
        data_point=data_point_baro,
        llm_roast=f"{frame_main} || {baro_footer}",
        is_published=True
    )
    insights_created.append(insight_2)

    # =========================================================================
    # CARD 3: ⚔️ DREAM_FINAL (Drömfinalen: Vilka Gör Upp om Guldet?)
    # =========================================================================
    user_final_pair_map = {}
    if final_match:
        for p in locked_players:
            p_preds_dict = {pred.match_id: pred for pred in all_preds_qs if pred.player_id == p.id}
            h_info = final_match.get_home_team_info(user_predictions=p_preds_dict)
            a_info = final_match.get_away_team_info(user_predictions=p_preds_dict)
            h_name = h_info.get('name', '')
            a_name = a_info.get('name', '')
            if h_name and a_name and 'winner match' not in h_name.lower() and 'winner match' not in a_name.lower():
                user_final_pair_map[p.id] = f"{h_name} vs {a_name}"

    final_sb = next((sb for sb in sidebets if any(k in sb.question.lower() for k in ["finalpar", "finalister", "möts i final"])), None)
    if final_sb:
        f_ans = list(SidebetAnswer.objects.filter(sidebet=final_sb, player_id__in=locked_player_ids))
        for a in f_ans:
            if a.answer.strip():
                user_final_pair_map[a.player_id] = a.answer.strip()

    if user_final_pair_map:
        counts = Counter(user_final_pair_map.values())
        top_pair, top_pair_cnt = counts.most_common(1)[0]
        
        if ' vs ' in top_pair:
            t1, t2 = top_pair.split(' vs ', 1)
        else:
            t1, t2 = top_pair, ''
        f1 = get_country_flag(t1)
        f2 = get_country_flag(t2)
        f1_str = f"{f1} " if f1 else ""
        f2_str = f"{f2} " if f2 else ""
        pair_formatted = f"{f1_str}{t1} vs {f2_str}{t2}" if t2 else f"{f1_str}{t1}"
        
        data_point_final = f"Mest Tippade Drömfinalen || {pair_formatted}"
        
        pair_backers = [
            get_player_nick_or_name(p, personas_list, is_toarp=is_toarp)
            for p in locked_players if user_final_pair_map.get(p.id) == top_pair
        ]
        backers_bullets = "<br>".join([f"• <span class=\"player-name-pop\">{b}</span>" for b in pair_backers])
        frame_main = f"👑:::{pair_formatted} ({top_pair_cnt} st)<br>{backers_bullets}"
    else:
        top_pair = f"{teams_list[0]} vs {teams_list[1]}" if len(teams_list) >= 2 else "Finaldramatik"
        data_point_final = f"Mästerskapets Finalpar || {top_pair}"
        frame_main = f"👑:::Förväntad final: **{top_pair}**<br>• Väntar på slutförda tipsrader"

    insight_3 = StaticInsight.objects.create(
        tournament=tournament,
        category='DREAM_FINAL',
        player_name=top_pair,
        data_point=data_point_final,
        llm_roast=f"{frame_main} || Vilka två nationer möts på mästerskapets absoluta topp?",
        is_published=True
    )
    insights_created.append(insight_3)

    # =========================================================================
    # CARD 4: ⚡ DELUSION_INDEX (Slutspelsträdet & Vattendelaren)
    # =========================================================================
    split_matches = []
    for m in all_tournament_matches:
        m_preds = [p for p in all_preds_qs if p.match_id == m.id]
        if len(m_preds) >= 2:
            h_cnt = sum(1 for p in m_preds if p.home_goals > p.away_goals)
            d_cnt = sum(1 for p in m_preds if p.home_goals == p.away_goals)
            a_cnt = sum(1 for p in m_preds if p.home_goals < p.away_goals)
            
            n = len(m_preds)
            entropy = 0.0
            for cnt in (h_cnt, d_cnt, a_cnt):
                if cnt > 0:
                    prob = cnt / n
                    entropy -= prob * math.log2(prob)
            
            home_n = m.get_home_team_info()['name']
            away_n = m.get_away_team_info()['name']
            
            h_players = [get_player_nick_or_name(p.player, personas_list, is_toarp=is_toarp) for p in m_preds if p.home_goals > p.away_goals]
            d_players = [get_player_nick_or_name(p.player, personas_list, is_toarp=is_toarp) for p in m_preds if p.home_goals == p.away_goals]
            a_players = [get_player_nick_or_name(p.player, personas_list, is_toarp=is_toarp) for p in m_preds if p.home_goals < p.away_goals]

            split_matches.append({
                'match_name': f"{home_n} vs {away_n}",
                'spread_text': f"1: {h_cnt}st | X: {d_cnt}st | 2: {a_cnt}st",
                'entropy': entropy,
                'home_n': home_n,
                'away_n': away_n,
                'h_players': h_players,
                'd_players': d_players,
                'a_players': a_players,
            })

    split_matches.sort(key=lambda x: x['entropy'], reverse=True)
    top_split = split_matches[0] if split_matches else {
        'match_name': 'Jämn Match', 'spread_text': 'Jämnt fördelade tips', 'home_n': 'Lag A', 'away_n': 'Lag B',
        'h_players': [], 'd_players': [], 'a_players': []
    }

    hf = get_country_flag(top_split['home_n'])
    af = get_country_flag(top_split['away_n'])
    hf_str = f"{hf} " if hf else ""
    af_str = f"{af} " if af else ""
    match_formatted = f"{hf_str}{top_split['home_n']} vs {af_str}{top_split['away_n']}"

    data_point_split = f"Högst Oenighet || {match_formatted}"
    
    h_spans = ", ".join([f"<span class=\"player-name-pop\">{p}</span>" for p in top_split['h_players']])
    d_spans = ", ".join([f"<span class=\"player-name-pop\">{p}</span>" for p in top_split['d_players']])
    a_spans = ", ".join([f"<span class=\"player-name-pop\">{p}</span>" for p in top_split['a_players']])

    frame_1 = f"1:::({len(top_split['h_players'])}st): {h_spans}" if h_spans else "1:::(0st): Inga hemmasegrar"
    frame_x = f"X:::({len(top_split['d_players'])}st): {d_spans}" if d_spans else "X:::(0st): Inga kryss"
    frame_2 = f"2:::({len(top_split['a_players'])}st): {a_spans}" if a_spans else "2:::(0st): Inga bortasegrar"

    insight_4 = StaticInsight.objects.create(
        tournament=tournament,
        category='DELUSION_INDEX',
        player_name=top_split['match_name'],
        data_point=data_point_split,
        llm_roast=f"{frame_1}<br><br>{frame_x}<br><br>{frame_2} || Den enskilt största poängdelaren i gängets tipsrader.",
        is_published=True
    )
    insights_created.append(insight_4)

    # =========================================================================
    # CARD 5: 🐺 LONE_WOLF (Sololigan & Knockout-Skrällar)
    # =========================================================================
    player_lone_counts = Counter()
    player_lone_examples = defaultdict(list)
    total_solo_picks = 0

    for m in all_tournament_matches:
        m_preds = [p for p in all_preds_qs if p.match_id == m.id]
        if len(m_preds) >= 3:
            h_preds = [p for p in m_preds if p.home_goals > p.away_goals]
            d_preds = [p for p in m_preds if p.home_goals == p.away_goals]
            a_preds = [p for p in m_preds if p.home_goals < p.away_goals]

            h_n = m.get_home_team_info()['name']
            away_n = m.get_away_team_info()['name']

            if len(a_preds) == 1 and len(h_preds) >= 2:
                p = a_preds[0].player
                player_lone_counts[p.id] += 1
                total_solo_picks += 1
                player_lone_examples[p.id].append(f"Skrällseger för {away_n} mot {h_n}")
            elif len(h_preds) == 1 and len(a_preds) >= 2:
                p = h_preds[0].player
                player_lone_counts[p.id] += 1
                total_solo_picks += 1
                player_lone_examples[p.id].append(f"Hemmaseger för {h_n} mot {away_n}")
            elif len(d_preds) == 1 and (len(h_preds) + len(a_preds)) >= 3:
                p = d_preds[0].player
                player_lone_counts[p.id] += 1
                total_solo_picks += 1
                player_lone_examples[p.id].append(f"Kryss i {h_n}-{away_n}")

    ranked_lone_players = []
    for p in locked_players:
        cnt = player_lone_counts[p.id]
        nick = get_player_nick_or_name(p, personas_list, is_toarp=is_toarp)
        examples = player_lone_examples[p.id]
        ranked_lone_players.append({
            'player': p,
            'nick': nick,
            'count': cnt,
            'examples': examples
        })

    ranked_lone_players.sort(key=lambda x: x['count'], reverse=True)

    if ranked_lone_players and ranked_lone_players[0]['count'] > 0:
        top_wolf = ranked_lone_players[0]
        data_point_lone = f"{top_wolf['count']} st Solodrag || <span class=\"player-name-pop\">{top_wolf['nick']}</span> Leder Sololigan"
        
        clean_examples = [ex for ex in top_wolf['examples'] if 'winner match' not in ex.lower() and 'lag #' not in ex.lower()]
        if not clean_examples:
            clean_examples = top_wolf['examples']
        top_ex_bullets = "<br>".join([f"• {ex}" for ex in clean_examples[:4]])
        frame_main = f"🐺:::Ensamvarg: <span class=\"player-name-pop\">{top_wolf['nick']}</span> ({top_wolf['count']} st solodrag)<br>{top_ex_bullets}"
    else:
        data_point_lone = "Konsensus || Samstämmiga tips"
        frame_main = "👥:::Total konsensus:<br>• Inga extrema solospel identifierade bland de låsta tipsen."

    insight_5 = StaticInsight.objects.create(
        tournament=tournament,
        category='LONE_WOLF',
        player_name=ranked_lone_players[0]['nick'] if ranked_lone_players else "Ensamvargar",
        data_point=data_point_lone,
        llm_roast=f"{frame_main} || Hävstängerna som kan avgöra hela ligatabellen om solodragen slår in.",
        is_published=True
    )
    insights_created.append(insight_5)

    # =========================================================================
    # CARD 6: ⚽ GOAL_DELUSION (Total Målprognos: Målfest eller Försvarsmur?)
    # =========================================================================
    if goal_stats:
        player_count = len(goal_stats)
        predicted_avg_tot_goals = int(tot_all_goals / player_count) if player_count > 0 else 0

        goal_stats.sort(key=lambda x: x['total_goals'], reverse=True)
        grand_optimist = goal_stats[0]
        pragmatist = goal_stats[-1]
        goal_diff = grand_optimist['total_goals'] - pragmatist['total_goals']

        data_point_goals = f"{predicted_avg_tot_goals} Mål i Snitt || {grand_optimist['total_goals']} vs {pragmatist['total_goals']} Mål (Ytterligheter)"
        frame_main = f"🔥:::Grand Optimist: <span class=\"player-name-pop\">{grand_optimist['p_nick']}</span><br>• Förutspår mästerskapets målrikaste tipsrad: {grand_optimist['total_goals']} mål ({grand_optimist['avg_goals']:.2f} mål/match)<br>• Hela {goal_diff} fler mål än flockens mest defensiva rad"
        goal_benchmark_footer = f"Målskillnad mellan flockens ytterligheter: hela {goal_diff} mål!"
    else:
        data_point_goals = "Målprognos || Mästerskapets Målbalans"
        frame_main = "🔥:::Målprognos:<br>• Väntar på låsta tipsrader"
        goal_benchmark_footer = "Baserat på deltagarnas samlade måltips."

    insight_6 = StaticInsight.objects.create(
        tournament=tournament,
        category='GOAL_DELUSION',
        player_name="Total Målprognos",
        data_point=data_point_goals,
        llm_roast=f"{frame_main} || {goal_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_6)

    # =========================================================================
    # CARD 7: 🎯 SIGN_DECISIVE (Tipset-Filosofi: Spikvilja vs Garderingar)
    # =========================================================================
    if goal_stats:
        tot_decisive = sum(x['decisive'] for x in goal_stats)
        tot_draw = sum(x['draws'] for x in goal_stats)
        pct_decisive = (tot_decisive / tot_all_matches * 100) if tot_all_matches > 0 else 76.0
        pct_draw = (tot_draw / tot_all_matches * 100) if tot_all_matches > 0 else 24.0

        goal_stats.sort(key=lambda x: x['decisive_pct'], reverse=True)
        top_decisive = goal_stats[0]
        
        goal_stats.sort(key=lambda x: x['draws'], reverse=True)
        top_draw = goal_stats[0]

        data_point_decisive = f"{pct_decisive:.0f}% Avgjorda || {pct_draw:.0f}% Kryssgarderingar"
        frame_main = f"⚡:::Spik-specialisten: <span class=\"player-name-pop\">{top_decisive['p_nick']}</span><br>• {top_decisive['decisive_pct']:.0f}% spikade segrar (1 & 2) – endast {top_decisive['draws']} kryss i hela raden<br>• 🤝 Kryss-taktikern: <span class=\"player-name-pop\">{top_draw['p_nick']}</span> med {top_draw['draws']} st kryss ({top_draw['draw_pct']:.0f}%)"
        decisive_footer = "Två helt olika filosofier för att maximera radens poängpotential."
    else:
        data_point_decisive = "Teckenbalans || 1-X-2 Fördelning"
        frame_main = "⚡:::Spikar:<br>• Väntar på låsta tips"
        decisive_footer = "Teckenfördelning i turneringen."

    insight_7 = StaticInsight.objects.create(
        tournament=tournament,
        category='SIGN_DECISIVE',
        player_name="Tipset-Filosofi",
        data_point=data_point_decisive,
        llm_roast=f"{frame_main} || {decisive_footer}",
        is_published=True
    )
    insights_created.append(insight_7)

    # =========================================================================
    # CARD 8: 👟 GOLDEN_BOOT (Skytteligan: Vem Vinner Guldskon?)
    # =========================================================================
    gb_sb = next((sb for sb in sidebets if any(k in sb.question.lower() for k in ["skytteliga", "skytt", "målskytt", "scorer", "golden boot"])), None)
    if not gb_sb and sidebets:
        gb_sb = next((sb for sb in sidebets if sb != champ_sb), None)

    gb_winner_name = "Sidebet"
    frame_main = "👑:::Gruppens favorit:<br>• Inget aktivt skytteligabet"

    if gb_sb:
        answers = list(SidebetAnswer.objects.filter(sidebet=gb_sb, player_id__in=locked_player_ids))
        if answers:
            counts = Counter(a.answer.strip() for a in answers if a.answer.strip())
            if counts:
                top_ans, top_cnt = counts.most_common(1)[0]
                gb_winner_name = top_ans
                top_backers = [
                    get_player_nick_or_name(a.player, personas_list, is_toarp=is_toarp)
                    for a in answers if a.answer.strip() == top_ans
                ]
                backers_bullets = "<br>".join([f"• <span class=\"player-name-pop\">{b}</span>" for b in top_backers])
                frame_main = f"👑:::Gruppens favorit: {top_ans} ({top_cnt} st)<br>{backers_bullets}"

    data_point_gb = f"Mästerskapets Skyttekung || {gb_sb.question if gb_sb else 'Gängets Favorit i Skytteligan'}"
    gb_roast = f"{frame_main} || Bonuspoängen som ger tunga extrapäng till mästerskapsexperten."

    insight_8 = StaticInsight.objects.create(
        tournament=tournament,
        category='GOLDEN_BOOT',
        player_name=gb_winner_name,
        data_point=data_point_gb,
        llm_roast=gb_roast,
        is_published=True
    )
    insights_created.append(insight_8)

    # =========================================================================
    # CARD 9: 🔮 BANKER_CONSENSUS (Konsensus-Fällan: Gängets Mest Sårbara Spik)
    # =========================================================================
    banker_matches = []
    for m in all_tournament_matches:
        m_preds = [p for p in all_preds_qs if p.match_id == m.id]
        if len(m_preds) >= 2:
            h_cnt = sum(1 for p in m_preds if p.home_goals > p.away_goals)
            d_cnt = sum(1 for p in m_preds if p.home_goals == p.away_goals)
            a_cnt = sum(1 for p in m_preds if p.home_goals < p.away_goals)
            
            top_cnt = max(h_cnt, d_cnt, a_cnt)
            pct = (top_cnt / len(m_preds)) * 100.0
            
            sign_str = "Hemmaseger" if top_cnt == h_cnt else ("Bortaseger" if top_cnt == a_cnt else "Kryss")
            home_n = m.get_home_team_info()['name']
            away_n = m.get_away_team_info()['name']
            
            banker_matches.append({
                'match_obj': m,
                'match_name': f"{home_n} vs {away_n}",
                'pct': pct,
                'sign_str': sign_str,
                'count': top_cnt,
                'total': len(m_preds),
                'home_n': home_n,
                'away_n': away_n,
                'm_preds': m_preds
            })

    banker_matches.sort(key=lambda x: -x['pct'])
    top_banker = banker_matches[0] if banker_matches else {
        'match_obj': None,
        'match_name': 'Omgångens Spik', 'pct': 90.0, 'sign_str': 'Hemmaseger', 'count': 4, 'total': 4,
        'home_n': 'Favorit', 'away_n': 'Underdog', 'm_preds': []
    }

    bhf = get_country_flag(top_banker['home_n'])
    baf = get_country_flag(top_banker['away_n'])
    bhf_str = f"{bhf} " if bhf else ""
    baf_str = f"{baf} " if baf else ""
    banker_match_formatted = f"{bhf_str}{top_banker['home_n']} vs {baf_str}{top_banker['away_n']}"

    data_point_banker = f"{top_banker['pct']:.0f}% Enighet || {banker_match_formatted}"
    
    team_backed = f"{bhf_str}{top_banker['home_n']}" if top_banker['sign_str'] == "Hemmaseger" else (f"{baf_str}{top_banker['away_n']}" if top_banker['sign_str'] == "Bortaseger" else "Kryss")
    frame_1 = f"🔒:::{top_banker['count']} av {top_banker['total']} deltagare ({top_banker['pct']:.0f}%) har spikat {team_backed}"
    
    # Audit match-specific mad professors
    rebel_bullets = []
    for p_pred in top_banker['m_preds']:
        p_nick = get_player_nick_or_name(p_pred.player, personas_list, is_toarp=is_toarp)
        if top_banker['sign_str'] == "Hemmaseger" and p_pred.home_goals <= p_pred.away_goals:
            if p_pred.home_goals == p_pred.away_goals:
                rebel_bullets.append(f"• <span class=\"player-name-pop\">{p_nick}</span> <span class=\"sign-badge-blue\">X</span> ({p_pred.home_goals}–{p_pred.away_goals})")
            else:
                rebel_bullets.append(f"• <span class=\"player-name-pop\">{p_nick}</span> {baf_str}{top_banker['away_n']} ({p_pred.home_goals}–{p_pred.away_goals})")
        elif top_banker['sign_str'] == "Bortaseger" and p_pred.home_goals >= p_pred.away_goals:
            if p_pred.home_goals == p_pred.away_goals:
                rebel_bullets.append(f"• <span class=\"player-name-pop\">{p_nick}</span> <span class=\"sign-badge-blue\">X</span> ({p_pred.home_goals}–{p_pred.away_goals})")
            else:
                rebel_bullets.append(f"• <span class=\"player-name-pop\">{p_nick}</span> {bhf_str}{top_banker['home_n']} ({p_pred.home_goals}–{p_pred.away_goals})")
        elif top_banker['sign_str'] == "Kryss" and p_pred.home_goals != p_pred.away_goals:
            w_team = f"{bhf_str}{top_banker['home_n']}" if p_pred.home_goals > p_pred.away_goals else f"{baf_str}{top_banker['away_n']}"
            rebel_bullets.append(f"• <span class=\"player-name-pop\">{p_nick}</span> {w_team} ({p_pred.home_goals}–{p_pred.away_goals})")

    if rebel_bullets:
        frame_2 = "🧪:::Galna professorerna som går emot<br>" + "<br>".join(rebel_bullets)
    else:
        frame_2 = "🧪:::Galna professorerna som går emot<br>• Noll deltagare vågade gå emot flocken"

    # Audit match-specific twins
    score_counts = Counter()
    score_players = defaultdict(list)
    for p_pred in top_banker['m_preds']:
        sc_str = f"{p_pred.home_goals}–{p_pred.away_goals}"
        p_nick = get_player_nick_or_name(p_pred.player, personas_list, is_toarp=is_toarp)
        score_counts[sc_str] += 1
        score_players[sc_str].append(p_nick)

    top_twins = score_counts.most_common(1)
    if top_twins and top_twins[0][1] >= 2:
        top_sc, top_sc_cnt = top_twins[0]
        twin_bullets = "<br>".join([f"• <span class=\"player-name-pop\">{name}</span>" for name in score_players[top_sc]])
        frame_3 = f"👯:::Tvillingtips: {top_sc}<br>{twin_bullets}"
    else:
        frame_3 = "👯:::Konsensus men inte helt profillöst!<br>• Flocken är enad om tecknet men sprider målsiffrorna"

    banker_footer = "Den match där gänget står och faller tillsammans."

    insight_9 = StaticInsight.objects.create(
        tournament=tournament,
        category='BANKER_CONSENSUS',
        player_name=top_banker['match_name'],
        data_point=data_point_banker,
        llm_roast=f"{frame_1}<br><br>{frame_2}<br><br>{frame_3} || {banker_footer}",
        is_published=True
    )
    insights_created.append(insight_9)

    return insights_created
