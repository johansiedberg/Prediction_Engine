"""
Format Blueprint Service
========================
Maintains canonical knowledge blueprints for major international championships and qualification tournaments.
Provides instant, authentic tournament structure profiles:
- Group allocation (number of groups, team distribution, skeleton seed pots)
- Advancement rules (direct qualifiers, ranking of runners-up table, ranking of best 3rds)
- Exact point systems (Football: 3/1/0, Basketball: 2/0/1, Handball: 2/1/0, Ice Hockey: 3/1/0)
- Authentic knockout bracket paths (Round of 32, Round of 16, Quarterfinals, Semifinals, 3rd Place Match, Final, Play-off Paths)
"""

import re
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class FormatBlueprintService:
    """
    Canonical Knowledge Registry for major international tournaments.
    """

    @classmethod
    def get_canonical_blueprint(cls, tournament_name: str, sport: str = "Football") -> Optional[Dict[str, Any]]:
        if not tournament_name:
            return None

        t_name = tournament_name.strip()
        t_lower = t_name.lower()
        sport_lower = (sport or "").lower()

        # 1. UEFA Euro Qualifying (e.g. "UEFA Euro 2028 qualifying", "Euro 2028 Qualifiers")
        if ("euro" in t_lower or "em-" in t_lower or "european championship" in t_lower) and ("qualif" in t_lower or "kval" in t_lower):
            group_letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
            groups_data = []
            for idx, letter in enumerate(group_letters, start=1):
                # 6 groups of 5 teams + 6 groups of 4 teams = 54 total teams
                teams_in_grp = 5 if idx <= 6 else 4
                teams_list = []
                for s_idx in range(1, teams_in_grp + 1):
                    teams_list.append({
                        "name": f"Pott {s_idx} ({letter}{s_idx})",
                        "code": f"{letter}{s_idx}",
                        "seed": f"Pott {s_idx}",
                        "is_placeholder": True
                    })
                groups_data.append({
                    "name": f"Group {letter}",
                    "teams": teams_list
                })

            return {
                "groups_count": 12,
                "teams_count": 54,
                "draw_completed": False,
                "points_system": {"win": 3, "draw": 1, "loss": 0},
                "advancement_logic": {
                    "teams_per_group_advancing": 1,
                    "has_best_thirds_table": False,
                    "best_third_placed_advancing": 0,
                    "has_runners_up_table": True,
                    "runners_up_advancing": 8,
                    "qualifying_table_ranking_criteria": [
                        "Poäng",
                        "Målskillnad",
                        "Gjorda mål",
                        "Gjorda bortamål",
                        "Disciplinpoäng",
                        "Nations League-ranking"
                    ],
                    "description": "De 12 gruppvinnarna och de 8 bästa tvåorna (totalt 20 lag) kvalificerar sig direkt till EM. Övriga 4 tvåor och Nations League-lag avancerar till Play-off."
                },
                "groups": groups_data,
                "knockout_rules": {
                    "starting_round": "Play-off Semifinals",
                    "total_rounds": 2,
                    "has_penalties": True,
                    "has_third_place_match": False,
                    "extra_time_minutes": 30,
                    "tiebreaker_description": "Playoff avgörs i enkelmöten med förlängning (2x15 min) och straffsparksläggning vid oavgjort."
                },
                "knockout_stages": [
                    {
                        "stage_name": "Play-off Semifinals",
                        "matches": [
                            {"match_code": "PO_A_SF1", "home_team": "Path A Lag 1", "away_team": "Path A Lag 4", "winner_to": "PO_A_FINAL"},
                            {"match_code": "PO_A_SF2", "home_team": "Path A Lag 2", "away_team": "Path A Lag 3", "winner_to": "PO_A_FINAL"},
                            {"match_code": "PO_B_SF1", "home_team": "Path B Lag 1", "away_team": "Path B Lag 4", "winner_to": "PO_B_FINAL"},
                            {"match_code": "PO_B_SF2", "home_team": "Path B Lag 2", "away_team": "Path B Lag 3", "winner_to": "PO_B_FINAL"},
                            {"match_code": "PO_C_SF1", "home_team": "Path C Lag 1", "away_team": "Path C Lag 4", "winner_to": "PO_C_FINAL"},
                            {"match_code": "PO_C_SF2", "home_team": "Path C Lag 2", "away_team": "Path C Lag 3", "winner_to": "PO_C_FINAL"},
                        ]
                    },
                    {
                        "stage_name": "Play-off Finals",
                        "matches": [
                            {"match_code": "PO_A_FINAL", "home_team": "Vinnare PO_A_SF1", "away_team": "Vinnare PO_A_SF2", "winner_to": "UEFA Euro 2028 (Gruppspel)"},
                            {"match_code": "PO_B_FINAL", "home_team": "Vinnare PO_B_SF1", "away_team": "Vinnare PO_B_SF2", "winner_to": "UEFA Euro 2028 (Gruppspel)"},
                            {"match_code": "PO_C_FINAL", "home_team": "Vinnare PO_C_SF1", "away_team": "Vinnare PO_C_SF2", "winner_to": "UEFA Euro 2028 (Gruppspel)"},
                        ]
                    }
                ],
                "official_rules_summary": "UEFA Euro 2028 qualifying: 54 nationer är indelade i 12 grupper (6 grupper med 5 lag och 6 grupper med 4 lag). Gruppvinnarna (12 lag) samt de 8 bästa grupptvåorna från den gemensamma tvåorankingen kvalificerar sig direkt till slutturneringen. De resterande 4 tvåorna och bäst rankade lag från UEFA Nations League avancerar till Playoff där ytterligare 3 platser fördelas via enkelmöten (semifinaler och finaler i Path A, B och C)."
            }

        # 2. UEFA Euro Flagship Finals (e.g. "UEFA Euro 2028", "UEFA Euro 2032")
        if ("euro" in t_lower or "em" in t_lower) and "qualif" not in t_lower and "kval" not in t_lower and "u19" not in t_lower and "u21" not in t_lower:
            group_letters = ["A", "B", "C", "D", "E", "F"]
            groups_data = []
            for letter in group_letters:
                groups_data.append({
                    "name": f"Group {letter}",
                    "teams": [{"name": f"{letter}{idx} (TBD)", "code": f"{letter}{idx}", "is_placeholder": True} for idx in range(1, 5)]
                })

            return {
                "groups_count": 6,
                "teams_count": 24,
                "points_system": {"win": 3, "draw": 1, "loss": 0},
                "advancement_logic": {
                    "teams_per_group_advancing": 2,
                    "has_best_thirds_table": True,
                    "best_third_placed_advancing": 4,
                    "has_runners_up_table": False,
                    "runners_up_advancing": 0,
                    "qualifying_table_ranking_criteria": ["Poäng", "Målskillnad", "Gjorda mål", "Disciplinpoäng", "Kvalranking"],
                    "description": "De 2 bästa lagen från varje grupp (12 lag) samt de 4 bästa treorna (totalt 16 lag) avancerar till Åttondelsfinal."
                },
                "groups": groups_data,
                "knockout_rules": {
                    "starting_round": "Round of 16",
                    "total_rounds": 4,
                    "has_penalties": True,
                    "has_third_place_match": False,  # No 3rd place match in Euro since 1984
                    "extra_time_minutes": 30,
                    "tiebreaker_description": "Förlängning (2x15 min) följt av Straffsparksläggning vid oavgjort."
                },
                "official_rules_summary": "UEFA European Championship (Euro): 24 lag i 6 grupper om 4 lag. Topp 2 från varje grupp samt de 4 bästa treorna avancerar till utslagsträdet (Åttondelsfinaler -> Kvartsfinaler -> Semifinaler -> Final). Ingen match om tredje pris spelas."
            }

        # 3. 48-Team FIFA World Cup (e.g. "2026 FIFA World Cup")
        if "fifa world cup" in t_lower and "u-20" not in t_lower and "u-17" not in t_lower and "qualif" not in t_lower:
            group_letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
            groups_data = []
            for letter in group_letters:
                groups_data.append({
                    "name": f"Group {letter}",
                    "teams": [{"name": f"{letter}{idx} (TBD)", "code": f"{letter}{idx}", "is_placeholder": True} for idx in range(1, 5)]
                })

            return {
                "groups_count": 12,
                "teams_count": 48,
                "points_system": {"win": 3, "draw": 1, "loss": 0},
                "advancement_logic": {
                    "teams_per_group_advancing": 2,
                    "has_best_thirds_table": True,
                    "best_third_placed_advancing": 8,
                    "has_runners_up_table": False,
                    "runners_up_advancing": 0,
                    "qualifying_table_ranking_criteria": ["Poäng", "Målskillnad", "Gjorda mål", "Disciplinpoäng", "FIFA-ranking"],
                    "description": "De 2 bästa lagen per grupp (24 lag) samt de 8 bästa treorna (totalt 32 lag) avancerar till Round of 32 (32-delsfinal)."
                },
                "groups": groups_data,
                "knockout_rules": {
                    "starting_round": "Round of 32",
                    "total_rounds": 5,
                    "has_penalties": True,
                    "has_third_place_match": True,
                    "extra_time_minutes": 30,
                    "tiebreaker_description": "Förlängning (2x15 min) följt av Straffsparksläggning vid oavgjort. Match om 3:e pris spelas före finalen."
                },
                "official_rules_summary": "FIFA World Cup (48 lag): 12 grupper om 4 lag. De två främsta i varje grupp samt de åtta bästa treorna avancerar till Round of 32. Utslagsträdet spelas i 5 omgångar med förlängning och straffar, inklusive match om tredje pris (bronsmatch)."
            }

        # 4. UEFA Nations League (e.g. "2026–27 UEFA Nations League")
        if "nations league" in t_lower:
            return {
                "groups_count": 14,
                "teams_count": 54,
                "points_system": {"win": 3, "draw": 1, "loss": 0},
                "advancement_logic": {
                    "teams_per_group_advancing": 2,
                    "has_best_thirds_table": False,
                    "best_third_placed_advancing": 0,
                    "has_runners_up_table": False,
                    "runners_up_advancing": 0,
                    "description": "De 2 främsta lagen från varje League A-grupp (A1–A4, totalt 8 lag) avancerar till League A Kvartsfinaler."
                },
                "knockout_rules": {
                    "starting_round": "Quarterfinals",
                    "total_rounds": 3,
                    "has_penalties": True,
                    "has_third_place_match": True,
                    "extra_time_minutes": 30,
                    "tiebreaker_description": "League A-slutspelet avgörs via Kvartsfinaler (hemma/borta eller enkelmöten), följt av Nations League Finals (Semifinaler, Match om 3:e pris och Final)."
                }
            }

        # 5. FIBA Basketball World Cup & FIBA U19 (e.g. "2027 FIBA Basketball World Cup", "FIBA Under-19")
        if "fiba" in t_lower or "basketball world cup" in t_lower:
            is_u19 = "u-19" in t_lower or "under-19" in t_lower or "u19" in t_lower
            g_count = 4 if is_u19 else 8
            t_count = 16 if is_u19 else 32
            group_letters = [chr(65 + i) for i in range(g_count)]
            groups_data = []
            for letter in group_letters:
                groups_data.append({
                    "name": f"Group {letter}",
                    "teams": [{"name": f"{letter}{idx} (TBD)", "code": f"{letter}{idx}", "is_placeholder": True} for idx in range(1, 5)]
                })

            return {
                "groups_count": g_count,
                "teams_count": t_count,
                "draw_completed": False,
                "points_system": {"win": 2, "draw": 0, "loss": 1},
                "advancement_logic": {
                    "teams_per_group_advancing": 2,
                    "has_best_thirds_table": False,
                    "best_third_placed_advancing": 0,
                    "has_runners_up_table": False,
                    "runners_up_advancing": 0,
                    "description": "Topp 2 i varje grupp avancerar till Kvartsfinaler (eller Mellanrunda/Second Round för senior VM)."
                },
                "groups": groups_data,
                "knockout_rules": {
                    "starting_round": "Quarterfinals",
                    "total_rounds": 3,
                    "has_penalties": False,
                    "has_third_place_match": True,
                    "extra_time_minutes": 5,
                    "tiebreaker_description": "Förlängning (5 min per period tills avgörande). Match om 3:e pris spelas före finalen."
                },
                "official_rules_summary": "FIBA World Cup: Poängsystem 2 poäng för vinst, 1 poäng för förlust. Vid oavgjort efter ordinarie tid spelas förlängning om 5 minuter. Slutspelsträdet omfattar Kvartsfinaler, Semifinaler, Match om 3:e pris samt Final."
            }

        # 6. Handball World Championship / EHF Euro (e.g. "2027 World Men's Handball Championship")
        if "handball" in sport_lower or "handboll" in sport_lower:
            group_letters = [chr(65 + i) for i in range(8)]
            groups_data = []
            for letter in group_letters:
                groups_data.append({
                    "name": f"Group {letter}",
                    "teams": [{"name": f"{letter}{idx} (TBD)", "code": f"{letter}{idx}", "is_placeholder": True} for idx in range(1, 5)]
                })

            return {
                "groups_count": 8,
                "teams_count": 32,
                "draw_completed": False,
                "groups": groups_data,
                "points_system": {"win": 2, "draw": 1, "loss": 0},
                "match_format": {
                    "regular_time_minutes": 60,
                    "extra_time_minutes": 10,
                    "has_penalties": True
                },
                "advancement_logic": {
                    "teams_per_group_advancing": 3,
                    "has_best_thirds_table": False,
                    "best_third_placed_advancing": 0,
                    "has_runners_up_table": False,
                    "runners_up_advancing": 0,
                    "description": "Topp 3 från varje grupp (totalt 24 lag) avancerar till Mellanrundan (Main Round, 4 grupper om 6 lag). Topp 2 från varje Main Round-grupp (totalt 8 lag) avancerar till Kvartsfinaler."
                },
                "knockout_rules": {
                    "starting_round": "Quarterfinals",
                    "total_rounds": 3,
                    "has_penalties": True,
                    "has_third_place_match": True,
                    "extra_time_minutes": 10,
                    "tiebreaker_description": "Vid oavgjort i slutspel tillämpas 2x5 min förlängning, följt av 7-meterskastning (straffar). Match om 3:e pris spelas."
                },
                "official_rules_summary": "IHF World Championship: 32 lag i 8 grundomgångsgrupper (A–H, 48 matcher). De 3 bästa lagen per grupp avancerar med inbördes poäng till 4 Mellanrundegrupper (Main Round I–IV, 24 nya matcher). De två främsta per Main Round-grupp (8 lag) bildar slutspelsträdet från Kvartsfinaler till Bronsmatch och Final (8 matcher). Totalt 80 mästerskapsmatcher (exklusive Presidents Cup)."
            }

        # 7. Floorball World Championship (e.g. "2026 Men's World Floorball Championships", "Innebandy-VM")
        if "floorball" in sport_lower or "innebandy" in sport_lower or "iff" in t_lower:
            group_letters = ["A", "B", "C", "D"]
            groups_data = []
            for letter in group_letters:
                tier_label = "Toppdivision" if letter in ["A", "B"] else "Nedre division"
                groups_data.append({
                    "name": f"Group {letter} ({tier_label})",
                    "teams": [{"name": f"{letter}{idx} (TBD)", "code": f"{letter}{idx}", "is_placeholder": True} for idx in range(1, 5)]
                })

            return {
                "groups_count": 4,
                "teams_count": 16,
                "draw_completed": False,
                "groups": groups_data,
                "points_system": {"win": 2, "draw": 1, "loss": 0},
                "match_format": {
                    "regular_time_minutes": 60,
                    "extra_time_minutes": 10,
                    "has_penalties": True
                },
                "advancement_logic": {
                    "teams_per_group_advancing": 2,
                    "has_best_thirds_table": False,
                    "best_third_placed_advancing": 0,
                    "has_runners_up_table": False,
                    "runners_up_advancing": 0,
                    "description": "Grupp A & B (Toppdivision): 1:an och 2:an avancerar direkt till Kvartsfinaler. 3:an och 4:an spelar Play-off (Åttondelsfinaler). Grupp C & D (Nedre division): 1:an och 2:an spelar Play-off mot 3:or och 4:or från Grupp A & B om de sista 4 kvartsfinalplatserna."
                },
                "knockout_rules": {
                    "starting_round": "Play-off",
                    "total_rounds": 4,
                    "has_penalties": True,
                    "has_third_place_match": True,
                    "extra_time_minutes": 10,
                    "tiebreaker_description": "Vid oavgjort i slutspel spelas förlängning (10 min sudden death, 20 min i final) följt av straffläggning (5 straffar). Match om 3:e pris spelas."
                },
                "official_rules_summary": "IFF World Championship: 16 lag i 4 grupper om 4 lag (24 matcher). Topp 2 i Grupp A & B går direkt till Kvartsfinal. 3:or och 4:or i Grupp A & B möter 1:or och 2:or från Grupp C & D i Play-off (4 matcher). Vinnarna möter topplagen i Kvartsfinaler (4 matcher), följt av Semifinaler (2 matcher), Bronsmatch (1 match) och Final (1 match). Totalt 36 mästerskapsmatcher."
            }

        # 8. Continental Cups with 3rd Place Match (AFCON, Copa América, Asian Cup)
        if "africa cup of nations" in t_lower or "afcon" in t_lower or "copa am" in t_lower:
            return {
                "knockout_rules": {
                    "has_third_place_match": True,
                }
            }

        return None
