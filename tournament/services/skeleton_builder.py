"""
Skeleton Builder Service
========================
Generates mathematical placeholders for tournament trees (e.g. 'Winner Group A vs Runner-up Group B')
and empty group structures based on the extracted TournamentSetup blueprint.
Allows the frontend to render the complete tournament structure and bracket tree before actual teams are assigned.
"""

import logging
from typing import Dict, List, Any, Optional

from tournament.schemas.tournament_blueprint import (
    TournamentSetup,
    GroupStructure,
    KnockoutStructure,
    KnockoutMatchPlaceholder,
)

logger = logging.getLogger(__name__)


class SkeletonBuilder:
    """
    Takes a TournamentSetup blueprint (or raw dictionary/ScannedTournament blueprint)
    and constructs placeholder structures for group stages and knockout brackets.
    """

    def __init__(self, blueprint: TournamentSetup | Dict[str, Any] | None = None):
        if isinstance(blueprint, dict):
            try:
                self.blueprint = TournamentSetup.model_validate(blueprint)
            except Exception as e:
                logger.warning("SkeletonBuilder: Failed to validate blueprint dict: %s", e)
                self.blueprint = TournamentSetup(tournament_name="Unknown")
        elif isinstance(blueprint, TournamentSetup):
            self.blueprint = blueprint
        else:
            self.blueprint = TournamentSetup(tournament_name="Unknown")

    def generate_group_placeholders(self) -> List[Dict[str, Any]]:
        """
        Generates group stage structures with placeholder team codes (e.g. 'A1', 'A2')
        if actual teams are not yet assigned.
        """
        result_groups = []
        existing_groups = self.blueprint.groups or []

        if existing_groups:
            for g in existing_groups:
                name = g.name
                teams = list(g.teams)
                count = g.teams_count or max(len(teams), 4)

                # Fill remaining team slots with placeholders if empty
                prefix = name.split()[-1] if ' ' in name else name[:1]
                while len(teams) < count:
                    idx = len(teams) + 1
                    teams.append(f"{prefix}{idx}")

                result_groups.append({
                    "name": name,
                    "teams_count": count,
                    "teams": teams,
                    "advancement_description": g.advancement_description or ""
                })
        else:
            # Generate default groups based on groups_count
            g_count = self.blueprint.groups_count or 4
            for i in range(g_count):
                g_char = chr(65 + i)
                name = f"Group {g_char}"
                teams = [f"{g_char}1", f"{g_char}2", f"{g_char}3", f"{g_char}4"]
                result_groups.append({
                    "name": name,
                    "teams_count": 4,
                    "teams": teams,
                    "advancement_description": "Top 2 teams advance to knockout stage"
                })

        return result_groups

    def generate_knockout_placeholders(self) -> List[Dict[str, Any]]:
        """
        Generates mathematical placeholders for the knockout bracket tree.
        Supports standard group-to-knockout mappings for 2, 4, 8, or 12/16 groups.
        """
        groups = self.blueprint.groups or []
        num_groups = len(groups) or self.blueprint.groups_count or 4
        group_letters = [
            g.name.split()[-1] if ' ' in g.name else chr(65 + i)
            for i, g in enumerate(groups)
        ] if groups else [chr(65 + i) for i in range(num_groups)]

        stages: List[Dict[str, Any]] = []

        if num_groups >= 12:
            # 12 groups (A-L): 32 teams advance -> Round of 32 -> R16 -> QF -> SF -> Final
            r32_matches = []
            for i in range(16):
                m_num = i + 1
                if i < 12:
                    g_char = group_letters[i] if i < len(group_letters) else chr(65 + i)
                    home_s = f"Winner Group {g_char}"
                    away_s = f"Best 3rd / Runner-up Group {chr(65 + (i+1)%12)}"
                else:
                    g_char = group_letters[i - 12] if (i - 12) < len(group_letters) else chr(65 + (i - 12))
                    home_s = f"Runner-up Group {g_char}"
                    away_s = f"Runner-up Group {chr(65 + (i-11)%12)}"
                r32_matches.append({
                    "match_code": f"R32_{m_num}",
                    "stage_name": "Round of 32",
                    "home_source": home_s,
                    "away_source": away_s
                })
            stages.append({"stage_name": "Round of 32", "match_count": 16, "matches": r32_matches})

            # Round of 16
            r16_matches = []
            for i in range(8):
                m1 = f"R32_{i*2+1}"
                m2 = f"R32_{i*2+2}"
                r16_matches.append({
                    "match_code": f"R16_{i+1}",
                    "stage_name": "Round of 16",
                    "home_source": f"Winner {m1}",
                    "away_source": f"Winner {m2}"
                })
            stages.append({"stage_name": "Round of 16", "match_count": 8, "matches": r16_matches})

            # Quarterfinals
            qf_matches = []
            for i in range(4):
                m1 = f"R16_{i*2+1}"
                m2 = f"R16_{i*2+2}"
                qf_matches.append({
                    "match_code": f"QF_{i+1}",
                    "stage_name": "Quarterfinals",
                    "home_source": f"Winner {m1}",
                    "away_source": f"Winner {m2}"
                })
            stages.append({"stage_name": "Quarterfinals", "match_count": 4, "matches": qf_matches})

            # Semifinals
            sf_matches = [
                {"match_code": "SF_1", "stage_name": "Semifinals", "home_source": "Winner QF_1", "away_source": "Winner QF_2"},
                {"match_code": "SF_2", "stage_name": "Semifinals", "home_source": "Winner QF_3", "away_source": "Winner QF_4"},
            ]
            stages.append({"stage_name": "Semifinals", "match_count": 2, "matches": sf_matches})

            # Finals
            final_matches = [
                {"match_code": "3RD_PLACE", "stage_name": "Third place play-off", "home_source": "Loser SF_1", "away_source": "Loser SF_2"},
                {"match_code": "FINAL", "stage_name": "Final", "home_source": "Winner SF_1", "away_source": "Winner SF_2"},
            ]
            stages.append({"stage_name": "Finals", "match_count": 2, "matches": final_matches})

        elif num_groups >= 6:
            # 6 to 11 groups (e.g. A-F, A-H): 16 teams advance -> R16 -> QF -> SF -> Final
            r16_matches = []
            for i in range(4):
                g1 = group_letters[i * 2 % len(group_letters)]
                g2 = group_letters[(i * 2 + 1) % len(group_letters)]
                r16_matches.append({
                    "match_code": f"R16_{i*2+1}",
                    "stage_name": "Round of 16",
                    "home_source": f"Winner Group {g1}",
                    "away_source": f"Runner-up / 3rd Group {g2}"
                })
                r16_matches.append({
                    "match_code": f"R16_{i*2+2}",
                    "stage_name": "Round of 16",
                    "home_source": f"Winner Group {g2}",
                    "away_source": f"Runner-up / 3rd Group {g1}"
                })
            stages.append({"stage_name": "Round of 16", "match_count": 8, "matches": r16_matches})

            # Quarterfinals
            qf_matches = []
            for i in range(4):
                m1_code = f"R16_{i*2+1}"
                m2_code = f"R16_{i*2+2}"
                qf_matches.append({
                    "match_code": f"QF_{i+1}",
                    "stage_name": "Quarterfinals",
                    "home_source": f"Winner {m1_code}",
                    "away_source": f"Winner {m2_code}"
                })
            stages.append({"stage_name": "Quarterfinals", "match_count": 4, "matches": qf_matches})

            # Semifinals
            sf_matches = [
                {"match_code": "SF_1", "stage_name": "Semifinals", "home_source": "Winner QF_1", "away_source": "Winner QF_2"},
                {"match_code": "SF_2", "stage_name": "Semifinals", "home_source": "Winner QF_3", "away_source": "Winner QF_4"},
            ]
            stages.append({"stage_name": "Semifinals", "match_count": 2, "matches": sf_matches})

            # Finals
            final_matches = [
                {"match_code": "3RD_PLACE", "stage_name": "Third place play-off", "home_source": "Loser SF_1", "away_source": "Loser SF_2"},
                {"match_code": "FINAL", "stage_name": "Final", "home_source": "Winner SF_1", "away_source": "Winner SF_2"},
            ]
            stages.append({"stage_name": "Finals", "match_count": 2, "matches": final_matches})

        elif num_groups >= 3:
            # 3 to 5 groups (A-D): 8 teams advance -> QF -> SF -> Final
            qf_matches = []
            for i in range(2):
                g1 = group_letters[i * 2 % len(group_letters)]
                g2 = group_letters[(i * 2 + 1) % len(group_letters)]
                qf_matches.append({
                    "match_code": f"QF_{i*2+1}",
                    "stage_name": "Quarterfinals",
                    "home_source": f"Winner Group {g1}",
                    "away_source": f"Runner-up Group {g2}"
                })
                qf_matches.append({
                    "match_code": f"QF_{i*2+2}",
                    "stage_name": "Quarterfinals",
                    "home_source": f"Winner Group {g2}",
                    "away_source": f"Runner-up Group {g1}"
                })
            stages.append({"stage_name": "Quarterfinals", "match_count": 4, "matches": qf_matches})

            # Semifinals
            sf_matches = [
                {"match_code": "SF_1", "stage_name": "Semifinals", "home_source": "Winner QF_1", "away_source": "Winner QF_2"},
                {"match_code": "SF_2", "stage_name": "Semifinals", "home_source": "Winner QF_3", "away_source": "Winner QF_4"},
            ]
            stages.append({"stage_name": "Semifinals", "match_count": 2, "matches": sf_matches})

            # Finals
            final_matches = [
                {"match_code": "3RD_PLACE", "stage_name": "Third place play-off", "home_source": "Loser SF_1", "away_source": "Loser SF_2"},
                {"match_code": "FINAL", "stage_name": "Final", "home_source": "Winner SF_1", "away_source": "Winner SF_2"},
            ]
            stages.append({"stage_name": "Finals", "match_count": 2, "matches": final_matches})

        else:
            # 1 to 2 groups (A-B): 4 teams advance -> SF -> Final
            g1 = group_letters[0] if group_letters else "A"
            g2 = group_letters[1] if len(group_letters) > 1 else "B"
            sf_matches = [
                {"match_code": "SF_1", "stage_name": "Semifinals", "home_source": f"Winner Group {g1}", "away_source": f"Runner-up Group {g2}"},
                {"match_code": "SF_2", "stage_name": "Semifinals", "home_source": f"Winner Group {g2}", "away_source": f"Runner-up Group {g1}"},
            ]
            stages.append({"stage_name": "Semifinals", "match_count": 2, "matches": sf_matches})

            final_matches = [
                {"match_code": "3RD_PLACE", "stage_name": "Third place play-off", "home_source": "Loser SF_1", "away_source": "Loser SF_2"},
                {"match_code": "FINAL", "stage_name": "Final", "home_source": "Winner SF_1", "away_source": "Winner SF_2"},
            ]
            stages.append({"stage_name": "Finals", "match_count": 2, "matches": final_matches})

        return stages

    def build_skeleton(self) -> Dict[str, Any]:
        """
        Builds the complete skeleton representation containing group stage and
        knockout bracket placeholders.
        """
        groups = self.generate_group_placeholders()
        knockout = self.generate_knockout_placeholders()

        return {
            "tournament_name": self.blueprint.tournament_name,
            "sport": self.blueprint.sport,
            "teams_count": self.blueprint.teams_count or sum(len(g["teams"]) for g in groups),
            "groups_count": len(groups),
            "groups": groups,
            "knockout_tree": knockout,
            "tiebreaker_hierarchy": [tb.value for tb in self.blueprint.tiebreaker_hierarchy],
            "official_rules_summary": self.blueprint.official_rules_summary or "",
        }
