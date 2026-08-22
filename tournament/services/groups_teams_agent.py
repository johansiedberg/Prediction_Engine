"""
Segment 4: Groups & Teams Agent
===============================
Agnostic Deepscan Agent that parses and constructs group matrices and team rosters:
- Group designations (e.g. Group A, Group B, Main Round)
- Real qualified teams vs Placeholder entries (e.g. 'A1 (TBD)', 'Playoff Winner')
- Country ISO codes and flag emojis
- Seeding pots and group counts
- Automatic skeleton group generation when draw is pending
"""

import logging
from typing import Optional, Dict, Any, List

from tournament.schemas.tournament_prospect_schema import (
    GroupsAndTeamsSegment,
    GroupEntry,
    TeamEntry,
)

logger = logging.getLogger(__name__)


class GroupsTeamsAgent:
    """
    Agnostic Agent responsible for resolving group stage matrices and team entries.
    """

    @classmethod
    def is_placeholder_team(cls, name: str) -> bool:
        """Determines if a team name is a placeholder rather than a confirmed team."""
        if not name:
            return True
        n = name.strip().lower()
        placeholder_tokens = [
            "tbd", "placeholder", "winner", "runner-up", "pot ", "seed ",
            "group ", "play-off", "playoff", "to be determined", "path a", "path b", "path c",
            "a1", "a2", "a3", "a4", "b1", "b2", "b3", "b4",
            "c1", "c2", "c3", "c4", "d1", "d2", "d3", "d4",
            "e1", "e2", "e3", "e4", "f1", "f2", "f3", "f4",
        ]
        if len(n) <= 3 and any(char.isdigit() for char in n):
            return True
        for token in placeholder_tokens:
            if token in n:
                return True
        return False

    @classmethod
    def build_groups_teams_segment(
        cls,
        audit_data: Optional[Dict[str, Any]] = None,
        default_groups_count: int = 4,
        teams_per_group: int = 4,
    ) -> GroupsAndTeamsSegment:
        """
        Extracts real group compositions or generates skeleton placeholders.
        """
        audit = audit_data or {}
        raw_groups = audit.get("groups") or []
        bp = audit.get("tournament_blueprint") or {}

        parsed_groups: List[GroupEntry] = []
        real_teams_found = 0
        total_teams_count = 0

        if raw_groups:
            for g in raw_groups:
                g_name = g.get("name") if isinstance(g, dict) else str(g)
                raw_team_list = g.get("teams", []) if isinstance(g, dict) else []

                team_entries: List[TeamEntry] = []
                for t in raw_team_list:
                    t_name = t.get("name") if isinstance(t, dict) else str(t)
                    t_code = t.get("code", "") if isinstance(t, dict) else ""
                    t_seed = t.get("seed", "") if isinstance(t, dict) else ""
                    is_ph = cls.is_placeholder_team(t_name)

                    if not is_ph:
                        real_teams_found += 1

                    team_entries.append(TeamEntry(
                        name=t_name,
                        code=t_code or (t_name[:3].upper() if len(t_name) >= 3 else t_name.upper()),
                        is_placeholder=is_ph,
                        seed=t_seed or None,
                    ))

                total_teams_count += len(team_entries)
                parsed_groups.append(GroupEntry(
                    name=g_name,
                    teams_count=len(team_entries) or 4,
                    teams=team_entries,
                    advancement_description=g.get("advancement_description", "") if isinstance(g, dict) else "",
                ))

        # Fallback: Generate skeleton placeholder groups if empty
        if not parsed_groups:
            g_count = audit.get("groups_count") or bp.get("groups_count") or default_groups_count
            group_letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]

            for i in range(min(g_count, len(group_letters))):
                letter = group_letters[i]
                g_name = f"Group {letter}"
                team_entries = [
                    TeamEntry(name=f"{letter}{j} (TBD)", code=f"{letter}{j}", is_placeholder=True, seed=f"{letter}{j}")
                    for j in range(1, teams_per_group + 1)
                ]
                total_teams_count += len(team_entries)
                parsed_groups.append(GroupEntry(
                    name=g_name,
                    teams_count=len(team_entries),
                    teams=team_entries,
                    advancement_description=f"Topp 2 i {g_name} avancerar.",
                ))

        has_real_teams = real_teams_found >= max(4, total_teams_count // 2)

        return GroupsAndTeamsSegment(
            groups_count=len(parsed_groups),
            teams_count=total_teams_count,
            has_real_teams=has_real_teams,
            groups=parsed_groups,
        )
