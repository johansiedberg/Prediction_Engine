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
import re
import datetime
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
    def _normalize_match_date(cls, raw_dt: Any, time_val: Any = None) -> Optional[str]:
        if not raw_dt:
            return None
        s = str(raw_dt).strip()
        if not s or s.lower() in ("none", "null", "tbd", "-", "undefined"):
            return None

        if time_val and str(time_val).strip() and str(time_val).strip() not in s:
            s = f"{s} {str(time_val).strip()}"

        import re
        if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
            return s
        if re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$', s):
            return s

        # Clean ordinal suffixes: 1st, 2nd, 3rd, 4th -> 1, 2, 3, 4 and " of "
        s_clean = re.sub(r'(\d+)(st|nd|rd|th)\b', r'\1', s, flags=re.IGNORECASE)
        s_clean = re.sub(r'\bof\b', ' ', s_clean, flags=re.IGNORECASE).strip()

        try:
            from dateutil import parser
            parsed = parser.parse(s_clean, fuzzy=True)
            has_time = any(c in s_clean for c in (':', 'am', 'pm', 'AM', 'PM', 'T'))
            if has_time and (parsed.hour != 0 or parsed.minute != 0 or ':' in s_clean):
                return parsed.strftime("%Y-%m-%d %H:%M")
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
            iso_p = LLMWikipediaScout._parse_date_string(s_clean)
            if iso_p:
                if time_val and ':' in str(time_val):
                    return f"{iso_p} {str(time_val).strip()}"
                return iso_p
            return s

    @classmethod
    def build_matches_knockout_segment(
        cls,
        audit_data: Optional[Dict[str, Any]] = None,
        groups_segment: Optional[GroupsAndTeamsSegment] = None,
        tournament_name: str = "",
        sport: str = "Football",
        tournament_meta: Optional[Dict[str, Any]] = None,
    ) -> MatchesAndKnockoutSegment:
        """
        Parses confirmed fixtures from audit data or leverages Gemini AI to research official match schedules & knockout trees
        using full tournament metadata and multi-sport intelligence.
        """
        audit = dict(audit_data or {})
        raw_fixtures = (
            audit.get("group_matches")
            or audit.get("fixtures")
            or audit.get("fixtures_sample")
            or []
        )
        raw_knockouts = (
            audit.get("knockout_bracket")
            or audit.get("knockout_stages")
            or []
        )
        raw_advancement = (
            audit.get("advancement_fixtures")
            or audit.get("knockout_mapping_sample")
            or []
        )

        # 0. Gemini AI Intelligence Enrichment
        # If the draw is not completed, or real teams are not confirmed, or if we ALREADY have
        # confirmed fixtures parsed from Wikipedia, skip querying Gemini to save 15-30s of latency.
        has_real_teams = bool(groups_segment and groups_segment.has_real_teams)
        is_draw_completed = bool(audit.get("draw_completed") and has_real_teams)
        already_has_fixtures = bool(raw_fixtures and len(raw_fixtures) >= 4)

        from tournament.services.gemini_scout_service import GeminiScoutService
        if GeminiScoutService.is_available() and tournament_name and is_draw_completed and not already_has_fixtures:
            try:
                gemini_matches = GeminiScoutService.scout_matches_and_knockout(
                    tournament_name=tournament_name,
                    sport=sport,
                    groups_data=[g.model_dump() for g in groups_segment.groups] if groups_segment else None,
                    wikipedia_context=str(audit.get("raw_text", ""))[:4000],
                    tournament_meta=tournament_meta,
                ) or {}

                g_fixtures = gemini_matches.get("group_matches") or gemini_matches.get("fixtures") or []
                if g_fixtures and (not raw_fixtures or len(raw_fixtures) < len(g_fixtures)):
                    raw_fixtures = g_fixtures
                    audit["fixtures"] = raw_fixtures
                    audit["group_matches"] = raw_fixtures

                g_knockouts = gemini_matches.get("knockout_bracket") or gemini_matches.get("knockout_stages") or []
                if g_knockouts and (not raw_knockouts or len(raw_knockouts) < len(g_knockouts)):
                    raw_knockouts = g_knockouts
                    audit["knockout_stages"] = raw_knockouts
                    audit["knockout_bracket"] = raw_knockouts

                g_adv = gemini_matches.get("advancement_fixtures") or gemini_matches.get("knockout_mapping_sample") or []
                if g_adv and (not raw_advancement or len(raw_advancement) < len(g_adv)):
                    raw_advancement = g_adv
                    audit["advancement_fixtures"] = raw_advancement

                if "fixtures_completed" in gemini_matches:
                    audit["fixtures_completed"] = gemini_matches["fixtures_completed"]
            except Exception as e:
                logger.warning("MatchesKnockoutAgent: Gemini matches scout error: %s", e)

        # Build team badge lookup cache from groups segment
        team_cache: Dict[str, Dict[str, Any]] = {}
        if groups_segment and groups_segment.groups:
            for g in groups_segment.groups:
                for t in g.teams:
                    team_cache[t.name.strip()] = {
                        "code": t.code or "",
                        "flag_url": t.flag_url or "",
                        "emblem_url": t.emblem_url or "",
                        "is_placeholder": t.is_placeholder,
                    }

        from tournament.services.team_badge_service import TeamBadgeService

        def _resolve_team_meta(name_str: str) -> Dict[str, Any]:
            if not name_str or not isinstance(name_str, str):
                return {"code": "", "flag_url": "", "emblem_url": "", "is_placeholder": True}
            clean = name_str.strip()
            if clean in team_cache:
                return team_cache[clean]

            # Instant 0ms check for bracket slots / match winners / placeholders
            if TeamBadgeService.is_placeholder(clean):
                ph_meta = {"code": "", "flag_url": "", "emblem_url": "", "is_placeholder": True}
                team_cache[clean] = ph_meta
                return ph_meta

            badge_res = TeamBadgeService.resolve_team_badge(
                clean, sport=sport, tournament_name=tournament_name, use_gemini_fallback=False
            )
            is_ph = badge_res.is_placeholder or TeamBadgeService.is_placeholder(clean)
            c_code = (badge_res.code or "").lower()
            f_url = badge_res.flag_url or (f"https://flagcdn.com/w40/{c_code}.png" if len(c_code) == 2 else "")
            meta = {
                "code": c_code,
                "flag_url": f_url,
                "emblem_url": badge_res.emblem_url or "",
                "is_placeholder": is_ph,
            }
            team_cache[clean] = meta
            return meta

        # 1. Group Matches vs Knockout Matches Separation
        group_matches: List[GroupMatchEntry] = []
        extra_knockout_matches: List[Dict[str, Any]] = []
        if raw_fixtures:
            for idx, f in enumerate(raw_fixtures, start=1):
                if isinstance(f, dict):
                    h_team = (f.get("home_team") or f.get("home") or "").strip()
                    a_team = (f.get("away_team") or f.get("away") or "").strip()
                    stage_raw = (f.get("stage_or_group") or f.get("group") or "Group Stage").strip()

                    # Filter out non-matches, empty opposing teams, or table rank artifacts (e.g. '4th', '6th', 'as Yugoslavia')
                    if not h_team or not a_team or h_team in ["–", "-", "—", "N/A", "TBD", "TBC"] and a_team in ["–", "-", "—", "N/A", "TBD", "TBC"]:
                        continue
                    if a_team in ["–", "-", "—", "N/A", ""]:
                        continue
                    if h_team in ["–", "-", "—", "N/A", ""]:
                        continue
                    if re.match(r'^\d+(?:st|nd|rd|th)$', h_team, re.I) or re.match(r'^\d+(?:st|nd|rd|th)$', a_team, re.I):
                        continue
                    if h_team.lower().startswith("as ") or a_team.lower().startswith("as "):
                        continue

                    # Sanitize stage name: remove non-match suffixes (criteria, ranking, seeding, tiebreakers, etc.)
                    stage_clean = re.sub(r'\s*-\s*(?:criteria.*|ranking.*|seeding.*|pots.*|tiebreaker.*|overview.*|format.*)$', '', stage_raw, flags=re.I).strip()
                    if not stage_clean:
                        stage_clean = "Group Stage"

                    # Detect if fixture is a knockout / playoff / bracket match
                    is_ko_stage = bool(re.search(r'\b(?:final|finals|semi|quarter|playoff|bracket|knockout|3rd\s*place|third\s*place|round\s*of\s*\d+)\b', stage_clean, re.I))
                    h_is_winner_ph = bool(re.search(r'\b(?:winner|loser|runner-up)\s+(?:match|m\d+|game|qf|sf)\b', h_team, re.I))
                    a_is_winner_ph = bool(re.search(r'\b(?:winner|loser|runner-up)\s+(?:match|m\d+|game|qf|sf)\b', a_team, re.I))

                    if is_ko_stage or h_is_winner_ph or a_is_winner_ph:
                        # Route bracket fixture to knockout list rather than group matches
                        extra_knockout_matches.append({
                            "stage": stage_clean,
                            "home_team": h_team,
                            "away_team": a_team,
                            "date_time": f.get("date_time") or f.get("date"),
                            "venue": f.get("venue") or "",
                        })
                        continue

                    h_meta = _resolve_team_meta(h_team)
                    a_meta = _resolve_team_meta(a_team)

                    h_code = str(f.get("home_team_code") or h_meta["code"]).lower()
                    h_flag = f.get("home_team_flag_url") or h_meta["flag_url"] or (f"https://flagcdn.com/w40/{h_code}.png" if len(h_code) == 2 else "")
                    a_code = str(f.get("away_team_code") or a_meta["code"]).lower()
                    a_flag = f.get("away_team_flag_url") or a_meta["flag_url"] or (f"https://flagcdn.com/w40/{a_code}.png" if len(a_code) == 2 else "")

                    dt_raw = f.get("date_time") or f.get("date")
                    dt_clean = cls._normalize_match_date(dt_raw, f.get("time"))

                    group_matches.append(GroupMatchEntry(
                        match_number=len(group_matches) + 1,
                        stage_or_group=stage_clean,
                        home_team=h_team,
                        away_team=a_team,
                        home_team_code=h_code,
                        home_team_flag_url=h_flag,
                        home_team_emblem_url=f.get("home_team_emblem_url") or h_meta["emblem_url"],
                        away_team_code=a_code,
                        away_team_flag_url=a_flag,
                        away_team_emblem_url=f.get("away_team_emblem_url") or a_meta["emblem_url"],
                        date_time=dt_clean,
                        venue=f.get("venue") or "",
                        is_placeholder=bool(f.get("is_placeholder", False)) or h_meta["is_placeholder"] or a_meta["is_placeholder"],
                    ))

        # Fallback: Generate round-robin match fixtures ONLY when draw is officially confirmed AND real groups exist
        can_generate_rr = bool(
            groups_segment
            and groups_segment.groups
            and groups_segment.has_real_teams
            and audit.get("draw_completed")
        )
        if not group_matches and can_generate_rr:
            match_num = 1
            for g in groups_segment.groups:
                t_list = g.teams
                n_teams = len(t_list)
                for i in range(n_teams):
                    for j in range(i + 1, n_teams):
                        h_team = t_list[i].name
                        a_team = t_list[j].name
                        h_meta = _resolve_team_meta(h_team)
                        a_meta = _resolve_team_meta(a_team)

                        h_code = str(t_list[i].code or h_meta["code"]).lower()
                        h_flag = t_list[i].flag_url or h_meta["flag_url"] or (f"https://flagcdn.com/w40/{h_code}.png" if len(h_code) == 2 else "")
                        a_code = str(t_list[j].code or a_meta["code"]).lower()
                        a_flag = t_list[j].flag_url or a_meta["flag_url"] or (f"https://flagcdn.com/w40/{a_code}.png" if len(a_code) == 2 else "")

                        group_matches.append(GroupMatchEntry(
                            match_number=match_num,
                            stage_or_group=g.name,
                            home_team=h_team,
                            away_team=a_team,
                            home_team_code=h_code,
                            home_team_flag_url=h_flag,
                            home_team_emblem_url=t_list[i].emblem_url or h_meta["emblem_url"],
                            away_team_code=a_code,
                            away_team_flag_url=a_flag,
                            away_team_emblem_url=t_list[j].emblem_url or a_meta["emblem_url"],
                            is_placeholder=t_list[i].is_placeholder or t_list[j].is_placeholder or h_meta["is_placeholder"] or a_meta["is_placeholder"],
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
                r_order = ks.get("round_order", r_idx) if isinstance(ks, dict) else r_idx

                match_entries: List[KnockoutMatchEntry] = []
                for m in m_list:
                    if isinstance(m, dict):
                        h_team = m.get("home_team") or m.get("home_source") or ""
                        a_team = m.get("away_team") or m.get("away_source") or ""
                        h_meta = _resolve_team_meta(h_team)
                        a_meta = _resolve_team_meta(a_team)

                        h_code = str(m.get("home_team_code") or h_meta["code"]).lower()
                        h_flag = m.get("home_team_flag_url") or h_meta["flag_url"] or (f"https://flagcdn.com/w40/{h_code}.png" if len(h_code) == 2 else "")
                        a_code = str(m.get("away_team_code") or a_meta["code"]).lower()
                        a_flag = m.get("away_team_flag_url") or a_meta["flag_url"] or (f"https://flagcdn.com/w40/{a_code}.png" if len(a_code) == 2 else "")

                        k_dt_raw = m.get("date_time") or m.get("date")
                        k_dt_clean = cls._normalize_match_date(k_dt_raw, m.get("time"))

                        match_entries.append(KnockoutMatchEntry(
                            match_code=m.get("match_code", ""),
                            stage_name=s_name,
                            home_team=h_team,
                            away_team=a_team,
                            home_team_code=h_code,
                            home_team_flag_url=h_flag,
                            home_team_emblem_url=m.get("home_team_emblem_url") or h_meta["emblem_url"],
                            away_team_code=a_code,
                            away_team_flag_url=a_flag,
                            away_team_emblem_url=m.get("away_team_emblem_url") or a_meta["emblem_url"],
                            winner_to=m.get("winner_to"),
                            date_time=k_dt_clean,
                            venue=m.get("venue", ""),
                        ))

                knockout_bracket.append(KnockoutStageEntry(
                    stage_name=s_name,
                    round_order=r_order,
                    matches=match_entries,
                ))

        # Fallback: Construct standard knockout stages if empty
        if not knockout_bracket:
            stages_to_add = ["Quarterfinals", "Semifinals", "Final"]
            if groups_segment and groups_segment.groups_count >= 6:
                stages_to_add = ["Round of 16", "Quarterfinals", "Semifinals", "Final"]
            elif groups_segment and groups_segment.groups_count >= 12:
                stages_to_add = ["Round of 32", "Round of 16", "Quarterfinals", "Semifinals", "Final"]

            for r_idx, s_name in enumerate(stages_to_add, start=1):
                knockout_bracket.append(KnockoutStageEntry(
                    stage_name=s_name,
                    round_order=r_idx,
                    matches=[],
                ))

        # Populate standard bracket placeholder matches if stages are empty
        for stage in knockout_bracket:
            s_name_lower = stage.stage_name.lower()
            if not stage.matches:
                match_entries: List[KnockoutMatchEntry] = []
                if "round of 32" in s_name_lower:
                    for m_idx in range(1, 17):
                        match_entries.append(KnockoutMatchEntry(
                            match_code=f"R32_{m_idx}",
                            stage_name=stage.stage_name,
                            home_team=f"Lag #{m_idx * 2 - 1}",
                            away_team=f"Lag #{m_idx * 2}",
                            winner_to=f"R16_{(m_idx + 1) // 2}",
                        ))
                elif "round of 16" in s_name_lower or "åttondels" in s_name_lower:
                    group_letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
                    for m_idx in range(1, 9):
                        h_src = f"1{group_letters[(m_idx - 1) % len(group_letters)]}" if m_idx <= len(group_letters) else f"Vinnare M{m_idx}"
                        a_src = f"2{group_letters[m_idx % len(group_letters)]}" if m_idx < len(group_letters) else "3:a Grupp"
                        match_entries.append(KnockoutMatchEntry(
                            match_code=f"R16_{m_idx}",
                            stage_name=stage.stage_name,
                            home_team=h_src,
                            away_team=a_src,
                            winner_to=f"QF_{(m_idx + 1) // 2}",
                        ))
                elif "quarter" in s_name_lower or "kvart" in s_name_lower:
                    for m_idx in range(1, 5):
                        match_entries.append(KnockoutMatchEntry(
                            match_code=f"QF_{m_idx}",
                            stage_name=stage.stage_name,
                            home_team=f"Vinnare R16_{m_idx * 2 - 1}",
                            away_team=f"Vinnare R16_{m_idx * 2}",
                            winner_to=f"SF_{(m_idx + 1) // 2}",
                        ))
                elif "semi" in s_name_lower:
                    for m_idx in range(1, 3):
                        match_entries.append(KnockoutMatchEntry(
                            match_code=f"SF_{m_idx}",
                            stage_name=stage.stage_name,
                            home_team=f"Vinnare QF_{m_idx * 2 - 1}",
                            away_team=f"Vinnare QF_{m_idx * 2}",
                            winner_to="Final",
                        ))
                elif "final" in s_name_lower:
                    match_entries.append(KnockoutMatchEntry(
                        match_code="FINAL",
                        stage_name=stage.stage_name,
                        home_team="Vinnare SF_1",
                        away_team="Vinnare SF_2",
                        winner_to="Guld / Mästare",
                    ))
                stage.matches = match_entries

        has_real_teams = bool(groups_segment and groups_segment.has_real_teams)
        draw_is_done = bool(
            (audit.get("draw_completed") or has_real_teams)
            and has_real_teams
        )
        fixtures_completed = bool(
            draw_is_done
            and group_matches
            and not any(m.is_placeholder for m in group_matches)
        )

        # Calculate theoretical matches if fixtures are just a sample
        theoretical_group_matches = 0
        if groups_segment and not fixtures_completed:
            for g in groups_segment.groups:
                t_count = len(g.teams)
                if t_count >= 2:
                    # Assume double round-robin for large qualifiers (like Euro/World Cup) if long duration, else single
                    # Default to single round robin math for placeholders to be safe, but at least it won't be '6'
                    theoretical_group_matches += (t_count * (t_count - 1)) // 2

        actual_listed_matches = len(group_matches) + sum(len(stage.matches) for stage in knockout_bracket)
        total_matches_count = max(actual_listed_matches, theoretical_group_matches + sum(len(stage.matches) for stage in knockout_bracket))

        return MatchesAndKnockoutSegment(
            total_matches=total_matches_count,
            fixtures_completed=fixtures_completed,
            group_matches=group_matches,
            advancement_fixtures=advancement_fixtures,
            knockout_bracket=knockout_bracket,
        )
