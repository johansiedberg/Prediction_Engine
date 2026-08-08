# TOURNAMENT EDITORIAL ENGINE - MASTER ARCHITECTURE & IMPLEMENTATION GUIDE

## 1. Executive Summary & Vision
We are building the **Tournament Editorial Engine** within an existing Django football prediction application. 

This engine powers the **"Insight and Analysis" tab** on the frontend, which is divided into two distinct sections:
1.  **Section 1: Prediction Insights (The Almanac):** A static section detailing pre-tournament analysis, group consensus, wild takes, lone-wolf picks, and delusion rankings.
2.  **Section 2: The Daily Gazette (Card View & Newspaper Modal):** A dynamic, newspaper-style daily feed.
    *   **Card Preview Grid:** Cards display the **Date**, an **AI-generated edgy visual asset**, a **Bold Headline**, and a **Tagline**.
    *   **Full Editorial Modal:** Clicking a card opens/expands the complete daily editorial column for that matchday.

---

## 2. Strict Language & Cultural Directive
To ensure maintainability while delivering maximum humor to the user group, code and content are strictly separated by language:

*   **100% English:** All Django code, model names, fields, comments, docstrings, backend logic, function names, and LLM Prompt Instructions.
*   **100% Swedish:** All LLM-generated output (Headlines, Taglines, Roasts, Gazette Articles, Image Prompts concepts) and cultural references.
    *   **Cultural Tone:** Dry, sarcastic, Scandinavian/Swedish humor. References should feel like childhood friends in Sweden watching football at a pub or roasting each other in a group chat. Understated, witty, cynical, and never corporate or motivational.

---

## 3. Core Architecture (The 4-Tier System)
Tier separation must be strictly maintained. Never let the LLM handle data analysis or ranking.

*   **Tier 1: Deterministic Event Detectors (Python/Django ORM)**
    Analyzes raw prediction data and match results. Generates `StaticInsight` records (for Section 1) and `InsightEvent` records (for Section 2).
*   **Tier 2: The Anti-Repetition Editor (Python Logic)**
    Queries top events by `importance_score`, manages decaying "Storyline Memory," and dynamically injects structural templates, randomized visual style modifiers, and negative phrase prompts to eliminate LLM crutches.
*   **Tier 3: Storyteller & Visualizer (API Integration)**
    Takes Tier 2 JSON payloads:
    1. Calls LLM/Media engine to generate Swedish prose, headline, tagline, and image concept in JSON format.
    2. **Multi-Event Rule:** Every daily editorial article MUST incorporate AT LEAST 2 to 3 distinct detected events (`events[0]`, `events[1]`, `events[2]`). The #1 ranked event sets the card headline, tagline, and image prompt, while secondary and tertiary events are woven into the article body sections.
    3. Calls Image API (or resolves local styled AI visual asset) based on the day's #1 ranked event.

---

## 4. Database Schema (Django Models)

### Core Editorial Models
*   **`StaticInsight` (Section 1):**
    *   `category`: `CharField` (e.g., 'CONSENSUS_ALERT', 'CERTIFIED_MADNESS', 'LONE_WOLF')
    *   `player_name`: `CharField` (nullable)
    *   `data_point`: `TextField` (e.g., "12 av 13 spelare tippade Spanien som gruppvinnare.")
    *   `llm_roast`: `TextField` (The generated Swedish joke/commentary)
    *   `is_published`: `BooleanField` (default=True)

*   **`InsightEvent` (Section 2):**
    *   `type`: `CharField` (e.g., 'ELIMINATION', 'BIG_MOVER', 'PREDICTION_AGED_POORLY')
    *   `player_name`: `CharField`
    *   `description`: `TextField` (e.g., "Lucas föll från 1:a till 5:e plats.")
    *   `importance_score`: `IntegerField` (0-100)
    *   `matchday_reference`: `IntegerField` or `DateField`
    *   `created_at`: `DateTimeField` (auto_now_add=True)
    *   `is_used`: `BooleanField` (default=False)

*   **`StorylineMemory` (Section 2):**
    *   `player_name`: `CharField`
    *   `narrative`: `TextField` (e.g., "Lucas satsade hårt på Belgien, men laget kraschade.")
    *   `last_updated`: `DateTimeField` (auto_now=True)
    *   `is_active`: `BooleanField` (Deactivates automatically after 48h without updates)

*   **`DailyGazette` (Section 2 Cards & Modal):**
    *   `publish_date`: `DateField` (Unique index per daily edition)
    *   `headline`: `CharField` (Bold headline in Swedish)
    *   `tagline`: `CharField` (Sub-headline/hook in Swedish)
    *   `image_url`: `URLField` or `ImageField` (Path to generated visual asset)
    *   `image_prompt`: `TextField` (Audit log of generated prompt)
    *   `content_format`: `CharField` (e.g., 'STANDARD_COLUMN', 'WINNERS_LOSERS', 'INTERVIEW', 'PUB_QUOTES')
    *   `content`: `TextField` (Full daily article in Swedish containing 2-3 events)
    *   `tone_used`: `CharField` (e.g., 'Torr Skandinavisk Humor')

### Anti-Repetition Models
*   **`StyleExample`:**
    *   `quote`: `TextField` (Hand-written Swedish roasts to calibrate LLM tone)
    *   `is_active`: `BooleanField` (default=True)

*   **`EditorialSettings` (Singleton Model):**
    *   `banned_phrases`: `JSONField` (List of overused phrases to forbid in LLM prompts, e.g., ["det återstår att se", "en sak är säker", "i en oväntad vändning"])

---

## 5. The Anti-Repetition & Variety Engine Logic
To prevent LLM fatigue over long tournaments, Tier 2 MUST dynamically randomize constraints for Tier 3 calls:

1.  **Format Rotation & Multi-Event Integration:** Python randomly selects 1 of 4 output formats per day, and weaves AT LEAST 2-3 events into the content:
    *   `STANDARD_COLUMN`: Lead narrative paragraph for Event #1 + section detailing Events #2 and #3.
    *   `WINNERS_LOSERS`: Bulleted list featuring 1-sentence roasts for Events #1, #2, and #3.
    *   `INTERVIEW`: Fake Q&A transcript asking an affected player about Events #1, #2, and #3.
    *   `PUB_QUOTES`: 4-5 cynical pub quotes reacting to Events #1, #2, and #3.
2.  **Visual Style Modifier Rotation:** Prepend image prompts with a randomized artistic style (e.g., *1920-tals politisk satirteckning*, *rå 1970-tals vintage polaroidbild*, *dramatiskt 1990-tals sporttidningsomslag*, *minimalistisk skandinavisk grafisk affisch*).
3.  **Negative Prompt Injection:** Pass the `banned_phrases` list into the prompt instruction: `"STRICT RULE: Do NOT use any of these overused Swedish phrases: [...]"`.
4.  **Few-Shot Calibration:** Pass 3 randomly selected `StyleExample` quotes in the prompt as tone reference.

---

## 6. Implementation Steps for AI Assistant

### Step 1: Models & Admin Interface
*   Create all models outlined in Section 4 in `models.py`.
*   Register them in `admin.py` with readable list displays (`importance_score`, `is_used`, `publish_date`).

### Step 2: Section 1 Logic (Static Almanac Generators)
*   Create `editorial_engine/static_generators.py`.
*   Write ORM queries to detect pre-tournament anomalies (`find_lone_wolves()`, `find_group_consensus()`, `calculate_delusion_index()`).
*   Generate 100% Swedish roasts and save to `StaticInsight`.

### Step 3: Section 2 Logic (Daily Event Detectors)
*   Create `editorial_engine/detectors.py`.
*   Write ORM queries to calculate daily events (`detect_eliminations()`, `detect_rank_swings()`, `detect_failed_bankers()`). Save as `InsightEvent`.

### Step 4: Section 2 Logic (Anti-Repetition Compiler & Media Pipeline)
*   Create `editorial_engine/compiler.py` and `editorial_engine/media.py`.
*   `compile_daily_assignment()` extracts top 3 unused events, active memories, selects a structural format, picks an image style modifier, and gathers banned phrases.
*   Pass context to LLM/Media engine structured as: `{ "headline": "...", "tagline": "...", "content": "...", "image_prompt": "..." }`, guaranteeing 2-3 events are present in `content`.
*   Pass `image_prompt` to Image Generation API / resolve local AI asset and save to `DailyGazette`.

### Step 5: Frontend Views & Templates
*   Create Django view for the **Insight and Analysis** tab.
*   **Section 1 Render (Almanackan):** Grid of static badges/cards for `StaticInsight`.
*   **Section 2 Render (Dagliga Gazetten):** Grid of `DailyGazette` cards sorted by `publish_date` descending. Each card shows the image, date, bold headline, and tagline.
*   **Modal Component:** Implement a modal/drawer triggered when a card is clicked, rendering the full `content`.

---

## 7. Strict Guardrails & Execution Rules
*   **100% Swedish Language Directive:** All generated output prose, headlines, taglines, pub quotes, roasts, data points, and UI badges MUST be 100% Swedish with dry, sarcastic Scandinavian pub humor.
*   **Multi-Event Coverage:** Every daily gazette article MUST cover at least 2 to 3 distinct detected events to form a comprehensive daily newsletter edition.
*   **Zero Causal Hallucination:** The LLM must NEVER invent reasons *why* a player made a prediction or *why* a match ended a certain way. Only describe verified outcome facts provided in the JSON payload.
*   **Deterministic Authority:** The Django ORM strictly owns narrative ranking. The LLM only writes prose.
*   **Image API Resilience:** If the Image API fails or times out, fall back gracefully to a static default placeholder image URL or local AI image asset so article generation never breaks.
*   **Idempotency:** Daily management commands generating gazettes must be idempotent for any given `publish_date`. Running the command twice must not create duplicate gazettes unless `--force` is passed.