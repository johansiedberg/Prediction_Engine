from enum import Enum
from typing import List, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator


class TiebreakerRule(str, Enum):
    """
    Strict list of tiebreaker rules used by tournament standing engines.
    """
    H2H_POINTS = "H2H_POINTS"
    H2H_GOAL_DIFFERENCE = "H2H_GOAL_DIFFERENCE"
    H2H_GOALS_SCORED = "H2H_GOALS_SCORED"
    OVERALL_GOAL_DIFFERENCE = "OVERALL_GOAL_DIFFERENCE"
    OVERALL_GOALS_SCORED = "OVERALL_GOALS_SCORED"
    DISCIPLINARY_POINTS = "DISCIPLINARY_POINTS"
    COEFFICIENT = "COEFFICIENT"
    RANDOM_DRAW = "RANDOM_DRAW"


class GroupStructure(BaseModel):
    """
    Represents a single group within the group stage.
    """
    name: str = Field(description="Group designation e.g. 'Group A'")
    teams_count: int = Field(default=4, description="Number of teams in group")
    teams: List[str] = Field(default_factory=list, description="List of team names or placeholder codes e.g. ['Sweden', 'Finland']")
    advancement_description: Optional[str] = Field(default="", description="Plain text explanation of advancement e.g. 'Top 2 advance to R16'")

    @field_validator("teams", mode="before")
    @classmethod
    def normalize_team_names(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            return []
        clean = []
        for item in v:
            if isinstance(item, dict):
                t_name = str(item.get("name") or "").strip()
            else:
                t_name = str(item or "").strip()
            if t_name:
                clean.append(t_name)
        return clean


class KnockoutMatchPlaceholder(BaseModel):
    """
    Represents a logical match mapping in the knockout tree before teams are decided.
    """
    match_code: str = Field(description="Unique match identifier code e.g. 'R16_M1' or 'QF_1'")
    home_source: str = Field(description="Logical mapping for home team e.g. 'W_GroupA' or 'W_R16_M1'")
    away_source: str = Field(description="Logical mapping for away team e.g. 'RU_GroupB' or 'W_R16_M2'")
    stage_name: str = Field(description="Name of knockout round e.g. 'Round of 16', 'Quarterfinals', 'Semifinals', 'Final'")


class KnockoutStructure(BaseModel):
    """
    Represents a single knockout stage.
    """
    stage_name: str = Field(description="Stage name e.g. 'Round of 16', 'Quarterfinals', 'Semifinals', 'Final'")
    match_count: int = Field(default=0, description="Number of matches in this stage")
    matches: List[KnockoutMatchPlaceholder] = Field(default_factory=list)
    has_third_place_match: bool = Field(default=False)


class TournamentSetup(BaseModel):
    """
    Root structural blueprint model extracted by Gemini Deepscan.
    """
    tournament_name: str = Field(default="", description="Official display name of the tournament")
    sport: str = Field(default="Football", description="Sport discipline")
    organizer: str = Field(default="", description="Governing body e.g. FIFA, UEFA, IFF")
    host_country: str = Field(default="", description="Host country or host cities")
    start_date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD")
    teams_count: int = Field(default=0, description="Total participating teams count")
    groups_count: int = Field(default=0, description="Number of groups in group stage")
    groups: List[GroupStructure] = Field(default_factory=list)
    knockout_stages: List[KnockoutStructure] = Field(default_factory=list)
    tiebreaker_hierarchy: List[TiebreakerRule] = Field(
        default_factory=lambda: [
            TiebreakerRule.H2H_POINTS,
            TiebreakerRule.H2H_GOAL_DIFFERENCE,
            TiebreakerRule.H2H_GOALS_SCORED,
            TiebreakerRule.OVERALL_GOAL_DIFFERENCE,
            TiebreakerRule.OVERALL_GOALS_SCORED,
            TiebreakerRule.DISCIPLINARY_POINTS,
            TiebreakerRule.RANDOM_DRAW,
        ],
        description="Strict ordered hierarchy of tiebreaker criteria"
    )
    points_for_win: int = Field(default=3, description="Points awarded for group match victory")
    points_for_draw: int = Field(default=1, description="Points awarded for group match draw")
    points_for_loss: int = Field(default=0, description="Points awarded for group match defeat")
    yellow_card_suspension_threshold: int = Field(default=2, description="Yellow cards needed for 1-match suspension")
    knockout_tiebreakers: str = Field(default="Vid oavgjort i slutspel tillämpas Förlängning (2x15 min) följt av Straffsparksläggning.", description="Rule summary for knockout ties")
    qualifying_advancement_summary: Optional[str] = Field(default="", description="Rule summary for advancing from groups to knockout tree")
    official_rules_summary: Optional[str] = Field(default="", description="Human-readable rulebook summary")
