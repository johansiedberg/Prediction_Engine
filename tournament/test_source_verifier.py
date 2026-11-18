from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase

from tournament.services.source_verifier import TournamentSourceVerifier
from tournament.services.groups_teams_agent import GroupsTeamsAgent
from tournament.services.wikipedia_scout import WikipediaScout


class SourceVerifierTests(SimpleTestCase):
    def test_rejects_non_official_and_404_urls_and_uses_wikidata_p856(self):
        candidate_map = {
            "start_date": "2027-01-07",
            "end_date": "2027-02-05",
            "official_website_url": "https://www.google.com/search?q=afc",
            "groups": [{"name": "Group A", "teams": [{"name": "Saudi Arabia"}, {"name": "Qatar"}]}],
            "has_real_teams": True,
            "fixtures": [{"home_team": "Saudi Arabia", "away_team": "Palestine"}] * 4,
        }

        def fake_validate(url, timeout=6):
            if url.endswith("/home.html"):
                return ("OK", 200, url)
            return ("DEAD", 404, url)

        fake_wd = {
            "qid": "Q97359865",
            "start_date": "2027-12-23",  # Stale Wikidata date
            "end_date": "2028-01-21",
            "official_websites": ["https://www.the-afc.com/en/national/afc_asian_cup/home.html"],
        }
        fake_grounded = {
            "official_competition_url": "https://www.the-afc.com/en/national/afc_asian_cup/home.html",
            "start_date": "2027-01-07",
            "end_date": "2027-02-05",
            "dates_verified_by_official": True,
            "groups_verified_by_official": True,
            "verified_groups": [{"name": "Group A", "teams": ["Saudi Arabia", "Qatar"]}],
            "fixtures_verified_by_official": True,
            "opening_match_summary": "Saudi Arabia vs Palestine on 2027-01-07",
            "verifying_source_name": "the-afc.com",
        }

        with (
            patch.object(TournamentSourceVerifier, "validate_url", side_effect=fake_validate),
            patch.object(TournamentSourceVerifier, "fetch_wikidata_claims", return_value=fake_wd),
            patch.object(TournamentSourceVerifier, "_search_grounded_verify", return_value=fake_grounded),
        ):
            res = TournamentSourceVerifier.verify_map(
                tournament_name="2027 AFC Asian Cup",
                sport="Football",
                candidate_map=candidate_map,
                existing_official_url="https://www.the-afc.com/en/national/afc_asian_cup/",
                wiki_url="https://en.wikipedia.org/wiki/2027_AFC_Asian_Cup",
            )

        self.assertEqual(res["official_source_url"], "https://www.the-afc.com/en/national/afc_asian_cup/home.html")
        self.assertEqual(res["start_date"], "2027-01-07")
        self.assertTrue(res["all_core_verified"])
        self.assertFalse(res["has_conflict"])
        self.assertIn("Wikidata stale", res["fields"]["dates"]["note"])

    def test_wikidata_date_conflict_without_grounded_tiebreak_marks_conflict(self):
        candidate_map = {
            "start_date": "2027-01-07",
            "end_date": "2027-02-05",
            "groups": [],
            "has_real_teams": False,
            "fixtures": [],
        }
        fake_wd = {
            "qid": "Q97359865",
            "start_date": "2027-12-23",
            "end_date": "2028-01-21",
            "official_websites": [],
        }

        with (
            patch.object(TournamentSourceVerifier, "validate_url", return_value=("OK", 200, "https://example.org/cup")),
            patch.object(TournamentSourceVerifier, "fetch_wikidata_claims", return_value=fake_wd),
        ):
            res = TournamentSourceVerifier.verify_map(
                tournament_name="Test Cup 2027",
                sport="Football",
                candidate_map=candidate_map,
                existing_official_url="https://example.org/cup",
                use_grounded_search=False,
            )

        self.assertEqual(res["fields"]["dates"]["status"], "CONFLICT")
        self.assertTrue(res["has_conflict"])
        self.assertFalse(res["all_core_verified"])

    def test_403_waf_domain_falls_back_to_grounded_verification(self):
        candidate_map = {
            "start_date": "2026-12-26",
            "end_date": "2027-01-05",
            "groups": [
                {"name": "Group A", "teams": [{"name": "Sweden"}, {"name": "Finland"}]},
                {"name": "Group B", "teams": [{"name": "Canada"}, {"name": "Czechia"}]},
            ],
            "has_real_teams": True,
            "fixtures": [{"home_team": "Sweden", "away_team": "Finland"}] * 4,
        }
        fake_grounded = {
            "official_competition_url": "https://www.iihf.com/en/events/2027/wm20",
            "start_date": "2026-12-26",
            "end_date": "2027-01-05",
            "dates_verified_by_official": True,
            "groups_verified_by_official": True,
            "verified_groups": [{"name": "Group A", "teams": ["Sweden", "Finland"]}],
            "fixtures_verified_by_official": True,
            "verifying_source_name": "iihf.com",
        }

        with (
            patch.object(TournamentSourceVerifier, "validate_url", return_value=("WAF_BLOCKED", 403, "https://www.iihf.com/en/events/2027/wm20")),
            patch.object(TournamentSourceVerifier, "fetch_wikidata_claims", return_value={"qid": "Q101142528"}),
            patch.object(TournamentSourceVerifier, "_search_grounded_verify", return_value=fake_grounded),
        ):
            res = TournamentSourceVerifier.verify_map(
                tournament_name="2027 World Junior Ice Hockey Championships",
                sport="Ice Hockey",
                candidate_map=candidate_map,
                existing_official_url="https://www.iihf.com/en/events/2027/wm20",
            )

        self.assertTrue(res["all_core_verified"])
        self.assertEqual(res["fields"]["official_url"]["http_state"], "WAF_BLOCKED")
        self.assertEqual(res["fields"]["groups_teams"]["status"], "VERIFIED")

    def test_wikipedia_only_fixtures_block_grade_a_readiness(self):
        candidate_map = {
            "start_date": "2026-12-05",
            "end_date": "2026-12-13",
            "groups": [
                {"name": "Group A", "teams": [{"name": "Finland"}, {"name": "Switzerland"}]},
                {"name": "Group B", "teams": [{"name": "Sweden"}, {"name": "Czechia"}]},
            ],
            "has_real_teams": True,
            "fixtures": [{"home_team": "Finland", "away_team": "Switzerland"}] * 6,
        }
        fake_grounded = {
            "official_competition_url": "https://floorball.sport/upcoming-events/",
            "start_date": "2026-12-05",
            "end_date": "2026-12-13",
            "dates_verified_by_official": True,
            "groups_verified_by_official": True,
            "fixtures_verified_by_official": False,  # PDF/app only
            "verifying_source_name": "floorball.sport",
        }

        with (
            patch.object(TournamentSourceVerifier, "validate_url", return_value=("OK", 200, "https://floorball.sport/upcoming-events/")),
            patch.object(TournamentSourceVerifier, "fetch_wikidata_claims", return_value={"qid": "Q123741856"}),
            patch.object(TournamentSourceVerifier, "_search_grounded_verify", return_value=fake_grounded),
        ):
            res = TournamentSourceVerifier.verify_map(
                tournament_name="Men's World Floorball Championships 2026",
                sport="Floorball",
                candidate_map=candidate_map,
            )

        self.assertFalse(res["all_core_verified"])
        self.assertEqual(res["fields"]["dates"]["status"], "VERIFIED")
        self.assertEqual(res["fields"]["groups_teams"]["status"], "VERIFIED")
        self.assertEqual(res["fields"]["fixtures"]["status"], "WIKIPEDIA_ONLY")

    def test_groups_teams_agent_strips_division_pollution(self):
        audit_data = {
            "groups": [
                {"name": "Division I", "teams": []},
                {"name": "Group A", "teams": [{"name": "Sweden"}, {"name": "Finland"}]},
                {"name": "Group B", "teams": [{"name": "Canada"}, {"name": "Czechia"}]},
                {"name": "Division II", "teams": []},
            ],
            "draw_completed": True,
        }
        with patch("tournament.services.gemini_scout_service.GeminiScoutService.is_available", return_value=False):
            seg = GroupsTeamsAgent.build_groups_teams_segment(
                audit_data=audit_data,
                tournament_name="2027 World Junior Ice Hockey Championships",
                sport="Ice Hockey",
            )
        names = [g.name for g in seg.groups]
        self.assertEqual(names, ["Group A", "Group B"])

    def test_wikipedia_search_rejects_undated_umbrella_page(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "query": {
                "search": [
                    {"title": "UEFA Nations League"},
                    {"title": "2026–27 UEFA Nations League"},
                ]
            }
        }
        with patch("tournament.services.wikipedia_scout.requests.get", return_value=mock_resp):
            title = WikipediaScout().search_wikipedia_article("2026–27 UEFA Nations League")
        self.assertEqual(title, "2026–27 UEFA Nations League")
