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

## [v2.7.0] - 2026-09-03 (Current Release)

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
