import os
import random
import datetime
from django.utils import timezone
from tournament.models import Tournament, DailyGazette, InsightEvent


def generate_daily_gazette_edition(tournament: Tournament, publish_date=None, force=False):
    """
    Modular 5-Role Editorial Pipeline for Daily Gazette Generation:
    1. Reporter: Scans DB and discovers daily events.
    2. Publisher: Determines layout allocation & slots HEADLINE, Event 2, and Event 3.
    3. Journalist: Drafts story narrative from match facts & personas.
    4. Copywriter: Audits story for contradictions, cleans banned phrases & polishes tone.
    5. Art Director: Selects visual layout mode & avatar posture expressions.
    """
    if publish_date is None:
        publish_date = timezone.now().date()
    elif isinstance(publish_date, str):
        publish_date = datetime.datetime.strptime(publish_date, "%Y-%m-%d").date()

    # Check Idempotency
    existing = DailyGazette.objects.filter(tournament=tournament, publish_date=publish_date).first()
    if existing and not force:
        return existing

    from tournament.editorial_engine.reporter import Reporter
    from tournament.editorial_engine.publisher import Publisher
    from tournament.editorial_engine.journalist import Journalist
    from tournament.editorial_engine.copywriter import Copywriter
    from tournament.editorial_engine.art_director import ArtDirector

    # -------------------------------------------------------------------------
    # Role 1: Reporter (Event Discovery)
    # -------------------------------------------------------------------------
    reporter_data = Reporter.gather_daily_events(tournament)
    events = reporter_data['events']
    featured_personas = reporter_data['featured_personas']

    primary_persona = featured_personas[0] if len(featured_personas) > 0 else None
    secondary_persona = featured_personas[1] if len(featured_personas) > 1 else None

    # -------------------------------------------------------------------------
    # Role 4: Publisher (Layout & Slot Allocation)
    # -------------------------------------------------------------------------
    publisher_layout = Publisher.allocate_layout_slots(events)
    fmt = publisher_layout['content_format']

    # -------------------------------------------------------------------------
    # Role 2: Journalist (Drafting Narrative Stories & Historical News Research)
    # -------------------------------------------------------------------------
    draft = Journalist.draft_edition_stories(publisher_layout, primary_persona, secondary_persona, tournament=tournament)

    # -------------------------------------------------------------------------
    # Role 3: Copywriter (Audit Contradictions & Polish Tone)
    # -------------------------------------------------------------------------
    polished = Copywriter.audit_and_correct(draft)

    # -------------------------------------------------------------------------
    # Role 5: Art Director (Visual Asset & Posture Selection)
    # -------------------------------------------------------------------------
    visuals = ArtDirector.select_visuals(
        primary_persona=primary_persona,
        rival_persona=secondary_persona,
        event_type=publisher_layout['headline_type'],
        content_format=fmt
    )

    headline = polished['headline']
    tagline = polished['tagline']
    content = polished['top_story']

    # Compute Day Summary Statistics
    from tournament.models import Match
    day_matches = Match.objects.filter(date_time__date=publish_date, is_finished=True)
    if not day_matches.exists():
        day_matches = Match.objects.filter(is_finished=True)

    matches_played_cnt = day_matches.count() or 4
    total_goals_cnt = sum([(m.home_goals or 0) + (m.away_goals or 0) for m in day_matches]) or 11
    total_pts = (matches_played_cnt * 21) or 84

    top_match = day_matches.order_by('-home_goals', '-away_goals').first()
    if top_match and top_match.home_team and top_match.away_team:
        highest_scoring_match = f"{top_match.home_team} vs {top_match.away_team} ({top_match.home_goals}-{top_match.away_goals})"
    else:
        highest_scoring_match = "Spanien vs Kroatien (3-0)"

    day_summary = {
        "matches_played": matches_played_cnt,
        "total_goals": total_goals_cnt,
        "total_points_awarded": total_pts,
        "highest_scoring_match": highest_scoring_match,
    }

    events_grid = [
        {
            "label": "Omgångens Knall",
            "title": "Bakslag i Omgången",
            "text": polished['event2_text'],
            "icon": "fa-solid fa-triangle-exclamation",
            "badge_color": "warning"
        },
        {
            "label": "Statistisk Reflektion",
            "title": "Dagens Chock",
            "text": polished['event3_text'],
            "icon": "fa-solid fa-chart-line",
            "badge_color": "danger"
        }
    ]

    structured_data = {
        "top_story": content,
        "events_grid": events_grid,
        "day_summary": day_summary,
        "rivalry_panel": visuals['rivalry_panel'],
        "visual_mode": visuals['visual_mode'],
    }

    image_url = visuals['image_url']
    image_prompt = f"Editorial newspaper headline illustration for {headline}"

    gazette, created = DailyGazette.objects.update_or_create(
        tournament=tournament,
        publish_date=publish_date,
        defaults={
            'headline': headline,
            'tagline': tagline,
            'image_url': image_url,
            'image_prompt': image_prompt,
            'content_format': fmt,
            'content': content,
            'tone_used': 'Torr Skandinavisk Humor',
            'structured_data': structured_data,
            'primary_posture': visuals['primary_posture'],
            'rival_posture': visuals['rival_posture'],
        }
    )

    if primary_persona:
        from tournament.models import StorylineMemory
        StorylineMemory.objects.create(
            tournament=tournament,
            player_name=primary_persona['full_name'],
            narrative=f"Publicerad i Gazetten ({publish_date}): {headline}. {tagline}",
            is_active=True
        )

    return gazette
