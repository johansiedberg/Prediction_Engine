"""
Unified Tournament Prospect JSON Schema
=======================================
Pydantic schema definitions representing the single authoritative state contract
for AI-scouted tournament prospects across all ingestion agents, deep-scanners,
staging models, and the live tournament creation engine.
"""

from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator


class ScoutingStage(str, Enum):
    SHALLOW = "SHALLOW"
    DEEP = "DEEP"


class CompletenessGrade(str, Enum):
    GRADE_A = "GRADE_A"  # 100% Ready (Redo)
    GRADE_B = "GRADE_B"  # Pending Draw/Fixtures (Väntar lottning)
    GRADE_C = "GRADE_C"  # Pending Deepscan / Missing structure (Ej redo)
    GRADE_D = "GRADE_D"  # Incompatible / Past event / Discarded


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


class ProspectMetadata(BaseModel):
    name: str = Field(description="Official tournament name e.g. FIFA World Cup 2026")
    master_event_code: str = Field(description="Slug identifier e.g. fifa-world-cup-2026")
    sport: str = Field(default="Football", description="Sport discipline")
    is_h2h_team_sport: bool = Field(default=True, description="True if H2H team sport with group/knockout mechanics")
    organizer: str = Field(default="", description="Governing body e.g. FIFA, UEFA, IFF")
    host_country: str = Field(default="", description="Host country or host cities")
    start_date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD")
    draw_date: Optional[str] = Field(default=None, description="Official draw date e.g. 2026-12-06")
    draw_completed: bool = Field(default=False, description="True if official draw completed")
    official_source_url: str = Field(default="", description="Direct URL to official website")
    logo_url: str = Field(default="", description="Emblem or logotype image URL")
    wikidata_qid: Optional[str] = Field(default=None, description="Wikidata Entity QID")


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



class TeamEntry(BaseModel):
    name: str = Field(description="Team name e.g. Spain")
    code: str = Field(default="", description="Short code e.g. ESP")
    is_placeholder: bool = Field(default=False, description="True if placeholder like A1 or Team 1")
    flag_emoji: str = Field(default="")


class GroupProspect(BaseModel):
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



class FixtureProspect(BaseModel):
    match_number: int = Field(description="Sequence match number")
    stage_or_group: str = Field(default="Group Stage")
    date_time: Optional[str] = Field(default=None)
    home_team: str = Field(default="")
    away_team: str = Field(default="")
    venue: str = Field(default="")
    is_placeholder: bool = Field(default=False)


class KnockoutMatchProspect(BaseModel):
    match_code: str = Field(description="e.g. QF_1")
    stage_name: str = Field(default="Quarterfinals")
    home_source: str = Field(default="Winner Group A")
    away_source: str = Field(default="Runner-up Group B")


class KnockoutStageProspect(BaseModel):
    stage_name: str = Field(description="e.g. Quarterfinals")
    matches: List[KnockoutMatchProspect] = Field(default_factory=list)


class RulesAndPointsProspect(BaseModel):
    points_for_win: int = Field(default=3)
    points_for_draw: int = Field(default=1)
    points_for_loss: int = Field(default=0)
    yellow_card_suspension_threshold: int = Field(default=2)
    tiebreaker_hierarchy: List[TiebreakerRule] = Field(
        default_factory=lambda: [
            TiebreakerRule.H2H_POINTS,
            TiebreakerRule.H2H_GOAL_DIFFERENCE,
            TiebreakerRule.H2H_GOALS_SCORED,
            TiebreakerRule.OVERALL_GOAL_DIFFERENCE,
            TiebreakerRule.OVERALL_GOALS_SCORED,
            TiebreakerRule.DISCIPLINARY_POINTS,
            TiebreakerRule.RANDOM_DRAW,
        ]
    )
    knockout_tiebreakers: str = Field(default="Vid oavgjort i slutspel tillämpas Förlängning (2x15 min) följt av Straffsparksläggning.")
    official_rules_summary: str = Field(default="")


class TournamentProspectBlueprint(BaseModel):
    """
    Unified Schema model representing a complete tournament prospect.
    """
    metadata: ProspectMetadata
    scouting_audit: ScoutingAudit = Field(default_factory=ScoutingAudit)
    groups: List[GroupProspect] = Field(default_factory=list)
    fixtures: List[FixtureProspect] = Field(default_factory=list)
    knockout_stages: List[KnockoutStageProspect] = Field(default_factory=list)
    rules_and_points: RulesAndPointsProspect = Field(default_factory=RulesAndPointsProspect)

    def to_legacy_dict(self) -> Dict[str, Any]:
        """
        Converts blueprint into legacy payload format for backwards compatibility with existing views.
        """
        return {
            "master_event": {
                "name": self.metadata.name,
                "code": self.metadata.master_event_code,
                "sport": self.metadata.sport,
                "organizer": self.metadata.organizer,
                "host_country": self.metadata.host_country,
                "start_date": self.metadata.start_date or "",
                "end_date": self.metadata.end_date or "",
                "official_source_url": self.metadata.official_source_url,
                "wikidata_qid": self.metadata.wikidata_qid,
            },
            "tournament_config": {
                "name": self.metadata.name,
                "total_teams": sum(len(g.teams) for g in self.groups) or 16,
                "knockout_stages": [ks.stage_name for ks in self.knockout_stages],
            },
            "scouting_audit": {
                "scouting_stage": self.scouting_audit.stage.value,
                "completeness_grade": self.scouting_audit.completeness_grade.value,
                "grade_reason": self.scouting_audit.grade_reason,
                "missing_items": self.scouting_audit.missing_items,
                "official_source_url": self.metadata.official_source_url,
                "next_rescan_date": self.scouting_audit.next_rescan_date,
                "scan_timestamp": self.scouting_audit.scan_timestamp,
                "advancement_rules": self.rules_and_points.official_rules_summary,
            },
            "groups": [
                {
                    "name": g.name,
                    "teams": [{"name": t.name, "code": t.code} for t in g.teams],
                    "advancement_description": g.advancement_description,
                }
                for g in self.groups
            ],
            "fixtures_sample": [
                {
                    "match_number": f.match_number,
                    "stage_or_group": f.stage_or_group,
                    "date_time": f.date_time or "",
                    "home_team": f.home_team,
                    "away_team": f.away_team,
                    "venue": f.venue,
                    "is_placeholder": f.is_placeholder,
                }
                for f in self.fixtures
            ],
            "knockout_mapping_sample": [
                {
                    "stage": km.stage_name,
                    "match_code": km.match_code,
                    "home_placeholder": km.home_source,
                    "away_placeholder": km.away_source,
                }
                for ks in self.knockout_stages
                for km in ks.matches
            ],
            "logo_url": self.metadata.logo_url,
            "tournament_blueprint": {
                "tournament_name": self.metadata.name,
                "sport": self.metadata.sport,
                "organizer": self.metadata.organizer,
                "host_country": self.metadata.host_country,
                "start_date": self.metadata.start_date,
                "end_date": self.metadata.end_date,
                "draw_date": self.metadata.draw_date or self.scouting_audit.draw_date or "",
                "draw_completed": self.metadata.draw_completed or self.scouting_audit.draw_completed,
                "tiebreaker_hierarchy": [tb.value for tb in self.rules_and_points.tiebreaker_hierarchy],
                "points_for_win": self.rules_and_points.points_for_win,
                "points_for_draw": self.rules_and_points.points_for_draw,
                "points_for_loss": self.rules_and_points.points_for_loss,
                "yellow_card_suspension_threshold": self.rules_and_points.yellow_card_suspension_threshold,

                "knockout_tiebreakers": self.rules_and_points.knockout_tiebreakers,
                "official_rules_summary": self.rules_and_points.official_rules_summary,
            },
        }
