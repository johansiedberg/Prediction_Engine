"""
Segment 5: Matches & Knockout Agent
===================================
Agnostic Deepscan Agent that parses fixtures, advancement formulas, and knockout trees:
- Group stage fixtures (Match #, Home team, Away team, Date/Time, Venue)
- Advancement pathway rules (e.g. 'Winner Group A vs 3rd Group C/D')
- Multi-round knockout bracket generation (Round of 32 -> Round of 16 -> QF -> SF -> Final)
- Fixture completeness checks
"""

import logging
from typing import Optional, Dict, Any, List

from tournament.schemas.tournament_prospect_schema import (
    MatchesAndKnockoutSegment,
    GroupMatchEntry,
    AdvancementFixtureEntry,
    KnockoutStageEntry,
    KnockoutMatchEntry,
    GroupsAndTeamsSegment,
)

logger = logging.getLogger(__name__)


class MatchesKnockoutAgent:
    """
    Agnostic Agent responsible for match schedules, fixture generation, and knockout brackets.
    """

    STANDARD_ROUNDS = [
        "Round of 32",
        "Round of 16",
        "Quarterfinals",
        "Semifinals",
        "Third Place Playoff",
        "Final",
    ]

    @classmethod
    def build_matches_knockout_segment(
        cls,
        audit_data: Optional[Dict[str, Any]] = None,
        groups_segment: Optional[GroupsAndTeamsSegment] = None,
        tournament_name: str = "",
        sport: str = "Football",
    ) -> MatchesAndKnockoutSegment:
        """
        Parses confirmed fixtures from audit data or leverages Gemini AI to research official match schedules & knockout trees.
        """
        audit = dict(audit_data or {})
        raw_fixtures = audit.get("fixtures") or audit.get("fixtures_sample") or []
        raw_knockouts = audit.get("knockout_stages") or []
        raw_advancement = audit.get("knockout_mapping_sample") or []

        # 0. Gemini AI Intelligence Enrichment
        from tournament.services.gemini_scout_service import GeminiScoutService
        if GeminiScoutService.is_available() and tournament_name and (not raw_fixtures or not raw_knockouts):
            try:
                gemini_matches = GeminiScoutService.scout_matches_and_knockout(
                    tournament_name=tournament_name,
                    sport=sport,
                    groups_data=[g.model_dump() for g in groups_segment.groups] if groups_segment else None,
                    wikipedia_context=str(audit.get("raw_text", ""))[:4000],
                )
                if gemini_matches:
                    if not raw_fixtures and gemini_matches.get("fixtures"):
                        raw_fixtures = gemini_matches["fixtures"]
                        audit["fixtures"] = raw_fixtures
                    if not raw_knockouts and gemini_matches.get("knockout_stages"):
                        raw_knockouts = gemini_matches["knockout_stages"]
                        audit["knockout_stages"] = raw_knockouts
                    if "fixtures_completed" in gemini_matches:
                        audit["fixtures_completed"] = gemini_matches["fixtures_completed"]
            except Exception as e:
                logger.warning("MatchesKnockoutAgent: Gemini matches scout error: %s", e)

        # 1. Group Matches Parsing
        group_matches: List[GroupMatchEntry] = []
        if raw_fixtures:
            for idx, f in enumerate(raw_fixtures, start=1):
                if isinstance(f, dict):
                    group_matches.append(GroupMatchEntry(
                        match_number=f.get("match_number", idx),
                        stage_or_group=f.get("stage_or_group") or f.get("group") or "Group Stage",
                        home_team=f.get("home_team") or f.get("home") or "",
                        away_team=f.get("away_team") or f.get("away") or "",
                        date_time=f.get("date_time") or f.get("date"),
                        venue=f.get("venue") or "",
                        is_placeholder=bool(f.get("is_placeholder", False)),
                    ))

        # Fallback: Generate round-robin match fixtures from groups if fixtures empty
        if not group_matches and groups_segment and groups_segment.groups:
            match_num = 1
            for g in groups_segment.groups:
                t_list = g.teams
                n_teams = len(t_list)
                for i in range(n_teams):
                    for j in range(i + 1, n_teams):
                        group_matches.append(GroupMatchEntry(
                            match_number=match_num,
                            stage_or_group=g.name,
                            home_team=t_list[i].name,
                            away_team=t_list[j].name,
                            is_placeholder=t_list[i].is_placeholder or t_list[j].is_placeholder,
                        ))
                        match_num += 1

        # 2. Advancement Fixtures
        advancement_fixtures: List[AdvancementFixtureEntry] = []
        if raw_advancement:
            for adv in raw_advancement:
                if isinstance(adv, dict):
                    advancement_fixtures.append(AdvancementFixtureEntry(
                        match_code=adv.get("match_code", ""),
                        stage_name=adv.get("stage") or adv.get("stage_name") or "Slutspel",
                        source_home=adv.get("home_placeholder") or adv.get("source_home") or "",
                        source_away=adv.get("away_placeholder") or adv.get("source_away") or "",
                    ))

        # 3. Knockout Bracket Tree
        knockout_bracket: List[KnockoutStageEntry] = []
        if raw_knockouts:
            for r_idx, ks in enumerate(raw_knockouts, start=1):
                s_name = ks.get("stage_name") if isinstance(ks, dict) else str(ks)
                m_list = ks.get("matches", []) if isinstance(ks, dict) else []

                match_entries: List[KnockoutMatchEntry] = []
                for m in m_list:
                    if isinstance(m, dict):
                        match_entries.append(KnockoutMatchEntry(
                            match_code=m.get("match_code", ""),
                            stage_name=s_name,
                            home_team=m.get("home_team") or m.get("home_source") or "",
                            away_team=m.get("away_team") or m.get("away_source") or "",
                            winner_to=m.get("winner_to"),
                            date_time=m.get("date_time"),
                            venue=m.get("venue", ""),
                        ))

                knockout_bracket.append(KnockoutStageEntry(
                    stage_name=s_name,
                    round_order=r_idx,
                    matches=match_entries,
                ))

        # Fallback: Construct standard knockout stages if empty
        if not knockout_bracket:
            stages_to_add = ["Quarterfinals", "Semifinals", "Final"]
            if groups_segment and groups_segment.groups_count >= 8:
                stages_to_add = ["Round of 16", "Quarterfinals", "Semifinals", "Final"]
            elif groups_segment and groups_segment.groups_count >= 12:
                stages_to_add = ["Round of 32", "Round of 16", "Quarterfinals", "Semifinals", "Final"]

            for r_idx, s_name in enumerate(stages_to_add, start=1):
                knockout_bracket.append(KnockoutStageEntry(
                    stage_name=s_name,
                    round_order=r_idx,
                    matches=[],
                ))

        fixtures_completed = bool(
            group_matches and not any(m.is_placeholder for m in group_matches)
        )

        return MatchesAndKnockoutSegment(
            total_matches=len(group_matches),
            fixtures_completed=fixtures_completed,
            group_matches=group_matches,
            advancement_fixtures=advancement_fixtures,
            knockout_bracket=knockout_bracket,
        )
