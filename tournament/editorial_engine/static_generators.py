"""
static_generators.py
--------------------
Generator for Section 1 ("Gängets Tipsanalys & Almanackan").
Analyzes placed predictions BEFORE match results, comparing player prediction metrics,
Decisive Matches vs Draws, Goal Extremes (Grand Optimist vs Pragmatist), Lone-Wolf picks,
Split Decisions, Banker consensus, and Champion consensus.
Produces clean dynamic structured topic boxes for any tournament.
"""

from collections import Counter
from django.db.models import Count
from tournament.models import (
    Tournament, Match, MatchPrediction, Sidebet, SidebetAnswer, StaticInsight
)
from tournament.editorial_engine.compiler import load_player_personas, find_persona_for_player


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


def get_player_nick_or_name(player, personas_list=None, is_toarp=False):
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
    Computes pre-match prediction insights across all users dynamically for ANY tournament.
    Guarantees clean 9 structured cards:
      Row 1: 1. Avgjorda Matcher (1/2) | 2. Oavgjorda Matcher (X)   | 3. Starkaste Bankern
      Row 2: 4. Skiljematch (Delat)    | 5. Målprognos & Extremer   | 6. Omgångens Målfest
      Row 3: 7. Ensamvargar            | 8. Turneringsmästaren      | 9. Skytteliga / Sidebet
    """
    insights_created = []
    
    # Nicknames & personas are strictly restricted to Toarps Herrklubb
    is_toarp = is_toarps_herrklubb_tournament(tournament)
    personas_list = load_player_personas() if is_toarp else []

    # Clear previously generated dynamic static insights for this tournament
    StaticInsight.objects.filter(tournament=tournament).delete()

    players = list(tournament.players.filter(is_staff=False, is_superuser=False))
    if not players:
        # Fallback to distinct players who have predictions
        from django.contrib.auth.models import User
        pred_player_ids = MatchPrediction.objects.filter(
            match__tournament=tournament
        ).values_list('player_id', flat=True).distinct()
        players = list(User.objects.filter(id__in=pred_player_ids))

    if not players:
        return []

    # -------------------------------------------------------------------------
    # Pre-calculate Goal & Sign stats for all players
    # -------------------------------------------------------------------------
    goal_stats = []
    tot_all_goals = 0
    tot_all_matches = 0

    all_tournament_matches = list(Match.objects.filter(tournament=tournament))
    all_preds_qs = list(MatchPrediction.objects.filter(match__tournament=tournament))

    for p in players:
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
            
            draw_pct = (draws / total_matches) * 100.0
            decisive_pct = (decisive / total_matches) * 100.0
            home_pct = (home_wins / total_matches) * 100.0
            away_pct = (away_wins / total_matches) * 100.0

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
                'draw_pct': draw_pct,
                'decisive_pct': decisive_pct,
                'home_pct': home_pct,
                'away_pct': away_pct,
            })

    if not goal_stats:
        return []

    # =========================================================================
    # ROW 1 (SPAR & CONSENSUS)
    # =========================================================================

    # -------------------------------------------------------------------------
    # Card 1: SIGN_DECISIVE (🎯 Avgjorda Matcher: Spikvilja)
    # -------------------------------------------------------------------------
    tot_decisive = sum(x['decisive'] for x in goal_stats)
    pct_decisive = (tot_decisive / tot_all_matches * 100) if tot_all_matches > 0 else 76.0

    goal_stats.sort(key=lambda x: x['decisive_pct'], reverse=True)
    top_decisive = goal_stats[0]
    low_decisive = goal_stats[-1]

    data_point_decisive = f"{pct_decisive:.0f}% || Avgjorda matcher (1 & 2)"
    decisive_extremists = f"⚡ Avgörande-förespråkare: {top_decisive['p_nick']} ({top_decisive['decisive_pct']:.0f}% avgjorda)<br>🛡️ Kryssgarderare: {low_decisive['p_nick']} ({low_decisive['decisive_pct']:.0f}% avgjorda)"
    decisive_footer = f"Totalt {tot_decisive} av {tot_all_matches} tipsrader förutspår en klar segrare."

    insight_1 = StaticInsight.objects.create(
        tournament=tournament,
        category='SIGN_DECISIVE',
        player_name=f"{top_decisive['p_nick']} vs {low_decisive['p_nick']}",
        data_point=data_point_decisive,
        llm_roast=f"{decisive_extremists} || {decisive_footer}",
        is_published=True
    )
    insights_created.append(insight_1)

    # -------------------------------------------------------------------------
    # Card 2: SIGN_BALANCE (🤝 Oavgjorda Matcher: Kryssbenägenhet)
    # -------------------------------------------------------------------------
    tot_draw = sum(x['draws'] for x in goal_stats)
    pct_draw = (tot_draw / tot_all_matches * 100) if tot_all_matches > 0 else 24.0

    goal_stats.sort(key=lambda x: x['draw_pct'], reverse=True)
    top_draw = goal_stats[0]
    low_draw = goal_stats[-1]

    data_point_draw = f"{pct_draw:.0f}% || Oavgjorda matcher (Kryss)"
    draw_extremists = f"👑 Kryss-kungen: {top_draw['p_nick']} ({top_draw['draw_pct']:.0f}% kryss)<br>🚫 Kryss-skeptiker: {low_draw['p_nick']} ({low_draw['draw_pct']:.0f}% kryss)"
    draw_footer = f"Totalt {tot_draw} krysstips registrerade över alla spelarrader."

    insight_2 = StaticInsight.objects.create(
        tournament=tournament,
        category='SIGN_BALANCE',
        player_name=f"{top_draw['p_nick']} vs {low_draw['p_nick']}",
        data_point=data_point_draw,
        llm_roast=f"{draw_extremists} || {draw_footer}",
        is_published=True
    )
    insights_created.append(insight_2)

    # -------------------------------------------------------------------------
    # Card 3: BANKER_CONSENSUS (🔒 Gängets Banker: Superkonsensus)
    # -------------------------------------------------------------------------
    banker_matches = []
    for m in all_tournament_matches:
        m_preds = [p for p in all_preds_qs if p.match_id == m.id]
        if len(m_preds) >= 2:
            h_cnt = sum(1 for p in m_preds if p.home_goals > p.away_goals)
            d_cnt = sum(1 for p in m_preds if p.home_goals == p.away_goals)
            a_cnt = sum(1 for p in m_preds if p.home_goals < p.away_goals)
            
            top_cnt = max(h_cnt, d_cnt, a_cnt)
            pct = (top_cnt / len(m_preds)) * 100.0
            
            # Goal variance tie-breaker (lowest variance wins)
            goals_list = [p.home_goals + p.away_goals for p in m_preds]
            mean_g = sum(goals_list) / len(goals_list)
            variance_g = sum((g - mean_g) ** 2 for g in goals_list) / len(goals_list)
            
            sign_str = "Hemmaseger" if top_cnt == h_cnt else ("Bortaseger" if top_cnt == a_cnt else "Kryss")
            home_n = m.get_home_team_info()['name']
            away_n = m.get_away_team_info()['name']
            
            banker_matches.append({
                'match_name': f"{home_n} vs {away_n}",
                'pct': pct,
                'variance': variance_g,
                'sign_str': sign_str,
                'count': top_cnt,
                'total': len(m_preds)
            })

    # Sort primarily by consensus % descending, then by variance ascending
    banker_matches.sort(key=lambda x: (-x['pct'], x['variance']))
    top_banker = banker_matches[0] if banker_matches else {
        'match_name': 'Omgångens Spik', 'pct': 90.0, 'sign_str': 'Hemmaseger', 'count': 4, 'total': 4
    }

    data_point_banker = f"{top_banker['pct']:.0f}% Enighet || {top_banker['match_name']}"
    banker_extremists = f"🔒 Turneringens säkraste spik: {top_banker['match_name']}<br>📈 {top_banker['count']} av {top_banker['total']} spelare eniga om {top_banker['sign_str'].lower()}."
    banker_footer = "Den match där gängets tipsare är mest överens om slutresultatet."

    insight_3 = StaticInsight.objects.create(
        tournament=tournament,
        category='BANKER_CONSENSUS',
        player_name=top_banker['match_name'],
        data_point=data_point_banker,
        llm_roast=f"{banker_extremists} || {banker_footer}",
        is_published=True
    )
    insights_created.append(insight_3)

    # =========================================================================
    # ROW 2 (SPLIT, GOAL METRICS & GOAL FEST)
    # =========================================================================

    # -------------------------------------------------------------------------
    # Card 4: DELUSION_INDEX (⚡ Skiljematchen: Vattendelaren)
    # -------------------------------------------------------------------------
    split_matches = []
    for m in all_tournament_matches:
        m_preds = [p for p in all_preds_qs if p.match_id == m.id]
        if len(m_preds) >= 2:
            h_cnt = sum(1 for p in m_preds if p.home_goals > p.away_goals)
            d_cnt = sum(1 for p in m_preds if p.home_goals == p.away_goals)
            a_cnt = sum(1 for p in m_preds if p.home_goals < p.away_goals)
            
            # Shannon Entropy calculation for 1-X-2 distribution
            import math
            n = len(m_preds)
            entropy = 0.0
            for cnt in (h_cnt, d_cnt, a_cnt):
                if cnt > 0:
                    prob = cnt / n
                    entropy -= prob * math.log2(prob)
            
            home_n = m.get_home_team_info()['name']
            away_n = m.get_away_team_info()['name']
            split_matches.append({
                'match_name': f"{home_n} vs {away_n}",
                'spread_text': f"1: {h_cnt}st | X: {d_cnt}st | 2: {a_cnt}st",
                'entropy': entropy,
            })

    split_matches.sort(key=lambda x: x['entropy'], reverse=True)
    top_split = split_matches[0] if split_matches else {'match_name': 'Jämn Match', 'spread_text': 'Jämnt fördelade tips'}

    data_point_split = f"Högst Oenighet || {top_split['match_name']}"
    split_extremists = f"⚡ Mest delade åsikter: {top_split['match_name']}<br>📊 Teckenfördelning: {top_split['spread_text']}"
    split_footer = "Matchen där poolens deltagare är som mest splittrade i sina tips."

    insight_4 = StaticInsight.objects.create(
        tournament=tournament,
        category='DELUSION_INDEX',
        player_name=top_split['match_name'],
        data_point=data_point_split,
        llm_roast=f"{split_extremists} || {split_footer}",
        is_published=True
    )
    insights_created.append(insight_4)

    # -------------------------------------------------------------------------
    # Card 5: GOAL_DELUSION (⚽ Målprognos & Extremer)
    # -------------------------------------------------------------------------
    player_count = len(goal_stats)
    predicted_avg_tot_goals = int(tot_all_goals / player_count) if player_count > 0 else 0

    goal_stats.sort(key=lambda x: x['total_goals'], reverse=True)
    grand_optimist = goal_stats[0]
    pragmatist = goal_stats[-1]
    goal_diff = grand_optimist['total_goals'] - pragmatist['total_goals']

    data_point_goals = f"{predicted_avg_tot_goals} mål/snitt || {grand_optimist['total_goals']} vs {pragmatist['total_goals']} mål"
    extremists_text = f"🔥 Grand Optimist: {grand_optimist['p_nick']} ({grand_optimist['total_goals']} mål, {grand_optimist['avg_goals']:.2f}/m)<br>🛡️ Defensiv Pragmatiker: {pragmatist['p_nick']} ({pragmatist['total_goals']} mål, {pragmatist['avg_goals']:.2f}/m)"
    goal_benchmark_footer = f"Målskillnad mellan poolens ytterligheter: hela {goal_diff} mål!"

    insight_5 = StaticInsight.objects.create(
        tournament=tournament,
        category='GOAL_DELUSION',
        player_name=f"{grand_optimist['p_nick']} vs {pragmatist['p_nick']}",
        data_point=data_point_goals,
        llm_roast=f"{extremists_text} || {goal_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_5)

    # -------------------------------------------------------------------------
    # Card 6: CERTIFIED_MADNESS (⏱️ Omgångens Målfest: Målgladaste Matchen)
    # -------------------------------------------------------------------------
    match_goals_summary = []
    for m in all_tournament_matches:
        m_preds = [p for p in all_preds_qs if p.match_id == m.id]
        if m_preds:
            m_tot = sum(p.home_goals + p.away_goals for p in m_preds)
            m_avg = round(m_tot / len(m_preds), 2)
            home_n = m.get_home_team_info()['name']
            away_n = m.get_away_team_info()['name']
            
            # Find who predicted highest goals for this match
            highest_pred = max(m_preds, key=lambda p: p.home_goals + p.away_goals)
            h_nick = get_player_nick_or_name(highest_pred.player, personas_list, is_toarp=is_toarp)
            
            match_goals_summary.append({
                'match_name': f"{home_n} vs {away_n}",
                'avg_goals': m_avg,
                'highest_pred_text': f"{h_nick} ({highest_pred.home_goals}-{highest_pred.away_goals})",
                'match_obj': m,
            })

    match_goals_summary.sort(key=lambda x: x['avg_goals'], reverse=True)
    top_m = match_goals_summary[0] if match_goals_summary else {
        'match_name': 'Målfest', 'avg_goals': 3.5, 'highest_pred_text': '-'
    }

    data_point_fest = f"{top_m['avg_goals']} mål/snitt || {top_m['match_name']}"
    fest_extremists = f"🔥 Målgladaste matchen: {top_m['match_name']}<br>💣 Vassaste måltipset: {top_m['highest_pred_text']}"
    fest_footer = "Högst förväntat målsnitt bland alla matcher i turneringen."

    insight_6 = StaticInsight.objects.create(
        tournament=tournament,
        category='CERTIFIED_MADNESS',
        player_name=top_m['match_name'],
        data_point=data_point_fest,
        llm_roast=f"{fest_extremists} || {fest_footer}",
        is_published=True
    )
    insights_created.append(insight_6)

    # =========================================================================
    # ROW 3 (LONE WOLVES, CHAMPION & SIDEBETS)
    # =========================================================================

    # -------------------------------------------------------------------------
    # Card 7: LONE_WOLF (🐺 Ensamvargar: Djärva Solospel)
    # -------------------------------------------------------------------------
    lone_wolf_candidates = []
    for m in all_tournament_matches:
        m_preds = [p for p in all_preds_qs if p.match_id == m.id]
        if len(m_preds) >= 3:
            home_preds = [p for p in m_preds if p.home_goals > p.away_goals]
            draw_preds = [p for p in m_preds if p.home_goals == p.away_goals]
            away_preds = [p for p in m_preds if p.home_goals < p.away_goals]

            home_n = m.get_home_team_info()['name']
            away_n = m.get_away_team_info()['name']

            if len(away_preds) == 1 and len(home_preds) >= 2:
                hero = away_preds[0]
                hero_nick = get_player_nick_or_name(hero.player, personas_list, is_toarp=is_toarp)
                lone_wolf_candidates.append(f"🐺 {hero_nick}: Ensam om bortaseger i {home_n} vs {away_n} ({hero.home_goals}-{hero.away_goals})")
            elif len(home_preds) == 1 and len(away_preds) >= 2:
                hero = home_preds[0]
                hero_nick = get_player_nick_or_name(hero.player, personas_list, is_toarp=is_toarp)
                lone_wolf_candidates.append(f"🐺 {hero_nick}: Ensam om hemmaseger i {home_n} vs {away_n} ({hero.home_goals}-{hero.away_goals})")
            elif len(draw_preds) == 1 and (len(home_preds) + len(away_preds)) >= 3:
                hero = draw_preds[0]
                hero_nick = get_player_nick_or_name(hero.player, personas_list, is_toarp=is_toarp)
                lone_wolf_candidates.append(f"🐺 {hero_nick}: Ensam om kryss i {home_n} vs {away_n} ({hero.home_goals}-{hero.away_goals})")

    if lone_wolf_candidates:
        lone_str = "<br>".join(lone_wolf_candidates[:3])
        data_point_lone = f"{len(lone_wolf_candidates)} st || Identifierade Ensamvargar"
    else:
        lone_str = "Gänget har tippat förhållandevis enigt utan extrema solospel."
        data_point_lone = "Konsensus || Samstämmiga tips"

    insight_7 = StaticInsight.objects.create(
        tournament=tournament,
        category='LONE_WOLF',
        player_name="Djärva Solospel",
        data_point=data_point_lone,
        llm_roast=f"{lone_str} || Modiga tipsare som går helt mot strömmen.",
        is_published=True
    )
    insights_created.append(insight_7)

    # -------------------------------------------------------------------------
    # Card 8: CHAMPION_CONSENSUS (🏆 Mästarkonsensus)
    # -------------------------------------------------------------------------
    sidebets = list(Sidebet.objects.filter(tournament=tournament))
    champ_sb = next((sb for sb in sidebets if any(k in sb.question.lower() for k in ["vinner", "mästare", "champion", "guld", "segrare"])), None)
    
    champ_name = "Favorit saknas"
    champ_consensus = "👥 Ingen vinnarfråga registrerad"
    champ_lone_wolves = "Inga ensamvargar registrerade"

    if champ_sb:
        answers = list(SidebetAnswer.objects.filter(sidebet=champ_sb))
        if answers:
            counts = Counter(a.answer.strip() for a in answers if a.answer.strip())
            if counts:
                top_ans, top_cnt = counts.most_common(1)[0]
                champ_name = top_ans
                champ_consensus = f"👥 Gruppens konsensus: {top_ans} ({top_cnt} tippare)"

                lone_list = []
                for ans_val, cnt in counts.items():
                    if cnt == 1:
                        ans_obj = next((a for a in answers if a.answer.strip() == ans_val), None)
                        if ans_obj:
                            p_nick = get_player_nick_or_name(ans_obj.player, personas_list, is_toarp=is_toarp)
                            lone_list.append(f"{p_nick} ({ans_val})")
                if lone_list:
                    champ_lone_wolves = "🐺 Ensamvargar:<br>• " + "<br>• ".join(lone_list[:3])
                else:
                    champ_lone_wolves = "Alla deltagare delar på favoritvalen."

    data_point_champ = f"{champ_name} || Turneringsfavoriten"
    champ_extremists = f"{champ_consensus}<br>{champ_lone_wolves}"
    champ_benchmark_footer = f"Baserat på registrerade svar på mästarfrågan i {tournament.name}."

    insight_8 = StaticInsight.objects.create(
        tournament=tournament,
        category='CHAMPION_CONSENSUS',
        player_name=champ_name,
        data_point=data_point_champ,
        llm_roast=f"{champ_extremists} || {champ_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_8)

    # -------------------------------------------------------------------------
    # Card 9: GOLDEN_BOOT / SECONDARY_SIDEBET (👟 Skytteliga & Sidebets)
    # -------------------------------------------------------------------------
    gb_sb = next((sb for sb in sidebets if any(k in sb.question.lower() for k in ["skytteliga", "skytt", "målskytt", "scorer", "golden boot"])), None)
    if not gb_sb and sidebets:
        gb_sb = next((sb for sb in sidebets if sb != champ_sb), None)

    gb_winner_name = "Sidebet"
    gb_consensus_text = "👑 Inget aktivt sidebet"
    gb_lone_wolf_text = "Inga registrerade svar"

    if gb_sb:
        answers = list(SidebetAnswer.objects.filter(sidebet=gb_sb))
        if answers:
            counts = Counter(a.answer.strip() for a in answers if a.answer.strip())
            if counts:
                top_ans, top_cnt = counts.most_common(1)[0]
                gb_winner_name = top_ans
                gb_consensus_text = f"👑 Favoriten: {top_ans} ({top_cnt} tippare)"
                
                lone_list = []
                for ans_val, cnt in counts.items():
                    if cnt == 1 and ans_val != top_ans:
                        ans_obj = next((a for a in answers if a.answer.strip() == ans_val), None)
                        if ans_obj:
                            p_nick = get_player_nick_or_name(ans_obj.player, personas_list, is_toarp=is_toarp)
                            lone_list.append(f"{p_nick} ({ans_val})")
                if lone_list:
                    gb_lone_wolf_text = "🐺 Ensamvargar:<br>• " + "<br>• ".join(lone_list[:3])
                else:
                    gb_lone_wolf_text = "Eniga tips bland deltagarna."

    data_point_gb = f"{gb_winner_name} || {gb_sb.question if gb_sb else 'Gängets Sidebet'}"
    gb_extremists = f"{gb_consensus_text}<br>{gb_lone_wolf_text}"
    gb_benchmark_footer = f"Baserat på deltagarnas svar i {tournament.name}."

    insight_9 = StaticInsight.objects.create(
        tournament=tournament,
        category='GOLDEN_BOOT',
        player_name=gb_winner_name,
        data_point=data_point_gb,
        llm_roast=f"{gb_extremists} || {gb_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_9)

    return insights_created
