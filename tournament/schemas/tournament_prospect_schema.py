"""
Unified Tournament Prospect JSON Schema (5-Segment Agnostic Blueprint)
========================================================================
Pydantic schema definitions representing the single authoritative state contract
for AI-scouted tournament prospects across all ingestion agents, deep-scanners,
staging models, and the live tournament creation engine.

Divided into 5 distinct agnostic segments:
1. HeadSegment (Discovery / Webcrawl)
2. GeneralSegment (Deepscan)
3. StructureAndRulesSegment (Deepscan)
4. GroupsAndTeamsSegment (Deepscan)
5. MatchesAndKnockoutSegment (Deepscan)
"""

from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator


class ScoutingStage(str, Enum):
    SHALLOW = "SHALLOW"
    DEEP = "DEEP"


class CompletenessGrade(str, Enum):
    GRADE_A = "GRADE_A"
    GRADE_B = "GRADE_B"
    GRADE_C = "GRADE_C"
    GRADE_D = "GRADE_D"


class ProspectStatus(str, Enum):
    NEW = "NEW"
    WATCHLIST = "WATCHLIST"
    CONVERTED = "CONVERTED"
    ARCHIVED = "ARCHIVED"


class TiebreakerRule(str, Enum):
    H2H_POINTS = "H2H_POINTS"
    H2H_GOAL_DIFFERENCE = "H2H_GOAL_DIFFERENCE"
    H2H_GOALS_SCORED = "H2H_GOALS_SCORED"
    OVERALL_GOAL_DIFFERENCE = "OVERALL_GOAL_DIFFERENCE"
    OVERALL_GOALS_SCORED = "OVERALL_GOALS_SCORED"
    DISCIPLINARY_POINTS = "DISCIPLINARY_POINTS"
    COEFFICIENT = "COEFFICIENT"
    RANDOM_DRAW = "RANDOM_DRAW"


# ---------------------------------------------------------------------------
# 1. HEAD SEGMENT (Webcrawl / Discovery)
# ---------------------------------------------------------------------------

class HeadSegment(BaseModel):
    name: str = Field(description="Official tournament name e.g. FIFA World Cup 2026")
    master_event_code: str = Field(description="Slug identifier e.g. fifa-world-cup-2026")
    sport: str = Field(default="Football", description="Sport discipline")
    is_h2h_team_sport: bool = Field(default=True, description="True if H2H team sport with group/knockout mechanics")
    start_date: Optional[str] = Field(default=None, description="Expected start date YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="Expected end date YYYY-MM-DD")
    organizer: str = Field(default="", description="Governing body e.g. FIFA, UEFA, IIHF")
    host_country: str = Field(default="", description="Host country")
    discovery_source: str = Field(default="", description="Source of shallow discovery e.g. AllSportDB, WikiPortal")


# ---------------------------------------------------------------------------
# 2. GENERAL SEGMENT (Deepscan)
# ---------------------------------------------------------------------------

class LocationInfo(BaseModel):
    host_country: str = Field(default="", description="Host country or multiple countries")
    host_cities: List[str] = Field(default_factory=list, description="Host cities")
    venues: List[str] = Field(default_factory=list, description="Stadiums and venues")


class EmblemInfo(BaseModel):
    logo_url: str = Field(default="", description="Emblem or logotype image URL")
    is_vector: bool = Field(default=False, description="True if SVG or high-res vector")
    is_transparent: bool = Field(default=False, description="True if transparent background")
    source: str = Field(default="", description="Emblem source e.g. Wikimedia Commons, Official")


class BackdropInfo(BaseModel):
    backdrop_url: str = Field(default="", description="Tournament landscape backdrop / banner image URL")
    source: str = Field(default="", description="Backdrop source e.g. Official Site, Key Visual, Google Search")


class GeneralSegment(BaseModel):
    start_date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD")
    location: LocationInfo = Field(default_factory=LocationInfo)
    emblem: EmblemInfo = Field(default_factory=EmblemInfo)
    backdrop: BackdropInfo = Field(default_factory=BackdropInfo)
    organizer: str = Field(default="", description="Governing body e.g. FIFA, UEFA, IIHF")
    official_website_url: str = Field(default="", description="Direct URL to official federation tournament site")
    wikipedia_url: str = Field(default="", description="Wikipedia article URL")
    wikidata_qid: Optional[str] = Field(default=None, description="Wikidata Entity QID")


# ---------------------------------------------------------------------------
# 3. STRUCTURE & RULES SEGMENT (Deepscan)
# ---------------------------------------------------------------------------

class TiebreakerStep(BaseModel):
    step: int = Field(default=1)
    rule: str = Field(default="H2H_POINTS")
    label: str = Field(default="Inbördes möten (Poäng)")
    icon: str = Field(default="fa-trophy")
    desc: str = Field(default="")


class GeneralSetup(BaseModel):
    draw_date: Optional[str] = Field(default=None, description="Date of official group/fixture lottery")
    draw_completed: bool = Field(default=False, description="True if official draw is complete")
    seeding_elements: List[str] = Field(default_factory=list, description="Seeding pots/tiers e.g. Pot 1 (Hosts)")
    host_guarantees: Optional[str] = Field(default=None, description="Host team auto-placement rules")


class GroupStageRules(BaseModel):
    points_win: int = Field(default=3)
    points_draw: int = Field(default=1)
    points_loss: int = Field(default=0)
    yellow_cards_suspension: str = Field(default="2 gula kort = 1 match avstängning")
    red_card_suspension: str = Field(default="1 rött kort = minst 1 match avstängning")
    tiebreaker_hierarchy: List[TiebreakerStep] = Field(default_factory=list)
    teams_per_group_advancing: int = Field(default=2)


class QualifyingTablesRules(BaseModel):
    has_best_thirds: bool = Field(default=False)
    best_thirds_count: int = Field(default=0)
    has_runners_up: bool = Field(default=False)
    runners_up_count: int = Field(default=0)
    ranking_criteria: List[str] = Field(default_factory=list)
    description: str = Field(default="")


class KnockoutRules(BaseModel):
    starting_round: str = Field(default="Slutspel")
    total_rounds: int = Field(default=3)
    extra_time_minutes: int = Field(default=30)
    has_penalties: bool = Field(default=True)
    tiebreaker_description: str = Field(default="Vid oavgjort i slutspel spelas förlängning följt av straffar.")


class StructureAndRulesSegment(BaseModel):
    general_setup: GeneralSetup = Field(default_factory=GeneralSetup)
    group_stage_rules: GroupStageRules = Field(default_factory=GroupStageRules)
    qualifying_tables_rules: QualifyingTablesRules = Field(default_factory=QualifyingTablesRules)
    knockout_rules: KnockoutRules = Field(default_factory=KnockoutRules)
    official_rules_summary: str = Field(default="")


# ---------------------------------------------------------------------------
# 4. GROUPS & TEAMS SEGMENT (Deepscan)
# ---------------------------------------------------------------------------

class TeamEntry(BaseModel):
    name: str = Field(description="Team name e.g. Spain or Real Madrid")
    code: str = Field(default="", description="FlagCDN country code e.g. es, se, gb-eng")
    is_placeholder: bool = Field(default=False, description="True if placeholder like A1 or Playoff Winner")
    seed: Optional[str] = Field(default=None, description="Seeding code e.g. A1, Pot 1")
    flag_emoji: str = Field(default="")
    flag_url: str = Field(default="", description="Direct URL to national flag image")
    emblem_url: str = Field(default="", description="Direct URL to club badge / crest image")


class GroupEntry(BaseModel):
    name: str = Field(description="Group designation e.g. Group A")
    teams_count: int = Field(default=4)
    teams: List[TeamEntry] = Field(default_factory=list)
    advancement_description: str = Field(default="")

    @field_validator("teams", mode="before")
    @classmethod
    def normalize_teams(cls, v: Any) -> List[Any]:
        if not isinstance(v, list):
            return []
        result = []
        for item in v:
            if isinstance(item, TeamEntry):
                result.append(item)
            elif isinstance(item, dict):
                result.append(item)
            elif isinstance(item, str):
                s = item.strip()
                if s:
                    result.append({"name": s, "is_placeholder": False})
        return result


class GroupsAndTeamsSegment(BaseModel):
    groups_count: int = Field(default=0)
    teams_count: int = Field(default=0)
    has_real_teams: bool = Field(default=False)
    groups: List[GroupEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 5. MATCHES & KNOCKOUT SEGMENT (Deepscan)
# ---------------------------------------------------------------------------

class GroupMatchEntry(BaseModel):
    match_number: int = Field(description="Sequence match number")
    stage_or_group: str = Field(default="Group Stage")
    home_team: str = Field(default="")
    away_team: str = Field(default="")
    home_team_code: str = Field(default="")
    home_team_flag_url: str = Field(default="")
    home_team_emblem_url: str = Field(default="")
    away_team_code: str = Field(default="")
    away_team_flag_url: str = Field(default="")
    away_team_emblem_url: str = Field(default="")
    date_time: Optional[str] = Field(default=None)
    venue: str = Field(default="")
    is_placeholder: bool = Field(default=False)


class AdvancementFixtureEntry(BaseModel):
    match_code: str = Field(description="e.g. R32_1, QF_1")
    stage_name: str = Field(default="Quarterfinals")
    source_home: str = Field(default="Winner Group A")
    source_away: str = Field(default="Runner-up Group B")


class KnockoutMatchEntry(BaseModel):
    match_code: str = Field(description="e.g. QF_1")
    stage_name: str = Field(default="Quarterfinals")
    home_team: str = Field(default="")
    away_team: str = Field(default="")
    home_team_code: str = Field(default="")
    home_team_flag_url: str = Field(default="")
    home_team_emblem_url: str = Field(default="")
    away_team_code: str = Field(default="")
    away_team_flag_url: str = Field(default="")
    away_team_emblem_url: str = Field(default="")
    winner_to: Optional[str] = Field(default=None)
    date_time: Optional[str] = Field(default=None)
    venue: str = Field(default="")


class KnockoutStageEntry(BaseModel):
    stage_name: str = Field(description="e.g. Round of 32, Quarterfinals")
    round_order: int = Field(default=1)
    matches: List[KnockoutMatchEntry] = Field(default_factory=list)


class MatchesAndKnockoutSegment(BaseModel):
    total_matches: int = Field(default=0)
    fixtures_completed: bool = Field(default=False)
    group_matches: List[GroupMatchEntry] = Field(default_factory=list)
    advancement_fixtures: List[AdvancementFixtureEntry] = Field(default_factory=list)
    knockout_bracket: List[KnockoutStageEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SCOUTING AUDIT & UNIFIED BLUEPRINT
# ---------------------------------------------------------------------------

class ScoutingAudit(BaseModel):
    stage: ScoutingStage = Field(default=ScoutingStage.SHALLOW)
    completeness_grade: CompletenessGrade = Field(default=CompletenessGrade.GRADE_C)
    status: ProspectStatus = Field(default=ProspectStatus.NEW)
    grade_reason: str = Field(default="")
    missing_items: List[str] = Field(default_factory=list)
    draw_date: Optional[str] = Field(default=None)
    draw_completed: bool = Field(default=False)
    next_rescan_date: Optional[str] = Field(default=None)
    scan_timestamp: Optional[str] = Field(default=None)
    active_sources_used: List[str] = Field(default_factory=list)


class TournamentProspectBlueprint(BaseModel):
    """
    Unified 5-Segment Tournament Prospect Blueprint Model.
    """
    head_segment: Optional[HeadSegment] = None
    metadata: Optional[HeadSegment] = Field(default=None, exclude=True)
    general_segment: GeneralSegment = Field(default_factory=GeneralSegment)
    structure_and_rules_segment: StructureAndRulesSegment = Field(default_factory=StructureAndRulesSegment)
    groups_and_teams_segment: GroupsAndTeamsSegment = Field(default_factory=GroupsAndTeamsSegment)
    matches_and_knockout_segment: MatchesAndKnockoutSegment = Field(default_factory=MatchesAndKnockoutSegment)
    scouting_audit: ScoutingAudit = Field(default_factory=ScoutingAudit)
    groups_init: Optional[List[GroupEntry]] = Field(default=None, alias="groups", exclude=True)

    def model_post_init(self, __context: Any) -> None:
        if self.head_segment is None and self.metadata is not None:
            self.head_segment = self.metadata
        elif self.head_segment is None:
            self.head_segment = HeadSegment(name="Tournament Prospect", master_event_code="prospect")

        if self.groups_init is not None:
            self.groups_and_teams_segment.groups = self.groups_init
            self.groups_and_teams_segment.groups_count = len(self.groups_init)
            self.groups_and_teams_segment.teams_count = sum(len(g.teams) for g in self.groups_init)

    @property
    def groups(self) -> List[GroupEntry]:
        return self.groups_and_teams_segment.groups

    @property
    def fixtures(self) -> List[GroupMatchEntry]:
        return self.matches_and_knockout_segment.group_matches

    def to_legacy_dict(self) -> Dict[str, Any]:
        return self.to_payload_dict()

    def to_payload_dict(self) -> Dict[str, Any]:
        """
        Exports full 5-segment schema as a persistent dictionary with backward-compatible accessors.
        """
        head_dict = self.head_segment.model_dump() if self.head_segment else {}
        gen_dict = self.general_segment.model_dump()
        struct_dict = self.structure_and_rules_segment.model_dump()
        groups_dict = self.groups_and_teams_segment.model_dump()
        matches_dict = self.matches_and_knockout_segment.model_dump()
        audit_dict = self.scouting_audit.model_dump()
        audit_dict["scouting_stage"] = self.scouting_audit.stage.value if hasattr(self.scouting_audit.stage, 'value') else str(self.scouting_audit.stage)

        blueprint_dict = {
            "head_segment": head_dict,
            "general_segment": gen_dict,
            "structure_and_rules_segment": struct_dict,
            "groups_and_teams_segment": groups_dict,
            "matches_and_knockout_segment": matches_dict,
            "scouting_audit": audit_dict,
        }

        return {
            "head_segment": head_dict,
            "general_segment": gen_dict,
            "structure_and_rules_segment": struct_dict,
            "groups_and_teams_segment": groups_dict,
            "matches_and_knockout_segment": matches_dict,
            "scouting_audit": audit_dict,
            "tournament_blueprint": blueprint_dict,
            # Legacy aliases for existing view layers & templates
            "master_event": {
                "name": self.head_segment.name if self.head_segment else "",
                "code": self.head_segment.master_event_code if self.head_segment else "",
                "sport": self.head_segment.sport if self.head_segment else "Football",
                "organizer": self.general_segment.organizer,
                "host_country": self.general_segment.location.host_country,
                "start_date": self.general_segment.start_date or (self.head_segment.start_date if self.head_segment else "") or "",
                "end_date": self.general_segment.end_date or "",
                "official_source_url": self.general_segment.official_website_url,
                "wikipedia_url": self.general_segment.wikipedia_url,
                "wikidata_qid": self.general_segment.wikidata_qid,
                "logo_url": self.general_segment.emblem.logo_url,
            },
            "tournament_config": {
                "name": self.head_segment.name if self.head_segment else "",
                "total_teams": self.groups_and_teams_segment.teams_count or 16,
                "knockout_stages": [ks.stage_name for ks in self.matches_and_knockout_segment.knockout_bracket],
            },
            "groups": [g.model_dump() for g in self.groups_and_teams_segment.groups],
            "fixtures_sample": [m.model_dump() for m in self.matches_and_knockout_segment.group_matches],
            "knockout_mapping_sample": [
                {
                    "stage": km.stage_name,
                    "match_code": km.match_code,
                    "home_placeholder": km.source_home,
                    "away_placeholder": km.source_away,
                }
                for km in self.matches_and_knockout_segment.advancement_fixtures
            ],
            "logo_url": self.general_segment.emblem.logo_url,
            "draw_date": self.structure_and_rules_segment.general_setup.draw_date or self.scouting_audit.draw_date or "",
            "draw_completed": self.structure_and_rules_segment.general_setup.draw_completed or self.scouting_audit.draw_completed,
            "advancement_logic": {
                "teams_per_group_advancing": self.structure_and_rules_segment.group_stage_rules.teams_per_group_advancing,
                "best_third_placed_advancing": self.structure_and_rules_segment.qualifying_tables_rules.best_thirds_count,
                "has_best_thirds_table": self.structure_and_rules_segment.qualifying_tables_rules.has_best_thirds,
                "has_runners_up_table": self.structure_and_rules_segment.qualifying_tables_rules.has_runners_up,
            },
            "points_system": {
                "win": self.structure_and_rules_segment.group_stage_rules.points_win,
                "draw": self.structure_and_rules_segment.group_stage_rules.points_draw,
                "loss": self.structure_and_rules_segment.group_stage_rules.points_loss,
            },
            "match_format": {
                "regular_time_minutes": 90,
                "extra_time_minutes": self.structure_and_rules_segment.knockout_rules.extra_time_minutes,
                "has_penalties": self.structure_and_rules_segment.knockout_rules.has_penalties,
            },
            "tiebreakers": [tb.label for tb in self.structure_and_rules_segment.group_stage_rules.tiebreaker_hierarchy],
        }


# Legacy Aliases for backwards compatibility with previous imports
ProspectMetadata = HeadSegment
GroupProspect = GroupEntry
FixtureProspect = GroupMatchEntry
KnockoutStageProspect = KnockoutStageEntry
KnockoutMatchProspect = KnockoutMatchEntry
RulesAndPointsProspect = StructureAndRulesSegment
