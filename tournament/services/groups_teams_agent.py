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
import re
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
        tournament_name: str = "",
        sport: str = "Football",
    ) -> GroupsAndTeamsSegment:
        """
        Extracts real group compositions or leverages Gemini AI to research official groups/teams.
        """
        audit = dict(audit_data or {})
        raw_groups = audit.get("groups") or []
        # 0. Fixtures Fallback: Reconstruct groups from audited match fixtures if available
        fixtures = audit.get("fixtures") or audit.get("group_matches") or audit.get("fixtures_sample") or []
        from tournament.services.scout_service import has_real_teams as check_real_teams
        prior_has_real = check_real_teams(raw_groups) if raw_groups else False

        if fixtures and (not raw_groups or not prior_has_real):
            from tournament.services.team_badge_service import TeamBadgeService
            fixtures_by_group: Dict[str, List[str]] = {}
            for f in fixtures:
                if isinstance(f, dict):
                    g_name = (f.get("stage_or_group") or "Group A").strip()
                    # Only consider actual group/pool stages, not knockout stages
                    if re.search(r'\b(?:final|semi|quarter|round\s+of|playoff|bracket|knockout|3rd\s+place|third\s+place)\b', g_name, re.I):
                        continue
                    h = (f.get("home_team") or f.get("home") or "").strip()
                    a = (f.get("away_team") or f.get("away") or "").strip()
                    if g_name not in fixtures_by_group:
                        fixtures_by_group[g_name] = []
                    if h and not TeamBadgeService.is_placeholder(h) and h not in fixtures_by_group[g_name]:
                        fixtures_by_group[g_name].append(h)
                    if a and not TeamBadgeService.is_placeholder(a) and a not in fixtures_by_group[g_name]:
                        fixtures_by_group[g_name].append(a)

            total_real_in_fixtures = sum(len(teams) for teams in fixtures_by_group.values())
            if total_real_in_fixtures >= 4 and len(fixtures_by_group) >= 1:
                extracted_groups = []
                for g_n, t_list in fixtures_by_group.items():
                    extracted_groups.append({
                        "name": g_n,
                        "teams": [{"name": t_name} for t_name in t_list]
                    })
                raw_groups = extracted_groups
                prior_has_real = True
                audit["groups"] = raw_groups

        bp = audit.get("tournament_blueprint") or {}
        prior_draw_completed = bool(audit.get("draw_completed") or bp.get("draw_completed"))
        is_empty_prospect = (audit.get("teams_count") == 0 and audit.get("groups_count") == 0 and not raw_groups)

        from tournament.services.format_blueprint_service import FormatBlueprintService
        canon_bp = FormatBlueprintService.get_canonical_blueprint(tournament_name, sport)
        if canon_bp and canon_bp.get("groups") and (not raw_groups or not prior_has_real):
            raw_groups = canon_bp["groups"]
            audit["groups"] = raw_groups
            if "draw_completed" in canon_bp:
                audit["draw_completed"] = canon_bp["draw_completed"]

        is_draw_completed = audit.get("draw_completed", True)
        
        from tournament.services.gemini_scout_service import GeminiScoutService
        if GeminiScoutService.is_available() and tournament_name and not is_empty_prospect and is_draw_completed:
            try:
                gemini_groups = GeminiScoutService.scout_groups_and_teams(
                    tournament_name=tournament_name,
                    sport=sport,
                    wikipedia_context=str(audit.get("raw_text", ""))[:4000],
                ) or {}
                if gemini_groups.get("groups"):
                    if not raw_groups or (not prior_has_real and gemini_groups.get("has_real_teams")) or (len(raw_groups) < len(gemini_groups["groups"]) and not prior_has_real):
                        raw_groups = gemini_groups["groups"]
                        audit["groups"] = raw_groups
                if "draw_completed" in gemini_groups:
                    if not prior_draw_completed and not prior_has_real:
                        audit["draw_completed"] = gemini_groups["draw_completed"]
                if gemini_groups.get("draw_date") and not audit.get("draw_date"):
                    audit["draw_date"] = gemini_groups["draw_date"]
            except Exception as e:
                logger.warning("GroupsTeamsAgent: Gemini groups scout error: %s", e)

        parsed_groups: List[GroupEntry] = []
        real_teams_found = 0
        total_teams_count = 0

        if raw_groups:
            from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
            from tournament.services.team_badge_service import TeamBadgeService

            # Check if preliminary groups (Group A-F) exist and have real teams
            has_letters_past_i = any(bool(re.match(r'^(?:Group|Pool|Division)\s+[J-Z]$', (g.get("name") if isinstance(g, dict) else str(g)).strip(), re.I)) for g in raw_groups)
            has_roman_ii = any(bool(re.match(r'^(?:Group|Pool)\s+(?:II|III|IV)\b', (g.get("name") if isinstance(g, dict) else str(g)).strip(), re.I)) for g in raw_groups)

            if has_roman_ii and not has_letters_past_i:
                # If roman numeral groups exist (e.g. Handball Main Round Group I, Group II) alongside prelim groups, exclude them
                filtered_raw_groups = [
                    g for g in raw_groups
                    if not re.match(r'^(?:Group|Pool)\s+(?:I|II|III|IV|V|VI)\b', (g.get("name") if isinstance(g, dict) else str(g)).strip(), re.I)
                ]
                if filtered_raw_groups:
                    raw_groups = filtered_raw_groups

            for g in raw_groups:
                g_name = g.get("name") if isinstance(g, dict) else str(g)
                if re.search(r'\b(?:final|semi|quarter|round\s+of|playoff|bracket|knockout|3rd\s+place|third\s+place)\b', g_name, re.I):
                    continue
                raw_team_list = g.get("teams", []) if isinstance(g, dict) else []

                team_entries: List[TeamEntry] = []
                seen_in_group = set()
                for t in raw_team_list:
                    raw_t_name = t.get("name") if isinstance(t, dict) else str(t)
                    t_name = LLMWikipediaScout._clean_team_name(raw_t_name)
                    if not t_name:
                        continue

                    # Deduplicate teams within the same group
                    norm_t = t_name.lower().strip()
                    if norm_t in seen_in_group:
                        continue
                    seen_in_group.add(norm_t)

                    t_code = t.get("code", "") if isinstance(t, dict) else ""
                    t_seed = t.get("seed", "") if isinstance(t, dict) else ""
                    t_flag_url = t.get("flag_url", "") if isinstance(t, dict) else ""
                    t_emblem_url = t.get("emblem_url", "") if isinstance(t, dict) else ""

                    badge_res = TeamBadgeService.resolve_team_badge(
                        t_name, sport=sport, tournament_name=tournament_name, use_gemini_fallback=False
                    )
                    is_ph = badge_res.is_placeholder or cls.is_placeholder_team(t_name)

                    if not is_ph:
                        real_teams_found += 1

                    team_entries.append(TeamEntry(
                        name=t_name,
                        code=t_code or badge_res.code or (t_name[:3].upper() if len(t_name) >= 3 else t_name.upper()),
                        is_placeholder=is_ph,
                        seed=t_seed or None,
                        flag_url=t_flag_url or badge_res.flag_url or "",
                        emblem_url=t_emblem_url or badge_res.emblem_url or "",
                    ))

                total_teams_count += len(team_entries)
                parsed_groups.append(GroupEntry(
                    name=g_name,
                    teams_count=len(team_entries) or 4,
                    teams=team_entries,
                    advancement_description=g.get("advancement_description", "") if isinstance(g, dict) else "",
                ))

        # Fallback: Generate skeleton placeholder groups if empty and prospect is not explicitly empty
        if not parsed_groups and audit.get("teams_count") != 0 and audit.get("groups_count") != 0:
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

        # Real teams require that groups have authentic structure (not 1 gigantic un-drawn list of qualified nations)
        is_flat_qualified_list = len(parsed_groups) == 1 and total_teams_count > 8
        has_real_teams = (not is_flat_qualified_list) and (real_teams_found >= max(4, total_teams_count // 2))

        return GroupsAndTeamsSegment(
            groups_count=len(parsed_groups),
            teams_count=total_teams_count,
            has_real_teams=has_real_teams,
            groups=parsed_groups,
        )
