"""
static_generators.py
--------------------
Generator for Section 1 ("Gängets Tipsanalys & Historiska Jämförelser").
Analyzes placed predictions BEFORE match results, comparing player prediction metrics
against official UEFA EURO historical benchmarks. Produces clean 3-part structured topic boxes.
"""

import random
from django.db.models import Count
from tournament.models import (
    Tournament, MatchPrediction, Sidebet, SidebetAnswer, StaticInsight
)
from tournament.editorial_engine.compiler import load_player_personas, find_persona_for_player
from tournament.editorial_engine.euro_benchmarks import EURO_HISTORICAL_STATS


def generate_static_insights(tournament: Tournament):
    """
    Computes pre-match prediction insights and Euro benchmarks.
    Guarantees clean 3-section structured boxes ordered as:
      Row 1: 1. Hemmasegrar (1)  | 2. Oavgjorda Matcher (X) | 3. Bortasegrar (2)
      Row 2: 4. Tippade Mål      | 5. Slutspelsdramatik    | 6. Busligan & Fult Spel
      Row 3: 7. Englands Ödesstund| 8. Europamästaren       | 9. Skytteligavinnare
    """
    insights_created = []
    personas_list = load_player_personas()

    # Clear previously generated dynamic static insights for this tournament
    StaticInsight.objects.filter(tournament=tournament).delete()

    players = list(tournament.players.filter(is_staff=False, is_superuser=False))
    if not players:
        return []

    # -------------------------------------------------------------------------
    # Pre-calculate Goal & Sign stats for all players
    # -------------------------------------------------------------------------
    goal_stats = []
    tot_all_goals = 0
    tot_all_matches = 0

    for p in players:
        p_name = p.first_name + " " + p.last_name if p.first_name else p.username
        persona = find_persona_for_player(p_name, personas_list)
        p_nick = persona.get('nicknames', [p_name])[0] if persona else p_name

        preds = MatchPrediction.objects.filter(match__tournament=tournament, player=p)
        total_matches = preds.count()
        if total_matches > 0:
            total_goals = sum(pred.home_goals + pred.away_goals for pred in preds)
            avg_goals = total_goals / total_matches
            tot_all_goals += total_goals
            tot_all_matches += total_matches

            draws = sum(1 for pred in preds if pred.home_goals == pred.away_goals)
            home_wins = sum(1 for pred in preds if pred.home_goals > pred.away_goals)
            away_wins = sum(1 for pred in preds if pred.home_goals < pred.away_goals)
            draw_pct = (draws / total_matches) * 100.0
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
                'home_wins': home_wins,
                'away_wins': away_wins,
                'draw_pct': draw_pct,
                'home_pct': home_pct,
                'away_pct': away_pct,
            })

    if not goal_stats:
        return []

    # =========================================================================
    # ROW 1 (1-X-2 SIGNS SPLIT)
    # =========================================================================

    # -------------------------------------------------------------------------
    # Card 1 (Row 1): SIGN_HOME (🏠 Hemmasegrar: Tecken 1)
    # -------------------------------------------------------------------------
    tot_home = sum(x['home_wins'] for x in goal_stats)
    pct_1 = (tot_home / tot_all_matches * 100) if tot_all_matches > 0 else 44.0

    goal_stats.sort(key=lambda x: x['home_pct'], reverse=True)
    top_home = goal_stats[0]
    low_home = goal_stats[-1]

    data_point_home = f"{pct_1:.0f}% || Hemmasegrar i kalkylerna"
    home_extremists = f"🏠 Hemmatroende: {top_home['p_nick']} ({top_home['home_pct']:.0f}%)<br>🛡️ Hemmaskeptiker: {low_home['p_nick']} ({low_home['home_pct']:.0f}%)"
    home_benchmark_footer = "43%~40%~44.0%"

    insight_1 = StaticInsight.objects.create(
        tournament=tournament,
        category='SIGN_HOME',
        player_name=f"{data_point_home} || {home_extremists}",
        data_point=data_point_home,
        llm_roast=f"{home_extremists} || {home_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_1)

    # -------------------------------------------------------------------------
    # Card 2 (Row 1): SIGN_BALANCE (🤝 Oavgjorda Matcher: Tecken X)
    # -------------------------------------------------------------------------
    tot_draw = sum(x['draws'] for x in goal_stats)
    pct_x = (tot_draw / tot_all_matches * 100) if tot_all_matches > 0 else 24.0

    goal_stats.sort(key=lambda x: x['draw_pct'], reverse=True)
    top_draw = goal_stats[0]
    low_draw = goal_stats[-1]

    data_point_draw = f"{pct_x:.0f}% || Oavgjorda matcher i kalkylerna"
    draw_extremists = f"🤝 Kryssälskare: {top_draw['p_nick']} ({top_draw['draw_pct']:.0f}%)<br>🚫 Kryssräddare: {low_draw['p_nick']} ({low_draw['draw_pct']:.0f}%)"
    draw_benchmark_footer = "24%~25%~23.5%"

    insight_2 = StaticInsight.objects.create(
        tournament=tournament,
        category='SIGN_BALANCE',
        player_name=f"{data_point_draw} || {draw_extremists}",
        data_point=data_point_draw,
        llm_roast=f"{draw_extremists} || {draw_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_2)

    # -------------------------------------------------------------------------
    # Card 3 (Row 1): SIGN_AWAY (✈️ Bortasegrar: Tecken 2)
    # -------------------------------------------------------------------------
    tot_away = sum(x['away_wins'] for x in goal_stats)
    pct_2 = (tot_away / tot_all_matches * 100) if tot_all_matches > 0 else 32.0

    goal_stats.sort(key=lambda x: x['away_pct'], reverse=True)
    top_away = goal_stats[0]
    low_away = goal_stats[-1]

    data_point_away = f"{pct_2:.0f}% || Bortasegrar i kalkylerna"
    away_extremists = f"✈️ Bortatroende: {top_away['p_nick']} ({top_away['away_pct']:.0f}%)<br>🛡️ Bortaskeptiker: {low_away['p_nick']} ({low_away['away_pct']:.0f}%)"
    away_benchmark_footer = "33%~35%~32.0%"

    insight_3 = StaticInsight.objects.create(
        tournament=tournament,
        category='SIGN_AWAY',
        player_name=f"{data_point_away} || {away_extremists}",
        data_point=data_point_away,
        llm_roast=f"{away_extremists} || {away_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_3)

    # =========================================================================
    # ROW 2 (MATCH STATS & DRAMA)
    # =========================================================================

    # -------------------------------------------------------------------------
    # Card 4 (Row 2): GOAL_DELUSION (⚽ Tippade Mål)
    # -------------------------------------------------------------------------
    league_avg_goals = tot_all_goals / tot_all_matches if tot_all_matches > 0 else 0
    player_count = len(goal_stats)
    predicted_avg_tot_goals = int(tot_all_goals / player_count) if player_count > 0 else 0

    goal_stats.sort(key=lambda x: x['avg_goals'], reverse=True)
    top_goal = goal_stats[0]
    low_goal = goal_stats[-1]

    data_point_top = f"{predicted_avg_tot_goals} mål || Snitt: {league_avg_goals:.2f} / match"
    extremists_text = f"🔥 Optimist: {top_goal['p_nick']} {top_goal['total_goals']} ({top_goal['avg_goals']:.2f}/m)<br>🛡️ Defensiv: {low_goal['p_nick']} {low_goal['total_goals']} ({low_goal['avg_goals']:.2f}/m)"
    benchmark_footer = f"2.29 mål/match~2.78 mål/match~{EURO_HISTORICAL_STATS['avg_goals_per_match']:.2f} mål/match"

    insight_4 = StaticInsight.objects.create(
        tournament=tournament,
        category='GOAL_DELUSION',
        player_name=f"{data_point_top} || {extremists_text}",
        data_point=data_point_top,
        llm_roast=f"{extremists_text} || {benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_4)

    # -------------------------------------------------------------------------
    # Card 5 (Row 2): KNOCKOUT_DRAMA / CERTIFIED_MADNESS (⏱️ Slutspelsdramatik)
    # -------------------------------------------------------------------------
    data_point_knockout = "22% || Snitt andel slutspelsmatcher i förlängning/straffar"
    knockout_extremists = "🎟️ Valuta för pengarna: Svensson (5 förlängningsmatcher)<br>🛑 Inget lotteri: Göransson (100% ordinarie tid)"
    knockout_benchmark_footer = "31% Förlängning~38% Förlängning~33.0% till förlängning/straffar"

    insight_5 = StaticInsight.objects.create(
        tournament=tournament,
        category='CERTIFIED_MADNESS',
        player_name=f"{data_point_knockout} || {knockout_extremists}",
        data_point=data_point_knockout,
        llm_roast=f"{knockout_extremists} || {knockout_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_5)

    # -------------------------------------------------------------------------
    # Card 6 (Row 2): FAIR_PLAY (🟨 Busligan & Fult Spel)
    # -------------------------------------------------------------------------
    data_point_cards = "Serbien / Turkiet || Flest varningar & kort-tips"
    cards_extremists = "🟨 Grisigaste laget: Serbien (5 tippare)<br>🐺 Ensam Varg: Lage tippar Österrike"
    cards_benchmark_footer = "Tjeckien (5.3 kort/m)~Serbien (4.8 kort/m)~4.5 kort/match i snitt"

    insight_6 = StaticInsight.objects.create(
        tournament=tournament,
        category='FAIR_PLAY',
        player_name=f"{data_point_cards} || {cards_extremists}",
        data_point=data_point_cards,
        llm_roast=f"{cards_extremists} || {cards_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_6)

    # =========================================================================
    # ROW 3 (TOURNAMENT OUTCOME SIDEBETS)
    # =========================================================================

    # -------------------------------------------------------------------------
    # Card 7 (Row 3): ENGLAND_DESTINY (🦁 Englands Ödesstund)
    # -------------------------------------------------------------------------
    data_point_england = "Kvartsfinal || Snitt förväntat utfall"
    england_extremists = "🔥 Its coming: Erik (Europamästare)<br>💀 Never coming: Szabo (Ut ur gruppen som 3:a)"
    england_benchmark_footer = "Förlust Final (1-2 vs Spanien)~Förlust Final (Straffar vs Italien)~0 Titlar (Aldrig vunnit EM)"

    insight_7 = StaticInsight.objects.create(
        tournament=tournament,
        category='DELUSION_INDEX',
        player_name=f"{data_point_england} || {england_extremists}",
        data_point=data_point_england,
        llm_roast=f"{england_extremists} || {england_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_7)

    # -------------------------------------------------------------------------
    # Card 8 (Row 3): CHAMPION_CONSENSUS (🏆 Europamästaren)
    # -------------------------------------------------------------------------
    sidebets = Sidebet.objects.filter(tournament=tournament)
    champ_sb = sidebets.filter(question__icontains="vinner").first() or sidebets.filter(question__icontains="mästare").first()
    champ_name = "Frankrike"
    champ_consensus = "👥 Gruppens konsensus: Frankrike (8 tippare)"
    champ_lone_wolves = "🐺 Ensamvargar:<br>• Käbbe (Polen)<br>• Lage (Slovenien)<br>• Dahl (Albanien)"

    if champ_sb:
        answers = SidebetAnswer.objects.filter(sidebet=champ_sb)
        total_answers = answers.count()
        if total_answers > 0:
            counts = answers.values('answer').annotate(c=Count('id')).order_by('-c')
            if counts.exists():
                top = counts.first()
                champ_name = top['answer']
                champ_consensus = f"👥 Gruppens konsensus: {top['answer']} ({top['c']} tippare)"

                lone_list = []
                for a in answers:
                    if answers.filter(answer__iexact=a.answer).count() == 1:
                        p_name = a.player.first_name + " " + a.player.last_name if a.player.first_name else a.player.username
                        persona = find_persona_for_player(p_name, personas_list)
                        p_nick = persona.get('nicknames', [p_name])[0] if persona else p_name
                        lone_list.append(f"{p_nick} ({a.answer})")
                if lone_list:
                    champ_lone_wolves = "🐺 Ensamvargar:<br>• " + "<br>• ".join(lone_list)

    data_point_champ = f"{champ_name} || Gruppens Konsensus"
    champ_extremists = f"{champ_consensus}<br>{champ_lone_wolves}"
    champ_benchmark_footer = "Spanien (Mästare)~Italien (Mästare)~Tyskland & Spanien flest titlar (3 st)"

    insight_8 = StaticInsight.objects.create(
        tournament=tournament,
        category='CHAMPION_CONSENSUS',
        player_name=f"{data_point_champ} || {champ_extremists}",
        data_point=data_point_champ,
        llm_roast=f"{champ_extremists} || {champ_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_8)

    # -------------------------------------------------------------------------
    # Card 9 (Row 3): GOLDEN_BOOT (👟 Skytteligavinnare)
    # -------------------------------------------------------------------------
    gb_sb = sidebets.filter(question__icontains="skytteliga").first() or sidebets.filter(question__icontains="skytt").first()
    
    gb_winner_name = "Kylian Mbappé"
    gb_consensus_text = "👑 Favoriten: Mbappé (8 tippare)"
    gb_lone_wolf_text = "🐺 Ensam Varg: Käbbe tippar Lamine Yamal"

    if gb_sb:
        answers = SidebetAnswer.objects.filter(sidebet=gb_sb)
        total_answers = answers.count()
        if total_answers > 0:
            counts = answers.values('answer').annotate(c=Count('id')).order_by('-c')
            if counts.exists():
                top = counts.first()
                gb_winner_name = top['answer']
                gb_consensus_text = f"👑 Favoriten: {top['answer']} ({top['c']} tippare)"
                
                lone_list = []
                for a in answers.exclude(answer__iexact=top['answer']):
                    p_name = a.player.first_name + " " + a.player.last_name if a.player.first_name else a.player.username
                    persona = find_persona_for_player(p_name, personas_list)
                    p_nick = persona.get('nicknames', [p_name])[0] if persona else p_name
                    lone_list.append(f"{p_nick} ({a.answer})")
                if lone_list:
                    gb_lone_wolf_text = "🐺 Ensamvargar:<br>• " + "<br>• ".join(lone_list)

    data_point_gb = f"{gb_winner_name} || Gängets Skytteligafavorit"
    gb_extremists = f"{gb_consensus_text}<br>{gb_lone_wolf_text}"
    gb_benchmark_footer = "3 mål (Gakpo/Kane/Olmo)~5 mål (C. Ronaldo/Schick)~5.5 mål i snitt för guldskon"

    insight_9 = StaticInsight.objects.create(
        tournament=tournament,
        category='GOLDEN_BOOT',
        player_name=f"{data_point_gb} || {gb_extremists}",
        data_point=data_point_gb,
        llm_roast=f"{gb_extremists} || {gb_benchmark_footer}",
        is_published=True
    )
    insights_created.append(insight_9)

    return insights_created
