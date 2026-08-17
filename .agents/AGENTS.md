# Project Rules for Prediction Engine

## Development Server
- **Prediction (Player Application)**: Default port **2028**
  - Start command: `./venv/bin/python manage.py runserver` (or `./venv/bin/python manage.py runserver 2028`)
  - Access at: http://127.0.0.1:2028
- **Engine Admin**: Default port **2029**
  - Start command: `./venv/bin/python manage.py runserver_admin` (or `./venv/bin/python manage.py runserver 2029`)
  - Access at: http://127.0.0.1:2029 (or https:// in HTTPS-enabled environments)

## HTTPS Security Standards
- Enforces HTTPS standards (`SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_REFERRER_POLICY`) for secure encrypted transport.

## Monochromatic Tonal Contrast & Legibility Guidelines
When colouring banners, badges, and status notification containers, ensure readable distinct fill/background + font/icon combinations following a monochromatic tonal contrast system.

### Color Mapping Specification
| Role | Token Level | Target Luminance | Purpose / Usage | Example (Green Success Light Mode) | Example (Green Success Dark Mode) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Surface (BG)** | 50 – 100 / 950 | Light (92% – 97%) / Deep (~10%) | Low visual noise; keeps screen scannable | `#F0FDF4` (Green-50) | `#052E16` (Green-950) |
| **Border / Divider** | 200 – 300 / 800 | Mid-Light (75% – 85%) / Mid-Dark | Defines container boundary | `#BBF7D0` (Green-200) | `#15803D` (Green-700/800) |
| **Icon / Accent** | 600 – 700 / 100-200 | Deep (35% – 45%) / Pale tint | High visual weight status indicator | `#15803D` (Green-700) | `#DCFCE7` (Green-100) |
| **Primary Text** | 800 – 900 / 100-200 | Very Dark (15% – 25%) / Pale tint | Maximum contrast & legibility | `#14532D` (Green-900) | `#DCFCE7` (Green-100) |

### Core UI/UX Rules
- **WCAG Contrast Ratios**:
  - **Text**: Minimum **4.5:1** contrast ratio (WCAG AA) against banner surface (aim for **7:1** WCAG AAA).
  - **Icons & Boundaries**: Minimum **3.0:1** contrast against background.
- **Shared Hue Continuity**:
  - Never place pure neutral black (`#000000`) or mid-tone vibrant colors (e.g., `#22C55E`) directly on a light pastel or deep dark background without proper tonal pairing. Tint dark text with 10–15% of background hue to create visual depth and prevent chromatic aberration.
- **Multi-Modal Signaling**:
  - Never rely on color alone to convey state. Every banner/badge must pair color with an explicit status icon (e.g., checkmark for success, shield for security) and descriptive text.
- **Dark Mode Inversion**:
  - Reverse polarity while desaturating backgrounds to prevent eye strain:
    - **Surface**: Deep tone (`#052E16` / Green-950, ~10% lightness)
    - **Border**: Mid-dark tone (`#15803D` / Green-700/800)
    - **Text & Icon**: Pale tint (`#DCFCE7` / Green-100, ~85–90% lightness)

## Tab State Persistence Standard
- In Engine Admin (`engine_admin.html`), all tab navigation (`1. Tournaments`, `2. Monitor`, `3. Pool-Admin-ansökningar`, `4. AI Tournament Scout`) MUST preserve active state in `localStorage` (`engineAdminActiveTab`) and URL hash (`#scout-pane`).
- Executing any action (scout scan, tournament delete, status update, point rule save) MUST restore the exact same active tab section on reload without resetting to section 1.

## Section 4: AI Tournament Scout UI & Filtering Rules
- **AllSportDB Ingestion**: AllSportDB (v3) API is the single authoritative source of scanned tournament prospects.
- **H2H Team Sport Filter**: Exclude non-H2H individual sports (Chess, Tennis, Archery, Sailing, Wrestling, etc.) by setting grade to `GRADE_C`.
- **Grade A/B/C Rating Monochromatic Badges**:
  - **Grade A (100% Ready)**: Green-950 surface (`#052E16`), Green-700 border (`#15803D`), Green-100 text (`#DCFCE7`) + Checkmark Shield icon.
  - **Grade B (Pending Draw/Fixtures)**: Amber-950 surface (`#451A03`), Amber-700 border (`#B45309`), Amber-100 text (`#FEF3C7`) + Clock icon.
  - **Grade C (Filtered/Watched)**: Slate-900 surface (`#0F172A`), Slate-600 border (`#475569`), Slate-200 text (`#E2E8F0`) + Info icon.




