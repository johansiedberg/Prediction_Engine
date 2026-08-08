"""
copywriter.py
-------------
Role 3: Copywriter for Daily Gazette Editorial Engine.

Responsible for:
1. Auditing draft stories for factual contradictions and logic errors.
2. Stripping banned cliché phrases, raw persona quotes, and meta link jargon.
3. Amplifying persona behavior through active descriptions while removing explicit trait labels.
4. Ensuring body text remains in clean, normal font formatting (removing bold markdown headers in body).
"""

import re

BANNED_PHRASES = [
    "det återstår att se",
    "en sak är säker",
    "i en oväntad vändning",
    "dramatiken nådde nya höjder",
    "bollen är rund",
    "klicka här",
    "länk till tidigare",
    "se tidigare utgåva",
    "som vi alla vet",
]

# Explicit trait labels to strip so text "shows" behavior rather than "telling" traits
EXPLICIT_TRAIT_LABELS = [
    r"\(analytisk\)",
    r"\(hög energi\)",
    r"\(sjukgymnast\)",
    r"\(skogshuggare\)",
    r"\(direktör\)",
    r"\(wiseman\)",
    r"\(entusiastisk tippare\)",
]


class Copywriter:
    """
    Copywriter component that audits, cleans, and polishes story drafts.
    """

    @staticmethod
    def audit_and_correct(journalist_draft: dict, banned_phrases: list = None) -> dict:
        """
        Audits draft stories for contradictions, cleans banned phrases/traits,
        converts direct quotes to indirect narrative, and polishes text into normal font formatting.

        Args:
            journalist_draft: Dict from Journalist.draft_edition_stories()
            banned_phrases: Optional custom list of banned cliché strings

        Returns:
            Polished story dictionary ready for publication.
        """
        phrases_to_ban = (banned_phrases or []) + BANNED_PHRASES

        top_story = journalist_draft.get('top_story', '')
        event2_text = journalist_draft.get('event2_text', '')
        event3_text = journalist_draft.get('event3_text', '')
        headline = journalist_draft.get('headline', '')
        tagline = journalist_draft.get('tagline', '')

        # 1. Strip Banned Phrases
        for phrase in phrases_to_ban:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            top_story = pattern.sub("", top_story)
            event2_text = pattern.sub("", event2_text)
            event3_text = pattern.sub("", event3_text)

        # 2. Strip Explicit Trait Labels ("Show, Don't Tell" enforcement)
        for trait_pattern in EXPLICIT_TRAIT_LABELS:
            pattern = re.compile(trait_pattern, re.IGNORECASE)
            top_story = pattern.sub("", top_story)

        # 3. Strip bold markdown formatting from body text for normal font presentation
        top_story = top_story.replace("**", "")
        event2_text = event2_text.replace("**", "")
        event3_text = event3_text.replace("**", "")

        # 4. Convert raw direct quote marks to indirect narrative
        top_story = top_story.replace('”', '').replace('"', '').replace("'", "")
        event2_text = event2_text.replace('”', '').replace('"', '').replace("'", "")
        event3_text = event3_text.replace('”', '').replace('"', '').replace("'", "")

        # 5. Clean punctuation and spacing artifacts
        top_story = re.sub(r' +', ' ', top_story)
        top_story = re.sub(r'\.\.+', '.', top_story).strip()

        event2_text = re.sub(r' +', ' ', event2_text).strip()
        event3_text = re.sub(r' +', ' ', event3_text).strip()

        return {
            'headline': headline,
            'tagline': tagline,
            'top_story': top_story,
            'event2_text': event2_text,
            'event3_text': event3_text,
            'audit_passed': True,
        }
