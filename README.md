# Project Overview and Architecture: Prediction Engine v2.0

## 1. Background and Objectives

After successfully managing major tournaments—including the 2026 Football World Cup—via advanced Excel macros to run leaderboards and point calculations, this project marks the evolution into a modern, standalone web platform built with Python and Django.

The main objective of the platform is to digitize and automate the entire workflow for tournament tipping pools:

* **Automated Point Calculation:** The system automatically calculates tournament points across multiple competition stages and updates participant rankings in real time based on actual match results.
* **Flexible Pool Scoring Systems:** Pool Administrators can configure pool-specific scoring rules across 4 distinct stages (Match predictions, Group tables, Qualification tables, and Knockout advancement) plus bonus Sidebets.
* **Dual-Portal Architecture:** Strict separation between master tournament setup/administration (Engine Admin) and pool competition/member management (Player & Pool Admin).
* **AI Tournament Scout & Ingestion:** Automated scouting and ingestion of international tournament fixtures and groups using Gemini structured scouting prompts (`ScoutService` & `ScannedTournament`).
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
Access URL: `http://127.0.0.1:2029`
* **Master Tournament Creation & AI Scout:** Create tournaments manually or import scanned tournament structures via AI scouting prompts.
* **Pool Request Management:** Review, approve, or reject pool creation requests (`PoolAdminRequest`) submitted by users.
* **Result Reporting & Settlement:** Enter official match results and verify tournament state transitions.
* **Simulation & Validation:** Run test simulations and validate tournament integrity via system checklists and preview modals.

### 2. Pool Admin (Pool Manager — Port 2028)
Access URL: `http://127.0.0.1:2028/pool-admin/<league_id>/`
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
Access URL: `http://127.0.0.1:2028`
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
│   ├── settings.py           # Core settings, dual-port URL configurations
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
│   │   ├── scout_service.py  # AI tournament scout & ingestion service
│   │   ├── analytics.py      # AI match & field analysis
│   │   ├── tournament_admin.py # Tournament checklist & validation
│   │   └── pool_admin_service.py # Player progress matrix & request approval
│   │
│   ├── views/                # Modular View Packages
│   │   ├── __init__.py
│   │   ├── auth.py           # Port-aware authentication & SSO receiver
│   │   ├── engine_admin.py   # Port 2029 Engine Admin views
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
  Access at: `http://127.0.0.1:2028`

* **Engine Admin (Master System Admin):** Default Port **2029**
  ```bash
  ./venv/bin/python manage.py runserver_admin 2029
  ```
  Access at: `http://127.0.0.1:2029`

---

## 5. Development & Workflow Conventions

* **Communication Language:** Discussion and planning are conducted in **English**.
* **Code & Comments:** All code, function signatures, and comments are written in **English**.
* **App Output & UI Text:** User-facing text, labels, badges, and examples are strictly in **Swedish**.
* **Design & Aesthetics:** Dark mode glassmorphism theme, high-contrast badges, crisp typography, and responsive micro-animations.