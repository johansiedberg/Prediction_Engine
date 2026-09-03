# Prediction Engine - Production Release Blueprint & System Specification
**Release Version**: `v2.7.0` | **Date**: September 3, 2026 | **Target**: Ubuntu Production Server (`192.168.86.35`)

---

## 📌 Executive Summary
This document provides the definitive, comprehensive architectural specification and system overview of all features, schema migrations, UI/UX systems, and background services introduced through **v2.7.0** (August 24 – September 3, 2026).

For the complete chronologically ordered commit log and detailed developer changes deployed from DEV, see **[CHANGELOG.md](CHANGELOG.md)**.

This blueprint serves as the single source of truth for developers and the autonomous **AntiGravity Agent** on the Ubuntu PRD server to understand, verify, and operate the platform.

---

## 🌐 1. Production Architecture & Port Map

The Prediction Engine operates as a dual-portal Django application behind a Caddy reverse proxy providing automatic HTTPS termination.

```
                  ┌─────────────────────────────────────────┐
                  │          Internet / Clients             │
                  └────────────────────┬────────────────────┘
                                       │
                    HTTPS (Port 2028)  │  HTTPS (Port 2029)
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │     Caddy HTTPS Reverse Proxy           │
                  └─────────┬─────────────────────┬─────────┘
                            │                     │
                Proxy to    │         Proxy to    │
             127.0.0.1:8028 │      127.0.0.1:8029 │
                            ▼                     ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
│  Player Application (Port 8028)      │  │  Engine Admin Portal (Port 8029)     │
│  - Participant Predictions & Hub     │  │  - System Dashboard & Monitor       │
│  - Pool Admin Management             │  │  - AI Tournament Scout Studio       │
│  - Magic Link Passwordless Auth      │  │  - Format Blueprint Configurator     │
│  - Terms & Conditions Onboarding     │  │  - Superuser Isolation               │
│  - Leaderboards & Live Gazette       │  │  - Gemini AI Rate Governor (14 RPM)  │
└──────────────────────────────────────┘  └──────────────────────────────────────┘
```

### Port Mapping Table
| Environment / Layer | Player Application | Engine Admin Portal | Purpose |
| :--- | :--- | :--- | :--- |
| **External (HTTPS via Caddy)** | `https://<DOMAIN_OR_IP>:2028` | `https://<DOMAIN_OR_IP>:2029` | Public / Secure Client Access |
| **Local Service Binding (Django)** | `127.0.0.1:8028` | `127.0.0.1:8029` | Bound by `manage.py runserver` / `runserver_admin` |
| **Command (Player)** | `./venv/bin/python manage.py runserver 127.0.0.1:8028` | - | Runs Player & Pool Admin |
| **Command (Engine Admin)** | - | `./venv/bin/python manage.py runserver_admin` | Runs Port 8029 Engine Admin |

---

## 🚀 2. Grouped Section-by-Section Feature Breakdown (Through v2.7.0)

### Section 1: AI Tournament Scout & LLM Engine
1. **Tri-Pillar AI Scout Architecture**:
   - Decomposed deep scouting into 5 modular, autonomous sub-agents:
     - `HeadDiscoveryAgent`: Scrapes canonical tournament metadata, Wikipedia infoboxes, official portals, and dates.
     - `StructureRulesAgent`: Identifies groups, qualification paths, point rules, and sidebets.
     - `GroupsTeamsAgent`: Gathers confirmed participating teams, flags, and seeds.
     - `MatchesKnockoutAgent`: Generates fixtures, group schedule matrices, advancement rules, and knockout trees.
     - `ModularDeepScout`: Orchestrates agent execution with fast-failure circuit breakers and timeout guards.
2. **Google Search Grounding & Official Federation Ingestion**:
   - Integrated `OfficialSiteScout` with Google Search Grounded queries to extract verified schedule data directly from FIFA, UEFA, FIBA, IIHF, and IHF federations.
3. **Strict 30-Day Runway Buffer Rule**:
   - Enforced strict 30-day runway filter at both shallow web ingestion and deep scan layers. Any tournament starting `< today + 30 days` is rejected immediately to prevent stale data pollution.
4. **Strict Date Normalization Hierarchy**:
   - All extracted dates normalize to ISO `YYYY-MM-DD`. Missing days default to `YYYY-MM-01` and missing months to `YYYY-01-01`.
5. **Gemini 14 RPM Governor (`GeminiRateLimiter`)**:
   - Enforces a thread-safe token bucket ceiling at 14 RPM to operate safely under Google's 15 RPM free tier limit and eliminate 429 backoff penalties.
6. **EmblemScout & BackdropScout**:
   - `EmblemScout`: Strips years from queries and isolates clean, authentic transparent SVG/PNG logos.
   - `BackdropScout`: Discovers widescreen (16:9) stadium and host city backdrop imagery.
   - 0ms instant bracket token placeholder recognition (`TeamBadgeService.is_placeholder`).

### Section 2: Tournament Studio & Rules Blueprint Engine
1. **FormatBlueprintService**:
   - Central registry for canonical tournament formats (World Cups, UEFA Euro, Copa América, Nations League, IIHF Ice Hockey, IHF Handball, IFF Floorball, Olympic Tournaments).
2. **Bronze 3rd Place Match Standardization**:
   - Standardized bronze medal matches across World Championships and Olympic events, while respecting the UEFA Euro single-elimination exception (no 3rd place match).
3. **Dynamic Knockout Brackets**:
   - Full support for dynamic bracket stages (Round of 32, Round of 16, Quarter-finals, Semi-finals, Bronze, Final) with match tree sequence wiring (`winner_to`).
4. **Sidebet Default Points**:
   - Standardized default sidebet points to 25 points across all formats.

### Section 3: Participant Management & Onboarding Flow
1. **Deltagarmatris (Participant Matrix)**:
   - Added interactive participant matrix in Pool Admin Tournament Config (`pool_admin_tournament_config.html`).
   - Displays player name, email, role badge (Admin gold frame / Player light blue frame), login timestamps, invitation dispatch button (paper plane icon), password reset modal button (key icon), and new password column.
2. **Passwordless Magic Links**:
   - Secure HMAC token generator in `tournament/utils/magic_link.py`.
   - Responsive invitation email templates (`invite_email_template.html`) and live HTML preview modal (`invite_preview.html`).
3. **Terms & Conditions Acceptance & Password Enforcement**:
   - Dedicated `/terms/` acceptance portal and inline modal (`terms_modal_body.html`).
   - `MustSetPasswordMiddleware` (`tournament/middleware.py`): Intercepts authenticated users with `must_set_password=True` or `terms_accepted=False` and enforces password setup and terms acceptance before allowing portal navigation.

### Section 4: Engine Admin Dashboard & Authentication Isolation
1. **System Superuser Account Isolation**:
   - Dedicated system superuser (`johansiedberg`) restricted exclusively to Port 2029 / 8029 system administration.
   - System superuser is strictly prohibited from participating in player tables, pools, or leaderboards.
2. **EngineAdminPortMiddleware**:
   - Strict port-based routing isolating Engine Admin (Port 2029/8029) from Player Portal (Port 2028/8028).
3. **Distraction-Free Login Standard**:
   - Streamlined authentication portals (`/login/`, `engine_admin_login.html`, `login.html`) completely stripped of news banners, registration links, and changelog popups.
4. **Monitor Dashboard Refactor**:
   - Refactored Tab 2 into a tournament-centric health monitoring dashboard with actionable alerts and service logs.
5. **Monochromatic Tonal Contrast & Icon Spacing System**:
   - Implemented WCAG AA/AAA monochromatic contrast tokens (Success `#052E16`, Warning `#451A03`, Danger `#450A0A`, Info `#172554`, Neutral `#0F172A`).
   - Mandatory minimum 5px–6px visual spacing gap for all icons and emojis.
   - Sticky configuration bar dock with scroll-spy navigation and `localStorage` tab persistence.

### Section 5: Database Schema & Migrations Catalog
| Migration File | Key Changes / Models Affected |
| :--- | :--- |
| `0060_remove_matchprediction_tournament__match_i_935568_idx_and_more.py` | Database index cleanup, duplicate index removal, and foreign key protection |
| `0061_scannedtournament_backdrop_url.py` | Added `backdrop_url` (16:9 widescreen art) to `ScannedTournament` |
| `0062_alter_sidebet_points.py` | Altered `Sidebet.points` default to `25` |
| `0063_userprofile_must_set_password.py` | Added `UserProfile.must_set_password` boolean for magic link onboarding |
| `0064_userprofile_terms_accepted_and_more.py` | Added `UserProfile.terms_accepted` and `terms_accepted_at` datetime |
| `0065_alter_staticinsight_category.py` | Extended `StaticInsight.category` choices with `SIGN_HOME` and `SIGN_AWAY` |
| `0066_actual_knockout_dual_predictions.py` | Added `TournamentSubmission.is_actual_knockout_saved` and composite indexes for live actual knockout predictions |

---

## 🛠️ 3. Production Deployment & Activation Runbook

### Method A: Automated Remote Deploy from DEV (Recommended)
Run the automated deploy script from your local development machine:
```bash
./push_to_prd.sh
```
This pushes all local commits to GitHub and triggers the remote `./deploy.sh` script over SSH.

### Method B: Direct Execution on Ubuntu PRD Server
SSH into the server and execute:
```bash
ssh johansiedberg@192.168.86.35
cd /home/johansiedberg/Projects/Prediction_Engine
./deploy.sh
```

### What `deploy.sh` Does Automatically:
1. `git pull origin main`: Fetches and fast-forwards the latest code.
2. `manage.py migrate`: Applies database migrations (`0061`–`0066`).
3. `manage.py collectstatic --noinput`: Compiles all static CSS/JS assets.
4. `pkill -9`: Kills any stale Python/Django processes holding ports 8028/8029.
5. `nohup runserver`: Starts Player on `127.0.0.1:8028` and Engine Admin on `127.0.0.1:8029`.
6. Health Check: Runs automated curl tests to confirm HTTP 200/302 responses.

---

## 🔍 4. Verification & Diagnostics Checklist for AntiGravity (Ubuntu PRD)

If troubleshooting on the Ubuntu PRD server, execute this diagnostic checklist:

### 1. Verify Active Python Processes
```bash
ps aux | grep manage.py
```
Expected: Exactly two active Django processes running:
- `manage.py runserver 127.0.0.1:8028`
- `manage.py runserver_admin` (listening on `127.0.0.1:8029`)

### 2. Verify Port Bindings
```bash
ss -tulpn | grep -E "8028|8029|2028|2029"
```
Expected:
- Ports `8028` and `8029` listening by Python.
- Ports `2028` and `2029` listening by Caddy.

### 3. Verify Database Migration Status
```bash
./venv/bin/python manage.py showmigrations
```
Expected: All migrations through `0066_actual_knockout_dual_predictions` have `[X]` applied.

### 4. Verify Local Service Health
```bash
curl -I http://127.0.0.1:8028/
curl -I http://127.0.0.1:8029/
```
Expected: Both return `HTTP/1.1 200 OK` or `HTTP/1.1 302 Found`.

### 5. Check Live Application Logs
```bash
tail -n 50 /home/johansiedberg/Projects/Prediction_Engine/runserver_player.log
tail -n 50 /home/johansiedberg/Projects/Prediction_Engine/runserver_admin.log
```

---

## 📋 5. Required Environment Variables (`.env`)
Ensure `/home/johansiedberg/Projects/Prediction_Engine/.env` contains:
```ini
DJANGO_SECRET_KEY=<production-secret-key>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=*
GEMINI_API_KEY=<your-gemini-api-key>
GEMINI_MAX_CALLS_PER_MINUTE=14
```
