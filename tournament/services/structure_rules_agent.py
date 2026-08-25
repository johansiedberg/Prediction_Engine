"""
Segment 3: Structure & Rules Agent
==================================
Agnostic Deepscan Agent that parses semantic competition regulations and point rules:
- General setup (draw date, draw completed status, seeding pots, host auto-placements)
- Group stage points (W/D/L, suspensions)
- Group tiebreaker rank hierarchies (H2H, Goal Diff, Goals scored, Fair play)
- Secondary Qualifying Tables (Best 3rds count, runners-up qualification math, ranking criteria)
- Knockout rules (starting round e.g. Round of 32 / Quarterfinals, extra time, penalties)
"""

import logging
from typing import Optional, Dict, Any, List

from tournament.schemas.tournament_prospect_schema import (
    StructureAndRulesSegment,
    GeneralSetup,
    GroupStageRules,
    QualifyingTablesRules,
    KnockoutRules,
    TiebreakerStep,
)

logger = logging.getLogger(__name__)


class StructureRulesAgent:
    """
    Agnostic Agent responsible for competition regulations, points logic, qualifying tables, and tiebreakers.
    """

    DEFAULT_TIEBREAKERS = [
        {"step": 1, "rule": "H2H_POINTS", "label": "Inbördes möten (Poäng)", "icon": "fa-trophy", "desc": "Flest poäng i matcher mellan berörda lag"},
        {"step": 2, "rule": "H2H_GOAL_DIFFERENCE", "label": "Inbördes målskillnad", "icon": "fa-scale-balanced", "desc": "Bäst målskillnad i matcher mellan berörda lag"},
        {"step": 3, "rule": "H2H_GOALS_SCORED", "label": "Inbördes gjorda mål", "icon": "fa-futbol", "desc": "Flest gjorda mål i matcher mellan berörda lag"},
        {"step": 4, "rule": "OVERALL_GOAL_DIFFERENCE", "label": "Total målskillnad", "icon": "fa-chart-column", "desc": "Målskillnad i samtliga gruppmatcher"},
        {"step": 5, "rule": "OVERALL_GOALS_SCORED", "label": "Gjorda mål totalt", "icon": "fa-bullseye", "desc": "Flest gjorda mål i samtliga gruppmatcher"},
        {"step": 6, "rule": "DISCIPLINARY_POINTS", "label": "Disciplinpoäng (Fair Play)", "icon": "fa-hand", "desc": "Lägst antal straffpoäng (gula/röda kort)"},
        {"step": 7, "rule": "RANDOM_DRAW", "label": "Lottning", "icon": "fa-dice", "desc": "Lottning av organisationskommittén"},
    ]

    @classmethod
    def build_structure_rules_segment(
        cls,
        audit_data: Optional[Dict[str, Any]] = None,
        official_rules_text: Optional[str] = None,
        tournament_name: str = "",
        sport: str = "Football",
        teams_count: Optional[int] = None,
    ) -> StructureAndRulesSegment:
        """
        Parses audit data and leverages Gemini AI to build a validated StructureAndRulesSegment.
        """
        audit = dict(audit_data or {})

        # 0a. Ingest data from Official Federation Portal if available
        official_ingest = audit.get("official_ingest") or {}
        if official_ingest:
            if official_ingest.get("draw_date") and not audit.get("draw_date"):
                audit["draw_date"] = official_ingest["draw_date"]
            if "draw_completed" in official_ingest and not audit.get("draw_completed"):
                audit["draw_completed"] = official_ingest["draw_completed"]
            if official_ingest.get("qualification_pathway") and not audit.get("official_rules_summary"):
                audit["official_rules_summary"] = official_ingest["qualification_pathway"]

        # 0b. Gemini AI Intelligence Enrichment with Search Grounding
        from tournament.services.gemini_scout_service import GeminiScoutService
        gemini_rules = {}
        prior_draw_completed = bool(audit.get("draw_completed") or (audit.get("tournament_blueprint") or {}).get("draw_completed"))
        if GeminiScoutService.is_available() and tournament_name:
            try:
                gemini_rules = GeminiScoutService.scout_structure_and_rules(
                    tournament_name=tournament_name,
                    sport=sport,
                    teams_count=teams_count,
                    wikipedia_context=str(audit.get("raw_text", ""))[:5000],
                ) or {}
                if gemini_rules:
                    if gemini_rules.get("points_system"):
                        audit["points_system"] = gemini_rules["points_system"]
                    if gemini_rules.get("tiebreakers"):
                        audit["tiebreakers"] = gemini_rules["tiebreakers"]
                    if gemini_rules.get("advancement_logic"):
                        audit["advancement_logic"] = gemini_rules["advancement_logic"]
                    if gemini_rules.get("knockout_rules", {}).get("starting_round"):
                        audit["knockout_stages"] = [gemini_rules["knockout_rules"]["starting_round"]]
                    if gemini_rules.get("draw_date") and not audit.get("draw_date"):
                        audit["draw_date"] = gemini_rules["draw_date"]
                    if "draw_completed" in gemini_rules:
                        # Do not overwrite confirmed draw_completed=True with False
                        if not prior_draw_completed:
                            audit["draw_completed"] = gemini_rules["draw_completed"]
                    if gemini_rules.get("official_rules_summary") and not audit.get("official_rules_summary"):
                        audit["official_rules_summary"] = gemini_rules["official_rules_summary"]
            except Exception as e:
                logger.warning("StructureRulesAgent: Gemini rules scout error: %s", e)

        bp = audit.get("tournament_blueprint") or {}
        adv_logic = audit.get("advancement_logic") or {}
        match_fmt = audit.get("match_format") or {}
        pts_sys = audit.get("points_system") or {}
        ko_rules_data = gemini_rules.get("knockout_rules") or {}

        # 1. General Setup (Draw date, seeding, host guarantees)
        draw_date = audit.get("draw_date") or bp.get("draw_date") or None
        draw_completed = bool(audit.get("draw_completed") or bp.get("draw_completed") or False)

        # Check if draw_date is in the past and normalize format
        if draw_date:
            try:
                import datetime
                from dateutil import parser
                parsed_draw = parser.parse(str(draw_date), fuzzy=True).date()
                draw_date = parsed_draw.strftime("%Y-%m-%d")
                if parsed_draw <= datetime.date.today():
                    draw_completed = True
            except Exception:
                from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                iso_draw = LLMWikipediaScout._parse_date_string(str(draw_date))
                if iso_draw:
                    draw_date = iso_draw

        seeding = audit.get("seeding_elements") or bp.get("seeding_elements") or []
        if isinstance(seeding, str):
            seeding = [s.strip() for s in seeding.split(",") if s.strip()]
        host_guar = audit.get("host_guarantees") or bp.get("host_guarantees") or None

        gen_setup = GeneralSetup(
            draw_date=draw_date,
            draw_completed=draw_completed,
            seeding_elements=list(seeding),
            host_guarantees=host_guar,
        )

        # 2. Group Stage Rules & Tiebreakers
        sport_lower = str(sport or "").lower()
        if "basket" in sport_lower or "fiba" in sport_lower:
            default_pts_win = 2
            default_pts_draw = 0
            default_pts_loss = 1
            default_extra_min = 5
            default_has_pens = False
            default_tb_desc = "Vid oavgjort spelas förlängningsperioder (5 min) tills en vinnare korats."
            default_suspension_y = "5 personliga foul = utesluten från matchen"
            default_suspension_r = "Diskvalificerande foul = matchstraff och eventuell avstängning"
        elif "ice hockey" in sport_lower or "hockey" in sport_lower:
            default_pts_win = 3
            default_pts_draw = 0
            default_pts_loss = 0
            default_extra_min = 5
            default_has_pens = True
            default_tb_desc = "Vid oavgjort spelas förlängning med Sudden Death, följt av straffläggning."
            default_suspension_y = "2 minuters utvisning"
            default_suspension_r = "Matchstraff = minst 1 match avstängning"
        elif "handball" in sport_lower or "handboll" in sport_lower:
            default_pts_win = 2
            default_pts_draw = 1
            default_pts_loss = 0
            default_extra_min = 10
            default_has_pens = True
            default_tb_desc = "Vid oavgjort i slutspel spelas förlängning (2x5 min) följt av straffkast vid behov."
            default_suspension_y = "Gult kort / 2 minuters utvisning"
            default_suspension_r = "Rött / blått kort = rapport och avstängning"
        elif "volleyball" in sport_lower or "volleyboll" in sport_lower:
            default_pts_win = 3
            default_pts_draw = 0
            default_pts_loss = 0
            default_extra_min = 0
            default_has_pens = False
            default_tb_desc = "Matcher avgörs i bäst av 5 set (skiljeset till 15 poäng)."
            default_suspension_y = "Varning (gult kort)"
            default_suspension_r = "Uteslutning / diskvalificering (rött kort)"
        else:
            default_pts_win = 3
            default_pts_draw = 1
            default_pts_loss = 0
            default_extra_min = 30
            default_has_pens = True
            default_tb_desc = "Vid oavgjort i slutspel tillämpas Förlängning (2x15 min) följt av Straffsparksläggning."
            default_suspension_y = "2 gula kort = 1 match avstängning"
            default_suspension_r = "1 rött kort = minst 1 match avstängning"

        pts_win = pts_sys.get("win", bp.get("points_for_win", default_pts_win))
        pts_draw = pts_sys.get("draw", bp.get("points_for_draw", default_pts_draw))
        pts_loss = pts_sys.get("loss", bp.get("points_for_loss", default_pts_loss))

        raw_tb = audit.get("tiebreakers") or bp.get("tiebreaker_hierarchy") or []
        tb_steps: List[TiebreakerStep] = []
        if raw_tb:
            for idx, item in enumerate(raw_tb, start=1):
                if isinstance(item, dict):
                    tb_steps.append(TiebreakerStep(
                        step=item.get("step", idx),
                        rule=item.get("rule", "CUSTOM"),
                        label=item.get("label", str(item)),
                        icon=item.get("icon", "fa-list-ol"),
                        desc=item.get("desc", ""),
                    ))
                else:
                    tb_steps.append(TiebreakerStep(
                        step=idx,
                        rule=str(item),
                        label=str(item),
                        icon="fa-list-ol",
                        desc="",
                    ))
        else:
            tb_steps = [TiebreakerStep(**tb) for tb in cls.DEFAULT_TIEBREAKERS]

        teams_adv = adv_logic.get("teams_per_group_advancing") or bp.get("teams_per_group_advancing") or 2

        group_rules = GroupStageRules(
            points_win=int(pts_win),
            points_draw=int(pts_draw),
            points_loss=int(pts_loss),
            yellow_cards_suspension=default_suspension_y,
            red_card_suspension=default_suspension_r,
            tiebreaker_hierarchy=tb_steps,
            teams_per_group_advancing=int(teams_adv),
        )

        # 3. Qualifying Tables Rules
        has_b3 = bool(adv_logic.get("has_best_thirds_table") or bp.get("has_best_thirds_table") or False)
        b3_count = int(adv_logic.get("best_third_placed_advancing") or bp.get("best_third_placed_advancing") or 0)
        has_ru = bool(adv_logic.get("has_runners_up_table") or bp.get("has_runners_up_table") or False)
        ru_count = int(adv_logic.get("runners_up_advancing") or bp.get("runners_up_advancing") or 0)

        qual_desc = adv_logic.get("description") or ""
        if not qual_desc:
            if has_b3 and b3_count > 0:
                qual_desc = f"De {b3_count} bästa 3:orna avancerar till slutspel."
            elif has_ru and ru_count > 0:
                qual_desc = f"De {ru_count} bästa tvåorna avancerar till slutspel/playoff."

        qual_rules = QualifyingTablesRules(
            has_best_thirds=has_b3,
            best_thirds_count=b3_count,
            has_runners_up=has_ru,
            runners_up_count=ru_count,
            ranking_criteria=adv_logic.get("qualifying_table_ranking_criteria") or ["Poäng", "Målskillnad", "Gjorda mål", "Disciplinpoäng"],
            description=qual_desc,
        )

        # 4. Knockout Rules
        ko_stages = audit.get("knockout_stages") or []
        first_round = ko_rules_data.get("starting_round") or (ko_stages[0] if ko_stages else "Slutspel")
        if isinstance(first_round, dict):
            first_round = first_round.get("stage_name", "Slutspel")

        extra_min = ko_rules_data.get("extra_time_minutes") if ko_rules_data.get("extra_time_minutes") is not None else match_fmt.get("extra_time_minutes", default_extra_min)
        has_pens = ko_rules_data.get("has_penalties") if "has_penalties" in ko_rules_data else match_fmt.get("has_penalties", default_has_pens)
        tiebreaker_desc = ko_rules_data.get("tiebreaker_description") or default_tb_desc

        ko_rules = KnockoutRules(
            starting_round=str(first_round),
            total_rounds=ko_rules_data.get("total_rounds") or len(ko_stages) or 3,
            extra_time_minutes=int(extra_min if extra_min is not None else default_extra_min),
            has_penalties=bool(has_pens),
            tiebreaker_description=tiebreaker_desc,
        )

        rules_summary = official_rules_text or audit.get("official_rules_summary") or bp.get("official_rules_summary") or ""

        return StructureAndRulesSegment(
            general_setup=gen_setup,
            group_stage_rules=group_rules,
            qualifying_tables_rules=qual_rules,
            knockout_rules=ko_rules,
            official_rules_summary=rules_summary,
        )
