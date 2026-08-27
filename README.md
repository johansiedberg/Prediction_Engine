# Project Overview and Architecture: Prediction Engine v2.5

> [!NOTE]
> **Production Specification & Recent Changelog**: See [PRD_RELEASE_BLUEPRINT.md](file:///Users/johansiedberg/Documents/GitHub/Prediction_Engine/PRD_RELEASE_BLUEPRINT.md) for the complete August 24–27, 2026 system release notes, database migration index (`0061`–`0064`), and Ubuntu PRD activation runbook.

## 1. Background and Objectives

After successfully managing major tournaments—including the 2026 Football World Cup—via advanced Excel macros to run leaderboards and point calculations, this project marks the evolution into a modern, standalone web platform built with Python and Django.

The main objective of the platform is to digitize and automate the entire workflow for tournament tipping pools:

* **Automated Point Calculation:** The system automatically calculates tournament points across multiple competition stages and updates participant rankings in real time based on actual match results.
* **Flexible Pool Scoring Systems:** Pool Administrators can configure pool-specific scoring rules across 4 distinct stages (Match predictions, Group tables, Qualification tables, and Knockout advancement) plus bonus Sidebets.
* **Dual-Portal Architecture:** Strict separation between master tournament setup/administration (Engine Admin) and pool competition/member management (Player & Pool Admin).
* **AI Tournament Scout & 5-Segment Deepscan Engine:** Modular AI architecture (`ModularDeepScout`, `GeminiScoutService`, and 5 dedicated sub-agents) automating shallow ingestion and deep auditing of international tournaments with strict 30-day runway filtering and zero-latency bracket token resolution.
* **High-Performance Caching & Indexing:** Multi-layer cache service and optimized database indexes for lightning-fast leaderboard and prediction calculations.
* **AI Match & Field Analytics:** Dynamic AI-generated editorial summaries providing match analysis, individual tips, outliers, and rivalry banter.

---

## 2. System Structure and User Roles

The application features three interaction roles across two dedicated development servers:

```
                  ┌─────────────────────────────────────────┐
                  │          PREDICTION ENGINE CORE         │
                  └────────────────────┬────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
 ┌─────────────────────┐                               ┌─────────────────────┐
 │    ENGINE ADMIN     │                               │ PLAYER & POOL ADMIN │
 │     (Port 2029)     │                               │     (Port 2028)     │
 └──────────┬──────────┘                               └──────────┬──────────┘
            │                                                     │
 ┌──────────┴──────────┐                               ┌──────────┴──────────┐
 │ • Master Tournaments│                               │ • Pool Admin Hub    │
 │ • AI Scout Ingestion│                               │ • Rule Configuration│
 │ • Approve Pools     │                               │ • Member Status     │
 │ • Result Reporting  │                               │ • Player Tipping    │
 │ • Tournament Sim    │                               │ • Live Leaderboard  │
 └─────────────────────┘                               └─────────────────────┘
```

### 1. Engine Admin (System Master — Port 2029)
Access URL: `https://127.0.0.1:2029` (or `http://` in local dev)

> [!IMPORTANT]
> **Strict Engine Admin Isolation & Global Scope:**
> The **Engine Admin** (Port 2029) is strictly a system maintenance and platform infrastructure function dedicated to the Prediction Engine itself. It operates in a global capacity, allowing the platform to act as a commercial or multi-tenant tipping engine.
> * **Zero Member / Pool Connection:** Engine Admin cannot and shall not have any connection to members of Herrklubben, Pool Administrators, or Prediction Players.
> * **Complete Decoupling:** The Engine Admin does not belong to any tipping pool, does not manage individual pools, and cannot submit predictions or participate as a player.

* **Master Tournament Creation & AI Scout:** Create tournaments manually or import scanned tournament structures via AI scouting prompts.
* **Pool Request Management:** Review, approve, or reject pool creation requests (`PoolAdminRequest`) submitted by users.
* **Result Reporting & Settlement:** Enter official match results and verify tournament state transitions.
* **Simulation & Validation:** Run test simulations and validate tournament integrity via system checklists and preview modals.

### 2. Pool Admin (Pool Manager — Port 2028)
Access URL: `https://127.0.0.1:2028/pool-admin/<league_id>/` (or `http://` in local dev)
* **Pool Admin Hub:** Centralized hub for managing active pools and tournament rule configurations (`pool_admin_hub.html`).
* **Custom Pool Branding:** Customize pool logo, header banner, and primary accent color.
* **Member Verification:** Manage pool participants, verify player submissions, and track prediction completion matrices.
* **4-Stage Point Rule Configuration:**
  * **Etapp 1 (Matcher):** 1X2 outcome, exact match score, goals per team, goal difference.
  * **Etapp 2 (Grupptabeller):** Exact group rank, correct points, scored goals, conceded goals, goal diff.
  * **Etapp 3 (Kvalificeringstabell):** Point rules for third-place rankings / runners-up tables.
  * **Etapp 4 (Slutspel, avancemang):** Stage advancement bonuses for Åttondelsfinal, Kvartsfinal, Semifinal, Bronsmatch, and Final.
  * **Sidebets:** Configure bonus questions (e.g., top scorer, tournament winner).

### 3. Player (Participant — Port 2028)
Access URL: `https://127.0.0.1:2028` (or `http://` in local dev)
* **Interactive Prediction Sheet:** Submit predictions for group matches, knockout stages, and sidebets.
* **Dynamic Leaderboard & Live Standings:** Real-time point updates, position tracking, and historical performance breakdowns powered by `cache_service`.
* **AI Match Analytics:** Banter-rich, tailored commentary comparing user predictions with group trends.

---

## 3. Directory Tree and Architecture

The codebase follows a decoupled architecture separating business logic (services), HTTP handlers (views), and database models:

```text
PREDICTION_ENGINE/
│
├── core/
│   ├── settings.py           # Core settings, rate limiters, dual-port URL configurations
│   ├── urls.py               # Master routing
│   ├── asgi.py & wsgi.py
│
├── templates/
│   └── tournament/
│       ├── base.html         # Main aesthetic layout
│       ├── pool_admin_hub.html # Pool Admin master league hub
│       ├── pool_admin_tournament_config.html # Pool 4-stage point rule configuration
│       ├── engine_admin.html # Engine Admin master portal & simulation
│       ├── engine_admin_preview_modal.html # Engine Admin tournament preview
│       ├── hub.html          # Player hub & predictions dashboard
│       ├── login.html
│       ├── register.html
│       └── request_pool_admin.html
│
├── tournament/
│   ├── services/             # Pure Business Logic Service Layer
│   │   ├── __init__.py
│   │   ├── scoring.py        # Point calculation engine
│   │   ├── cache_service.py  # Multi-layer leaderboard & prediction caching
│   │   ├── scout_service.py  # Shallow ingestion & prospect synchronization
│   │   ├── modular_deep_scout.py # Stage 2–4 5-Segment Deepscan Orchestrator
│   │   ├── head_discovery_agent.py   # Segment 1: Head Discovery Agent
│   │   ├── general_deep_scout_agent.py # Segment 2: General & Emblem Agent
│   │   ├── structure_rules_agent.py  # Segment 3: Structure & Rules Agent
│   │   ├── groups_teams_agent.py     # Segment 4: Groups & Teams Agent
│   │   ├── matches_knockout_agent.py # Segment 5: Matches & Knockout Agent
│   │   ├── gemini_scout_service.py   # Central Gemini AI Client & Grounding
│   │   ├── gemini_rate_limiter.py    # Sliding window 14 RPM rate limiter
│   │   ├── team_badge_service.py     # 4-tier team badge & bracket slot resolver
│   │   ├── llm_wikipedia_scout.py    # Grounded Wikipedia scraping & date parsing
│   │   ├── analytics.py      # AI match & field analysis
│   │   ├── tournament_admin.py # Tournament checklist & validation
│   │   └── pool_admin_service.py # Player progress matrix & request approval
│   │
│   ├── schemas/              # Pydantic Structural Schemas
│   │   ├── __init__.py
│   │   └── tournament_prospect_schema.py # Unified 5-Segment Prospect Blueprint
│   │
│   ├── views/                # Modular View Packages
│   │   ├── __init__.py
│   │   ├── auth.py           # Port-aware authentication & SSO receiver
│   │   ├── engine_admin/     # Port 2029 Engine Admin split views (scout, dashboard, etc.)
│   │   ├── pool_admin.py     # Port 2028 Pool Admin views
│   │   ├── dashboard.py      # Leaderboard, predictions & overview
│   │   └── match_views.py    # Predictions & score updates
│   │
│   ├── editorial_engine/     # AI Reporter & Match Commentary Generators
│   ├── management/commands/
│   │   ├── runserver.py      # Player server runner (Port 2028)
│   │   ├── runserver_admin.py# Engine Admin runner (Port 2029)
│   │   ├── seed_members.py   # Seeds 11 core members & admin user
│   │   ├── setup_euro2028_final.py # Seed Euro 2028 tournament structure
│   │   ├── setup_euro2028_qualifiers.py
│   │   ├── setup_wfc_2026.py # Seed World Floorball Championships 2026
│   │   └── setup_womens_euro_volleyball_2026.py
│   │
│   ├── fixtures/
│   │   └── initial_data.json # Initial user accounts and profile fixtures
│   │
│   ├── models.py             # Tournament, Match, League, PointSystem, ScannedTournament
│   ├── admin.py              # Django Admin registrations
│   ├── forms.py              # User & pool forms
│   ├── urls.py               # Application URL routes
│   └── middleware.py         # Port-based access control middleware
│
├── GEMINI_TOURNAMENT_SCOUT_PROMPT.txt # AI Tournament Scout extraction template
├── db.sqlite3
├── manage.py
└── README.md
```

---

## 4. Development & Server Commands

### Database & User Seeding

To initialize all user accounts and league configurations:
```bash
# Option A: Run automated seeder command
./venv/bin/python manage.py seed_members

# Option B: Load serialized initial user fixture
./venv/bin/python manage.py loaddata tournament/fixtures/initial_data.json
```

### Running Local Servers

* **Prediction Engine (Player App & Pool Admin):** Default Port **2028**
  ```bash
  ./venv/bin/python manage.py runserver 2028
  ```
  Access at: `https://127.0.0.1:2028` (or `http://` in local dev)

* **Engine Admin (Master System Admin):** Default Port **2029**
  ```bash
  ./venv/bin/python manage.py runserver_admin 2029
  ```
  Access at: `https://127.0.0.1:2029` (or `http://` in local dev)

---

## 5. Development & Workflow Conventions

* **Communication Language:** Discussion and planning are conducted in **English**.
* **Code & Comments:** All code, function signatures, and comments are written in **English**.
* **App Output & UI Text:** User-facing text, labels, badges, and examples are strictly in **Swedish**.
* **Antigravity Agent Permission & Workflow Control Rules:**
  * **Direct UI/UX Execution**: When the user explicitly requests UI/UX changes, the agent executes them directly without intermediate plan gating.
  * **Collateral UI/UX Review Gate**: When UI/UX modifications are part of a wider code feature/refactor (not explicitly requested as UI/UX by the user), the agent MUST present a proposed plan detailing the UI changes and await user confirmation before modifying UI files.
  * **Mandatory Plan Review**: Any prompt requesting a goal or implementation plan requires creating `implementation_plan.md`, setting `request_feedback: true`, and waiting for explicit user approval before execution.
  * **Autonomous Command Execution**: Once a plan is approved by the user, tool calls and background operations execute autonomously in batched sequences without turn-by-turn permission prompts.
* **Icon & Emoji Visual Spacing Standard:**
  * All icons (`<i class="...">`) and emojis (e.g. 🏆, ⚽, ⏱️, ✅, 🛡️) MUST maintain a minimum **5px–6px** visual gap (or two space units / flex gap) from adjacent text elements.
  * Emojis and icons must NEVER directly touch text characters without explicit padding/margin or space delimiters.
  * Use utility classes `.icon-gap`, `.emoji-gap`, `me-1.5`, `me-2`, or `d-inline-flex align-items-center gap-2`.
* **Monochromatic Tonal Contrast & Legibility System:**
  * All banners, cards, badges, and alert notifications use strict monochromatic tonal contrast token sets for maximum readability (minimum 4.5:1 text WCAG AA contrast ratio).
  * Status states (Success, Warning, Danger, Info, Neutral) utilize paired background, border, text, and icon tokens in both Light and Dark mode.
  * Dark mode uses reversed polarity with deep tone surfaces (~10% lightness), mid-dark borders (~35% lightness), and pale tint text/icons (~85–90% lightness) to avoid glare and chromatic aberration.
  * Multi-modal signaling pairs visual color with explicit status icons and descriptive text labels.
* **Tab State Persistence Standard:**
  * Tab navigation states in Engine Admin (`engine_admin.html`) persist in `localStorage` (`engineAdminActiveTab`) and URL hashes, restoring the active tab section seamlessly on page reload.
* **AI Tournament Scout Date Validation & 30-Day Runway Rule:**
  * The scout engine is dedicated to upcoming tournaments for Pool-Admin creation. Any tournament with `start_date < today + 30 days` (past or imminent) is immediately rejected/discarded at both shallow web ingestion and deepscan stages.
  * All date extractions strictly normalize to `YYYY-MM-DD` (falling back to `YYYY-MM-01` or `YYYY-01-01`) to prevent null-comparison bypasses.
  * Multi-tiered early rejection triggers at Step 0 (Title regex), Step 0.5 (Intermediate header audit), and during umbrella disambiguation splitting.
* **Gemini AI Rate Limiting & High-Performance Scouting Standard:**
  * Standardized on `gemini-flash-lite-latest` with a strict 14 RPM governor (`GEMINI_MAX_CALLS_PER_MINUTE = 14`) via `GeminiRateLimiter` to eliminate 60s 429 quota punishment blocks.
  * Bracket slot tokens (`1A`, `2B`, `3C/E/F`, `W73`, `Lag #1`, `Vinnare M1`, `Guld`) are resolved in **0.00ms** by `TeamBadgeService.is_placeholder` without making external Wikidata or DB queries.
  * Matches & Knockout sub-agent skips redundant Gemini fixture searches when the draw is pending or when full fixtures are already parsed from Wikipedia.