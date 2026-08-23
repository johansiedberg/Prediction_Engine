"""
Adaptive Multi-Tier Temporal Lifecycle Scraper Strategy
======================================================
Calculates the operational phase, polling frequency, and tool execution policy
based on tournament format (International vs. Club) and closeness to kickoff.

Temporal Windows:
- International:
  - Phase 1 (Macro-Meta):   > 270 days (> 9 months)  -> Poll monthly (30d), placeholders expected.
  - Phase 2 (The Draw):     90 to 270 days (3-9 mo)  -> Poll weekly (7d), trigger immediately on draw date.
  - Phase 3 (Production):   < 90 days (< 3 months)   -> Poll daily/hourly, exact timestamps & rosters.
- Club Competitions:
  - Phase 1 (Macro-Meta):   > 30 days (> 4 weeks)    -> Poll bi-weekly (14d).
  - Phase 2 (The Draw):     7 to 30 days (1-4 weeks) -> Poll every 3 days.
  - Phase 3 (Production):   < 7 days (< 1 week)      -> Poll daily / real-time.
"""

import datetime
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Optional, Dict, Any


class TournamentType(str, Enum):
    INTERNATIONAL_NATIONAL = "INTERNATIONAL_NATIONAL"
    CLUB_CONTINENTAL = "CLUB_CONTINENTAL"
    CLUB_DOMESTIC = "CLUB_DOMESTIC"


class ScraperPhase(str, Enum):
    PHASE_1_MACRO_META = "PHASE_1_MACRO_META"  # Metadata only (>9mo intl / >4wk club)
    PHASE_2_THE_DRAW   = "PHASE_2_THE_DRAW"    # Draw event window (9-3mo intl / 4-1wk club)
    PHASE_3_PRODUCTION = "PHASE_3_PRODUCTION"  # Production operations (<3mo intl / <1wk club)


@dataclass
class LifecycleState:
    phase: ScraperPhase
    tournament_type: TournamentType
    days_to_start: Optional[int]
    next_rescan_date: Optional[datetime.date]
    phase_label: str
    phase_short: str
    phase_badge_html: str
    tool_policy: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


class LifecycleStrategy:
    """
    Core engine evaluating tournament temporal closeness and assigning dynamic scraping policies.
    """

    CLUB_KEYWORD_PATTERNS = [
        r'\b(?:champions league|europa league|conference league|copa libertadores|copa sudamericana)\b',
        r'\b(?:club world cup|klubb-vm|spengler cup|super cup|fa cup|copa del rey|dfb-pokal|coupe de france)\b',
        r'\b(?:allsvenskan|premier league|la liga|serie a|bundesliga|ligue 1|shl|nhl|nba|nfl|kbl|k-league)\b',
        r'\b(?:champions hockey league|chl|ehf champions league|cev champions league)\b',
    ]

    INTERNATIONAL_KEYWORD_PATTERNS = [
        r'\b(?:world cup|fifa|uefa euro|em |vm |copa américa|afcon|asian cup|gold cup|nations cup)\b',
        r'\b(?:olympics|olympic games|os |iihf|fiba|ehf euro|iff|world championship|världsmästerskap)\b',
        r'\b(?:europamästerskap|nations league)\b',
    ]

    @classmethod
    def determine_tournament_type(
        cls, name: str = "", sport: str = "", organizer: str = ""
    ) -> TournamentType:
        """
        Classifies tournament as International National Teams, Club Continental, or Club Domestic.
        """
        text = f"{name} {organizer}".lower().strip()

        for pat in cls.CLUB_KEYWORD_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return TournamentType.CLUB_CONTINENTAL

        for pat in cls.INTERNATIONAL_KEYWORD_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return TournamentType.INTERNATIONAL_NATIONAL

        # Default fallback based on common words
        if any(w in text for w in ['herrar', 'damer', 'men', 'women', 'u21', 'u20', 'u19', 'u18', 'u17']):
            return TournamentType.INTERNATIONAL_NATIONAL

        return TournamentType.INTERNATIONAL_NATIONAL

    @classmethod
    def calculate_lifecycle_phase(
        cls,
        start_date: Optional[datetime.date] = None,
        draw_date: Optional[datetime.date] = None,
        tournament_type: Optional[TournamentType] = None,
        today: Optional[datetime.date] = None,
    ) -> LifecycleState:
        """
        Calculates exact lifecycle phase, next rescan date, and tool execution policy.
        """
        today = today or datetime.date.today()
        t_type = tournament_type or TournamentType.INTERNATIONAL_NATIONAL

        if not start_date:
            # Undated or tentative: Default to Phase 1 Macro-Meta with 30-day polling
            next_poll = draw_date if (draw_date and draw_date >= today) else today + datetime.timedelta(days=30)
            return LifecycleState(
                phase=ScraperPhase.PHASE_1_MACRO_META,
                tournament_type=t_type,
                days_to_start=None,
                next_rescan_date=next_poll,
                phase_label="Fas 1: Grundläggande metadata (Datum ej fastställt)",
                phase_short="Fas 1 (Metadata)",
                phase_badge_html='<span class="badge" style="background:#0F172A;border:1px solid #475569;color:#E2E8F0;"><i class="fa-solid fa-circle-info me-1.5 text-secondary"></i>Fas 1: Metadata</span>',
                tool_policy={
                    "fetch_fixtures": False,
                    "fetch_rosters": False,
                    "allow_gemini_quota": False,
                    "extract_placeholders_only": True,
                    "poll_interval_days": 30,
                },
                description="Turneringen saknar bekräftat startdatum. Skannern pollar metadata månadsvis."
            )

        days_to_start = (start_date - today).days

        # Event already concluded
        if days_to_start < 0:
            return LifecycleState(
                phase=ScraperPhase.PHASE_3_PRODUCTION,
                tournament_type=t_type,
                days_to_start=days_to_start,
                next_rescan_date=None,
                phase_label="Avslutad turnering",
                phase_short="Avslutad",
                phase_badge_html='<span class="badge bg-secondary text-dark font-monospace"><i class="fa-solid fa-flag-checkered me-1.5"></i>Avslutad</span>',
                tool_policy={"fetch_fixtures": False, "fetch_rosters": False, "allow_gemini_quota": False, "poll_interval_days": 999},
                description="Turneringen har redan passerat."
            )

        # Set thresholds based on International vs. Club compression switch
        if t_type == TournamentType.INTERNATIONAL_NATIONAL:
            phase_1_threshold = 270  # > 9 months
            phase_2_threshold = 90   # 3 to 9 months
        else:
            phase_1_threshold = 30   # > 4 weeks
            phase_2_threshold = 7    # 1 to 4 weeks

        # --- Phase 1: Macro-Metadata Only (> 9 months intl / > 4 weeks club) ---
        if days_to_start > phase_1_threshold:
            # If an official draw date is known and in the future, set wakeup to draw date
            if draw_date and draw_date >= today:
                next_poll = draw_date
            else:
                next_poll = today + datetime.timedelta(days=30)

            return LifecycleState(
                phase=ScraperPhase.PHASE_1_MACRO_META,
                tournament_type=t_type,
                days_to_start=days_to_start,
                next_rescan_date=next_poll,
                phase_label=f"Fas 1: Metadata (> {days_to_start} dagar kvar)",
                phase_short="Fas 1 (Metadata)",
                phase_badge_html='<span class="badge font-monospace" style="background:#0F172A;border:1px solid #475569;color:#E2E8F0;"><i class="fa-solid fa-circle-info me-1.5 text-info"></i>Fas 1: Metadata (&gt;9 mån)</span>',
                tool_policy={
                    "fetch_fixtures": False,
                    "fetch_rosters": False,
                    "allow_gemini_quota": False,
                    "extract_placeholders_only": True,
                    "poll_interval_days": 30,
                },
                description="Lång horisont. Endast övergripande turneringsstruktur och kvalgrupper skannas för att spara API-anrop."
            )

        # --- Phase 2: The Draw Event (9 to 3 months intl / 4 to 1 weeks club) ---
        elif days_to_start > phase_2_threshold:
            if draw_date and today < draw_date:
                next_poll = draw_date
                draw_str = f"Lottas {draw_date.strftime('%Y-%m-%d')}"
            else:
                next_poll = today + datetime.timedelta(days=7)
                draw_str = "Lottningsfönster aktivt"

            return LifecycleState(
                phase=ScraperPhase.PHASE_2_THE_DRAW,
                tournament_type=t_type,
                days_to_start=days_to_start,
                next_rescan_date=next_poll,
                phase_label=f"Fas 2: Lottning & Grupper ({draw_str})",
                phase_short="Fas 2 (Lottning)",
                phase_badge_html='<span class="badge font-monospace" style="background:#451A03;border:1px solid #B45309;color:#FEF3C7;"><i class="fa-regular fa-calendar-check me-1.5 text-warning"></i>Fas 2: Lottningsfönster (9–3 mån)</span>',
                tool_policy={
                    "fetch_fixtures": True,
                    "fetch_rosters": False,
                    "allow_gemini_quota": True,
                    "extract_seeding_pots": True,
                    "extract_group_matrices": True,
                    "poll_interval_days": 7,
                },
                description="Lottningsfönstret är aktivt. Skannern övervakar officiella lottningsresultat och gruppindelningar veckovis."
            )

        # --- Phase 3: Operational Production (< 3 months intl / < 1 week club) ---
        else:
            poll_interval = 1 if days_to_start <= 14 else 3
            next_poll = today + datetime.timedelta(days=poll_interval)

            return LifecycleState(
                phase=ScraperPhase.PHASE_3_PRODUCTION,
                tournament_type=t_type,
                days_to_start=days_to_start,
                next_rescan_date=next_poll,
                phase_label=f"Fas 3: Produktion & Spelschema ({days_to_start} dagar kvar)",
                phase_short="Fas 3 (Produktion)",
                phase_badge_html='<span class="badge font-monospace" style="background:#052E16;border:1px solid #15803D;color:#DCFCE7;"><i class="fa-solid fa-bolt me-1.5 text-success"></i>Fas 3: Drift &amp; Tider (&lt;3 mån)</span>',
                tool_policy={
                    "fetch_fixtures": True,
                    "fetch_rosters": True,
                    "allow_gemini_quota": True,
                    "fetch_exact_kickoff_hours": True,
                    "fetch_broadcasters": True,
                    "poll_interval_days": poll_interval,
                },
                description="Slutgiltigt spelschema, exakta avsparkstider och lagtrupper låses inför spelöppning."
            )
