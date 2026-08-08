"""
euro_benchmarks.py
------------------
Official UEFA EURO historical benchmarks and comparison helper utilities.
"""

EURO_HISTORICAL_STATS = {
    "avg_goals_per_match": 2.42,
    "euro_2020_goals_per_match": 2.78,
    "euro_2016_goals_per_match": 2.12,
    "euro_2012_goals_per_match": 2.45,
    "draw_percentage": 23.5,       # ~23.5% of group stage Euro matches end in draws
    "sign_distribution": {
        "1": 44.0,                  # ~44% Home wins
        "X": 24.0,                  # ~24% Draws
        "2": 32.0                   # ~32% Away wins
    },
    "top_scorer_goals": 5.5,        # 5-6 goals typical for Euro Golden Boot (e.g., Ronaldo 5 in 2020, Griezmann 6 in 2016)
    "high_scoring_match_rate": 5.2, # ~5.2% of matches feature 5+ goals
}


def compare_goals_per_match(player_avg: float, player_nick: str) -> str:
    """
    Compares a player's predicted average goals per match against Euro benchmarks.
    """
    euro_avg = EURO_HISTORICAL_STATS["avg_goals_per_match"]
    euro_2020 = EURO_HISTORICAL_STATS["euro_2020_goals_per_match"]
    euro_2016 = EURO_HISTORICAL_STATS["euro_2016_goals_per_match"]

    diff = player_avg - euro_avg

    if player_avg >= euro_2020:
        return (
            f"EURO-Historik: Historiska EM snittar 2.42 mål/match. {player_nick}s prognos på {player_avg:.2f} mål/match "
            f"överträffar till och med det galna EURO 2020-rekordet på {euro_2020:.2f} mål/match!"
        )
    elif player_avg > euro_avg:
        return (
            f"EURO-Historik: Historiska EM har ett snitt på {euro_avg:.2f} mål/match. {player_nick} ligger "
            f"{diff:+.2f} mål över det historiska EM-genomsnittet och förväntar sig en offensiv turnering."
        )
    elif player_avg < euro_2016:
        return (
            f"EURO-Historik: Historiska EM snittar {euro_avg:.2f} mål/match. {player_nick}s försiktiga {player_avg:.2f} mål/match "
            f"är lägre än det extremt målsnåla EURO 2016 ({euro_2016:.2f} mål/match)."
        )
    else:
        return (
            f"EURO-Historik: {player_nick}s målsnitt på {player_avg:.2f} mål/match ligger helt i linje med "
            f"det historiska EM-snittet på {euro_avg:.2f} mål per match."
        )


def compare_draw_percentage(player_draw_pct: float, player_nick: str) -> str:
    """
    Compares a player's draw percentage prediction against Euro benchmarks.
    """
    euro_draw_pct = EURO_HISTORICAL_STATS["draw_percentage"]
    diff = player_draw_pct - euro_draw_pct

    if player_draw_pct < 15.0:
        return (
            f"EURO-Historik: I EM slutar cirka 24% av matcherna oavgjort ({euro_draw_pct:.1f}%). "
            f"{player_nick} tippar endast {player_draw_pct:.0f}% kryss och förkastar den historiska oavgjorts-statistiken."
        )
    elif player_draw_pct >= 30.0:
        return (
            f"EURO-Historik: EM har i snitt {euro_draw_pct:.1f}% oavgjorda matcher. {player_nick} sticker ut "
            f"med hela {player_draw_pct:.0f}% kryss ({diff:+.1f}% mot EM-historiken)."
        )
    else:
        return (
            f"EURO-Historik: {player_nick}s kryssandel på {player_draw_pct:.0f}% matchar EM-historikens {euro_draw_pct:.1f}% kryssfrekvens perfekt."
        )
