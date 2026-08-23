"""
Unit Tests for Modular 5-Segment Scouting Pipeline
===================================================
Validates:
1. Pydantic schema validation for HeadSegment, GeneralSegment, StructureAndRulesSegment, GroupsAndTeamsSegment, MatchesAndKnockoutSegment.
2. HeadDiscoveryAgent (H2H eligibility, slug generation).
3. GeneralDeepScoutAgent (Dates, location, emblem format scoring).
4. StructureRulesAgent (Points system, tiebreaker hierarchy, qualifying tables math).
5. GroupsTeamsAgent (Group parsing, real teams vs placeholders detection).
6. MatchesKnockoutAgent (Fixtures schedule, advancement mapping, knockout tree).
7. Unified TournamentProspectBlueprint export and roundtrip.
"""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

import unittest
from tournament.schemas.tournament_prospect_schema import (
    TournamentProspectBlueprint,
    HeadSegment,
    GeneralSegment,
    LocationInfo,
    EmblemInfo,
    StructureAndRulesSegment,
    GeneralSetup,
    GroupStageRules,
    QualifyingTablesRules,
    KnockoutRules,
    TiebreakerStep,
    GroupsAndTeamsSegment,
    GroupEntry,
    TeamEntry,
    MatchesAndKnockoutSegment,
    GroupMatchEntry,
    AdvancementFixtureEntry,
    KnockoutStageEntry,
    KnockoutMatchEntry,
    ScoutingAudit,
    CompletenessGrade,
    ScoutingStage,
)
from tournament.services.head_discovery_agent import HeadDiscoveryAgent
from tournament.services.general_deep_scout_agent import GeneralDeepScoutAgent
from tournament.services.structure_rules_agent import StructureRulesAgent
from tournament.services.groups_teams_agent import GroupsTeamsAgent
from tournament.services.matches_knockout_agent import MatchesKnockoutAgent


class TestModularSegments(unittest.TestCase):

    def test_head_discovery_agent(self):
        """Tests shallow head discovery and sport validation."""
        head = HeadDiscoveryAgent.build_head_segment(
            name="2026 FIFA World Cup",
            sport="Football",
            start_date="2026-06-11",
            discovery_source="AllSportDB",
        )
        self.assertEqual(head.name, "2026 FIFA World Cup")
        self.assertEqual(head.master_event_code, "2026-fifa-world-cup")
        self.assertTrue(head.is_h2h_team_sport)
        self.assertEqual(head.start_date, "2026-06-11")

    def test_general_deep_scout_agent(self):
        """Tests general segment parsing with location and emblem metadata."""
        agent = GeneralDeepScoutAgent()
        audit_mock = {
            "start_date": "2026-06-11",
            "end_date": "2026-07-19",
            "host_country": "United States, Canada, Mexico",
            "host_cities": ["New York", "Los Angeles", "Mexico City"],
            "organizer": "FIFA",
            "logo_url": "https://upload.wikimedia.org/wikipedia/commons/test_logo.svg",
        }
        gen = agent.build_general_segment(
            tournament_name="2026 FIFA World Cup",
            audit_data=audit_mock,
            wikipedia_title="2026_FIFA_World_Cup",
        )
        self.assertEqual(gen.start_date, "2026-06-11")
        self.assertEqual(gen.end_date, "2026-07-19")
        self.assertEqual(gen.location.host_country, "United States / Canada / Mexico")
        self.assertEqual(len(gen.location.host_cities), 3)
        self.assertTrue(gen.emblem.is_vector)
        self.assertTrue(gen.emblem.is_transparent)
        self.assertEqual(gen.organizer, "FIFA")

    def test_structure_rules_agent(self):
        """Tests points, tiebreakers, and qualifying table calculations."""
        audit_mock = {
            "draw_date": "2025-12-05",
            "draw_completed": True,
            "points_system": {"win": 3, "draw": 1, "loss": 0},
            "advancement_logic": {
                "teams_per_group_advancing": 2,
                "has_best_thirds_table": True,
                "best_third_placed_advancing": 8,
            },
            "match_format": {
                "regular_time_minutes": 90,
                "extra_time_minutes": 30,
                "has_penalties": True,
            },
            "knockout_stages": ["Round of 32", "Round of 16", "Quarterfinals", "Semifinals", "Final"],
        }
        struct = StructureRulesAgent.build_structure_rules_segment(audit_data=audit_mock)
        self.assertEqual(struct.general_setup.draw_date, "2025-12-05")
        self.assertTrue(struct.general_setup.draw_completed)
        self.assertEqual(struct.group_stage_rules.points_win, 3)
        self.assertEqual(struct.group_stage_rules.teams_per_group_advancing, 2)
        self.assertTrue(struct.qualifying_tables_rules.has_best_thirds)
        self.assertEqual(struct.qualifying_tables_rules.best_thirds_count, 8)
        self.assertEqual(struct.knockout_rules.starting_round, "Round of 32")
        self.assertEqual(struct.knockout_rules.total_rounds, 5)
        self.assertTrue(struct.knockout_rules.has_penalties)

    def test_groups_teams_agent(self):
        """Tests group table parsing and real team vs placeholder classification."""
        audit_mock = {
            "groups": [
                {
                    "name": "Group A",
                    "teams": [
                        {"name": "Mexico", "code": "MEX"},
                        {"name": "South Africa", "code": "RSA"},
                        {"name": "A3 (TBD)", "code": "A3"},
                        {"name": "A4 (TBD)", "code": "A4"},
                    ]
                }
            ]
        }
        groups_seg = GroupsTeamsAgent.build_groups_teams_segment(audit_data=audit_mock)
        self.assertEqual(groups_seg.groups_count, 1)
        self.assertEqual(groups_seg.teams_count, 4)
        self.assertFalse(groups_seg.groups[0].teams[0].is_placeholder)
        self.assertTrue(groups_seg.groups[0].teams[2].is_placeholder)

    def test_matches_knockout_agent(self):
        """Tests fixture generation and knockout bracket tree mapping."""
        audit_mock = {
            "fixtures": [
                {
                    "match_number": 1,
                    "stage_or_group": "Group A",
                    "home_team": "Mexico",
                    "away_team": "South Africa",
                    "date_time": "2026-06-11 15:00",
                    "venue": "Estadio Azteca",
                }
            ],
            "knockout_stages": [
                {
                    "stage_name": "Round of 32",
                    "matches": [
                        {"match_code": "R32_1", "home_team": "1A", "away_team": "3C/E/F"}
                    ]
                }
            ]
        }
        matches_seg = MatchesKnockoutAgent.build_matches_knockout_segment(audit_data=audit_mock)
        self.assertEqual(matches_seg.total_matches, 2)
        self.assertEqual(matches_seg.group_matches[0].home_team, "Mexico")
        self.assertEqual(len(matches_seg.knockout_bracket), 1)
        self.assertEqual(matches_seg.knockout_bracket[0].stage_name, "Round of 32")
        self.assertEqual(matches_seg.group_matches[0].home_team, "Mexico")
        self.assertEqual(len(matches_seg.knockout_bracket), 1)
        self.assertEqual(matches_seg.knockout_bracket[0].stage_name, "Round of 32")

    def test_unified_blueprint_payload_dict(self):
        """Tests complete 5-segment TournamentProspectBlueprint export to persistent dict."""
        blueprint = TournamentProspectBlueprint(
            head_segment=HeadSegment(
                name="2026 FIFA World Cup",
                master_event_code="2026-fifa-world-cup",
                sport="Football",
                start_date="2026-06-11",
            ),
            general_segment=GeneralSegment(
                start_date="2026-06-11",
                end_date="2026-07-19",
                location=LocationInfo(host_country="USA"),
                emblem=EmblemInfo(logo_url="https://example.com/logo.svg", is_vector=True),
                organizer="FIFA",
            ),
            structure_and_rules_segment=StructureAndRulesSegment(
                general_setup=GeneralSetup(draw_date="2025-12-05", draw_completed=True),
                group_stage_rules=GroupStageRules(points_win=3, teams_per_group_advancing=2),
                qualifying_tables_rules=QualifyingTablesRules(has_best_thirds=True, best_thirds_count=8),
                knockout_rules=KnockoutRules(starting_round="Round of 32", total_rounds=5),
            ),
            groups_and_teams_segment=GroupsAndTeamsSegment(
                groups_count=1,
                teams_count=4,
                has_real_teams=True,
                groups=[
                    GroupEntry(
                        name="Group A",
                        teams=[TeamEntry(name="Mexico", code="MEX")]
                    )
                ]
            ),
            matches_and_knockout_segment=MatchesAndKnockoutSegment(
                total_matches=1,
                fixtures_completed=True,
                group_matches=[
                    GroupMatchEntry(match_number=1, home_team="Mexico", away_team="USA")
                ]
            ),
            scouting_audit=ScoutingAudit(
                stage=ScoutingStage.DEEP,
                completeness_grade=CompletenessGrade.GRADE_A,
            )
        )
        payload = blueprint.to_payload_dict()
        self.assertIn("head_segment", payload)
        self.assertIn("general_segment", payload)
        self.assertIn("structure_and_rules_segment", payload)
        self.assertIn("groups_and_teams_segment", payload)
        self.assertIn("matches_and_knockout_segment", payload)
        self.assertEqual(payload["master_event"]["name"], "2026 FIFA World Cup")
        self.assertEqual(payload["points_system"]["win"], 3)
        self.assertTrue(payload["advancement_logic"]["has_best_thirds_table"])
        self.assertEqual(payload["advancement_logic"]["best_third_placed_advancing"], 8)

    def test_normalize_multiple_locations(self):
        from tournament.services.scout_service import normalize_locations
        self.assertEqual(normalize_locations("Saudi Arabia"), "Saudi Arabia")
        self.assertEqual(normalize_locations("Kenya Tanzania Uganda"), "Kenya / Tanzania / Uganda")
        self.assertEqual(normalize_locations("Italy Turkey"), "Italy / Turkey")
        self.assertEqual(normalize_locations("England Republic of Ireland Scotland Wales"), "England / Republic of Ireland / Scotland / Wales")
        self.assertEqual(normalize_locations("Czech Republic Poland Romania Slovakia Turkey"), "Czech Republic / Poland / Romania / Slovakia / Turkey")
        self.assertEqual(normalize_locations("South Africa Zimbabwe Namibia"), "South Africa / Zimbabwe / Namibia")
        self.assertEqual(normalize_locations("Morocco Portugal Spain [ A ] [ B ]"), "Morocco / Portugal / Spain")
        self.assertEqual(normalize_locations("Spain, Portugal & Switzerland"), "Spain / Portugal / Switzerland")
        self.assertEqual(normalize_locations("United Kingdom & Republic of Ireland"), "United Kingdom / Republic of Ireland")
        self.assertEqual(normalize_locations("Bulgaria Finland Italy Romania"), "Bulgaria / Finland / Italy / Romania")
        self.assertEqual(normalize_locations("USA, Canada, Mexico"), "USA / Canada / Mexico")
        self.assertEqual(normalize_locations("USA / Canada / Mexico"), "USA / Canada / Mexico")
        self.assertEqual(normalize_locations(["USA", "Canada", "Mexico"]), "USA / Canada / Mexico")


if __name__ == "__main__":
    unittest.main()

