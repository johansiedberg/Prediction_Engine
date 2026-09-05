# Prediction Engine - Version Changelog

This changelog documents the complete version history, release notes, and commit log deployed from DEV to PRD.
It serves as the definitive reference for developers and the autonomous **AntiGravity Agent** on both the Ubuntu Production Server (`192.168.86.35`) and local DEV environments.

---

## 🤖 Agent Guide: How to Read & Use This Changelog
- **Version Verification**: Compare the top version here against `git describe --tags` or `git log -n 1 --oneline`.
- **Identifying Recent Changes**: Check the latest version's **Commits from DEV** table below to understand newly deployed features, bugfixes, or refactors.
- **Migration Awareness**: Check the **Database Migrations** section for any new schema changes required before debugging model or ORM errors.
- **Service Impact**: Verify whether any changes touched port 2028 (Player app) or port 2029 (Engine Admin).

---

## [v2.7.2] - 2026-09-05 (Current Release)

### 🎯 Milestone Highlights
- **Scraper Ingestion & Fixture Deduplication (Floorball & Multi-Sport)**:
  - **Strategy Overlap Prevention**: Prevented Strategy 3b NLP table mining from reprocessing match rows inside containers (`fevent`, `vevent`, `footballbox`) already handled by Strategies 1 and 2 in `wikipedia_scout.py`, eliminating corrupted duplicates where trailing venue strings were captured into away team names.
  - **Hyphenated Stage Header Recognition**: Expanded `get_preceding_stage` regex to match `play[\s\-]off`, `knock[\s\-]out`, `bracket`, `bronze`, and `placement`, ensuring playoff matches are properly categorized rather than cascading into the preceding group (e.g. `Group D`).
  - **Venue Suffix Sanitization**: Expanded `_clean_team_name` in `llm_wikipedia_scout.py` to strip Nordic and European arenas, sports halls, and cities (`Kauppi`, `Hakametsä`, `Nokia`, `Ice Hall`, `Sports Center`, `Tampere`, etc.).
  - **Intelligent Team Snapping & Deduplication**:
    - In `matches_knockout_agent.py`, added team snapping against known group teams and expanded knockout stage regex, guaranteeing candidate teams snap to authentic names and deduplicate.
    - In `scout_service.py` (`convert_scanned_to_live_tournament`), added team snapping against created teams, dynamic stage resolution, and duplicate match prevention.
  - **Database Cleanup (PRD & DEV)**:
    - Purged 24 corrupted duplicate matches (matches 40–63) and 8 generic skeleton placeholders from *Men's World Floorball Championships 2026*.
    - Reassigned playoff matches (matches 25–28) from `Group D` to a dedicated `Play-off round` knockout stage with `group=None`.
  - **Qualifying Tables & Best Thirds Conditional Gating**:
    - Strictly gated the "Bästa Treor", "Rankade Grupptvåor", and "Ranking Värdnationer" section buttons and tab content by `active_tournament.has_best_thirds_table`, `has_runners_up_table`, and `has_host_ranking_table`.
    - Fixed `hasBestThirdsTable` and `isQualifyingTournament` in `predictions_content.html` standings JS to reflect actual tournament settings instead of defaulting to true for all non-qualifying tournaments, correctly rendering clean 2-team direct qualification lines for tournaments without a cross-group ranking table (e.g. *Men's World Floorball Championships 2026*).
    - In `dashboard.py`, set `thirds_prediction_status = None` when neither `has_best_thirds_table` nor `has_runners_up_table` is enabled.

### 📋 Commits from DEV (v2.7.1 -> v2.7.2)
| Commit SHA | Type | Description |
| :--- | :--- | :--- |
| `7567beb` | `fix(scout)` | Prevent duplicate venue-mangled matches and fix hyphenated playoff stages |
| `9ded4b9` | `fix(predictions)` | Gate Best Thirds and qualifying tables by tournament configuration |

---

## [v2.7.1] - 2026-09-05

### 🎯 Milestone Highlights
- **Webscan HTTP 500 & Gunicorn Worker Timeout Resolution**:
  - Capped AI date lookups in `resolve_and_filter_prospect_dates` to newly ingested prospects and max 5 queries per scrape to prevent long worker blocking.
  - Updated `SUPPORTED_MODELS` in `GeminiScoutService` to active models: `gemini-flash-latest`, `gemini-flash-lite-latest`, `gemini-3.1-flash-lite`, and `gemini-3.8-flash`.
  - Added fast-fail `is_in_penalty()` bypass on Gemini rate limiter to instantly skip fallback attempts when quota is in cooldown.
  - Extended Gunicorn worker timeout to 300s in `prediction-admin.service` on PRD.
  - Improved user feedback in Engine Admin when zero new prospects are discovered.
- **Scoring Engine Parity & Knockout Advancement**:
  - Centralized knockout point calculation in `tournament/services/scoring.py` with canonical helpers `get_knockout_stage_point_value`, `get_third_place_qualifying_point_value`, and `evaluate_knockout_prediction_match`.
  - Fixed hardcoded `tp_pts = 0` in `CacheService` to correctly reward third-place predictions.
  - Aligned `dashboard.py` and `CacheService` for dual-phase prediction scoring (`INITIAL_BRACKET` and `ACTUAL_KNOCKOUT`).
- **Sport Categorization & Field Hockey / EuroHockey Resolution**:
  - Expanded `detect_sport_from_title` in `tournament_filter.py` with word-boundary keyword matching across all H2H team sports (`Field Hockey`, `Cricket`, `Netball`, `American Football`, `Water Polo`, `Lacrosse`, `Bandy`).
  - Unified `infer_sport_from_title` in `scout_service.py` to delegate directly to `detect_sport_from_title`, preventing keyword drift and false Football fallbacks.
  - Added infobox row and lead paragraph sport extraction to `WikipediaScout.audit_infobox_only()`.
  - Expanded `ALLSPORTDB_SPORTS_MAP` and updated `infer_sport` in `dashboard.py` to recognize `Field Hockey` (`🏑`), `Netball` (`🏐`), `Cricket` (`🏏`), and `American Football` (`🏈`).
  - Updated Engine Admin Section 1 and JavaScript sport badge rendering for `Field Hockey` (`🏑 Landhockey`) and other H2H sports.
- **My Predictions Navigation & Glowing Button Status**:
  - Removed text underline from section buttons (`#tournamentTab .nav-link`) in `predictions_content.html`.
  - Added glowing bottom borders with 4 status indicators:
    - **Green**: Predictions all set (all matches and questions completed).
    - **Red**: Predictions not set (unpredicted or incomplete matches/questions).
    - **Blue**: Predictions not applicable yet (e.g. *Äkta Slutspel* before actual knockout stage opens, or *Bästa Treor* before all group predictions are filled).
    - **Grey**: Predictions not needed at all (e.g. Qualifying tables such as *Rankade Grupptvåor* and *Ranking Värdnationer*).
  - Implemented real-time dynamic glow updates (`updateSectionButtonGlows()`) on score inputs, tiebreaker clicks, and tab switching.

### 📦 Database Migrations Introduced
- `0067_alter_staticinsight_category`: Updated category choices for static insights almanac.

### 📋 Commits from DEV (v2.7.0 -> v2.7.1)
| Commit SHA | Type | Description |
| :--- | :--- | :--- |
| `5391a16` | `feat(scout)` | Fix webscan timeout, rate limiter cascade, and scoring engine parity |
| `6b884d1` | `style(predictions)` | Add glowing bottom status (Green, Red, Blue, Grey) to section buttons |

---

## [v2.7.0] - 2026-09-03


### 🎯 Milestone Highlights
- **AI Tournament Scout & Gemini 3.8 Flash**:
  - Upgraded AI Scout default model to Google Gemini 3.8 Flash (`gemini-3.8-flash`).
  - Added automated graceful fallback for search grounding HTTP 429 errors (retries immediately without grounding and bypasses the 60s cooldown penalty).
  - Robust JSON parser supporting both arrays `[...]` and objects `{...}` across all sub-agents.
  - Title year regex filtering purging past tournaments with null start dates.
  - Fixed property assignment safety on `prospect.payload['scouting_audit']['next_rescan_date']`.
- **Actual Knockout Dual Predictions & Dynamic Stage Gazette**:
  - Implemented dual prediction lifecycle: participants make initial bracket predictions (`INITIAL_BRACKET`) and update predictions during the actual knockout window (`ACTUAL_KNOCKOUT`).
  - Automated knockout window state detection and kickoff locking.
  - Tournament Editorial Engine v2.0 & v2.1 with dynamic multi-role avatars and stage gazette.
- **Test Suite Performance & Hermetic Safety**:
  - **11x Speedup**: Total test suite runtime dropped from **246.98s (~4.1 min)** down to **17.39s**.
  - **Zero Gemini Quota Spent**: All 120 tests run hermetically offline with zero live Gemini API or external network calls.
  - **Opt-In Live API Protection**: Live API tests isolated behind `@tag('live_api')` and `RUN_LIVE_GEMINI_TESTS=1` gating with explicit user permission.
  - **Fast MD5 Password Hasher**: Enabled `MD5PasswordHasher` exclusively for test runs (`if 'test' in sys.argv`).

### 📦 Database Migrations Introduced
- `0065_expanded_static_insight_categories`: Expanded static insight categories for editorial engine.
- `0066_actual_knockout_dual_predictions`: Added support for dual match prediction phases (`INITIAL_BRACKET` / `ACTUAL_KNOCKOUT`).

### 📋 Commits from DEV (v2.6.0 -> v2.7.0)
| Commit SHA | Type | Description |
| :--- | :--- | :--- |
| `6aa9f1a` | `perf(test)` | Add fast password hasher for test runner and cache isolation (22s full suite) |
| `91345b1` | `feat(test)` | Optimize test suite to hermetic offline mocks and add Flash 3.8 regression tests |
| `1fe0f68` | `fix(scout)` | Optimize Webscan and Deepscan for Gemini 3.8 Flash and graceful fallback |
| `3bf4e0e` | `chore` | Add gemini-3.8-flash, fix test suite, update documentation, and clean root |
| `74e24b1` | `feat` | Enhance tournament insight cards and knockout match card sizing |
| `6d78ffc` | `feat` | Implement actual knockout stage prediction and centered tiebreaker toggle |
| `c144dda` | `feat` | Enhance result styling, strict qualifying points, separate bronze stage, and progressive knockout bracket build-up |
| `3bee437` | `feat` | Editorial multi-role engine v2.1, avatar postures, and header redesign |
| `410c2a4` | `feat(gazette)`| Add default cover image for all non-Toarp pools |
| `89667d9` | `chore(db)` | Add migration 0065 for expanded static insight categories |
| `f1b8ff5` | `feat` | Implement tournament editorial engine v2.0 & dynamic stage gazette |

---

## [v2.6.0] - 2026-08-29

### 🎯 Milestone Highlights
- **Prediction Lifecycle & Top Action Bar**:
  - Added floating top action bar with lit save button indicating unsaved predictions.
  - Automated kickoff locking preventing edits after match start times.
  - Enhanced Pool Admin dashboard with real-time submission verification and member status tracking.
- **Visual Polish & Assets**:
  - Added default tournament emblem assets (PNG/WebP).
  - Modernized card layouts across player dashboard and predictions view.

### 📋 Commits from DEV (v2.5.0 -> v2.6.0)
| Commit SHA | Type | Description |
| :--- | :--- | :--- |
| `71278c9` | `feat` | Prediction lifecycle, top action bar with lit save button, kickoff auto-lock, and pool-admin enhancements |

---

## [v2.5.0] - 2026-08-27

### 🎯 Milestone Highlights
- **Initial Production Release Blueprint**:
  - Dual-portal Django architecture behind Caddy HTTPS reverse proxy (Port 2028 Player / Port 2029 Engine Admin).
  - Tri-Pillar AI Scout Architecture (5 modular sub-agents for shallow and deep tournament scouting).
  - Strict 30-day runway buffer filtering and date normalization hierarchy.
  - Monochromatic tonal contrast system and WCAG AAA compliance.
  - Superuser isolation: `johansiedberg` strictly restricted to port 2029 engine administration.

### 📦 Database Migrations Introduced
- `0061` through `0064`: Core schema migrations for multi-stage tournaments, point systems, and AI scout prospect models.
