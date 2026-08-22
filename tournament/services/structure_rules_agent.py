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

        # 0. Gemini AI Intelligence Enrichment
        from tournament.services.gemini_scout_service import GeminiScoutService
        if GeminiScoutService.is_available() and tournament_name:
            try:
                gemini_rules = GeminiScoutService.scout_structure_and_rules(
                    tournament_name=tournament_name,
                    sport=sport,
                    teams_count=teams_count,
                    wikipedia_context=str(audit.get("raw_text", ""))[:4000],
                )
                if gemini_rules:
                    if not audit.get("points_system") and gemini_rules.get("points_system"):
                        audit["points_system"] = gemini_rules["points_system"]
                    if not audit.get("tiebreakers") and gemini_rules.get("tiebreakers"):
                        audit["tiebreakers"] = gemini_rules["tiebreakers"]
                    if not audit.get("advancement_logic") and gemini_rules.get("advancement_logic"):
                        audit["advancement_logic"] = gemini_rules["advancement_logic"]
                    if not audit.get("knockout_stages") and gemini_rules.get("knockout_rules", {}).get("starting_round"):
                        audit["knockout_stages"] = [gemini_rules["knockout_rules"]["starting_round"]]
                    if not audit.get("draw_date") and gemini_rules.get("draw_date"):
                        audit["draw_date"] = gemini_rules["draw_date"]
                    if "draw_completed" not in audit and "draw_completed" in gemini_rules:
                        audit["draw_completed"] = gemini_rules["draw_completed"]
                    if not audit.get("official_rules_summary") and gemini_rules.get("official_rules_summary"):
                        audit["official_rules_summary"] = gemini_rules["official_rules_summary"]
            except Exception as e:
                logger.warning("StructureRulesAgent: Gemini rules scout error: %s", e)

        bp = audit.get("tournament_blueprint") or {}
        adv_logic = audit.get("advancement_logic") or {}
        match_fmt = audit.get("match_format") or {}
        pts_sys = audit.get("points_system") or {}

        # 1. General Setup (Draw date, seeding, host guarantees)
        draw_date = audit.get("draw_date") or bp.get("draw_date") or None
        draw_completed = bool(audit.get("draw_completed") or bp.get("draw_completed") or False)
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
        pts_win = pts_sys.get("win", bp.get("points_for_win", 3))
        pts_draw = pts_sys.get("draw", bp.get("points_for_draw", 1))
        pts_loss = pts_sys.get("loss", bp.get("points_for_loss", 0))

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
            yellow_cards_suspension="2 gula kort = 1 match avstängning",
            red_card_suspension="1 rött kort = minst 1 match avstängning",
            tiebreaker_hierarchy=tb_steps,
            teams_per_group_advancing=int(teams_adv),
        )

        # 3. Qualifying Tables Rules
        has_b3 = bool(adv_logic.get("has_best_thirds_table") or bp.get("has_best_thirds_table") or False)
        b3_count = int(adv_logic.get("best_third_placed_advancing") or bp.get("best_third_placed_advancing") or 0)
        has_ru = bool(adv_logic.get("has_runners_up_table") or bp.get("has_runners_up_table") or False)
        ru_count = int(adv_logic.get("runners_up_advancing") or bp.get("runners_up_advancing") or 0)

        qual_desc = ""
        if has_b3 and b3_count > 0:
            qual_desc = f"De {b3_count} bästa 3:orna avancerar till slutspel."
        elif has_ru and ru_count > 0:
            qual_desc = f"De {ru_count} bästa tvåorna avancerar till slutspel/playoff."

        qual_rules = QualifyingTablesRules(
            has_best_thirds=has_b3,
            best_thirds_count=b3_count,
            has_runners_up=has_ru,
            runners_up_count=ru_count,
            ranking_criteria=["Poäng", "Målskillnad", "Gjorda mål", "Disciplinpoäng"],
            description=qual_desc,
        )

        # 4. Knockout Rules
        ko_stages = audit.get("knockout_stages") or []
        first_round = ko_stages[0] if ko_stages else "Slutspel"
        if isinstance(first_round, dict):
            first_round = first_round.get("stage_name", "Slutspel")

        extra_min = match_fmt.get("extra_time_minutes", 30) if match_fmt.get("extra_time_minutes") is not None else 30
        has_pens = match_fmt.get("has_penalties", True)

        ko_rules = KnockoutRules(
            starting_round=str(first_round),
            total_rounds=len(ko_stages) or 3,
            extra_time_minutes=int(extra_min),
            has_penalties=bool(has_pens),
            tiebreaker_description="Vid oavgjort i slutspel tillämpas Förlängning (2x15 min) följt av Straffsparksläggning.",
        )

        rules_summary = official_rules_text or audit.get("official_rules_summary") or bp.get("official_rules_summary") or ""

        return StructureAndRulesSegment(
            general_setup=gen_setup,
            group_stage_rules=group_rules,
            qualifying_tables_rules=qual_rules,
            knockout_rules=ko_rules,
            official_rules_summary=rules_summary,
        )
