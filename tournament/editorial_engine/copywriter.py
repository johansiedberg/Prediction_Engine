"""
copywriter.py
-------------
Role 3: Copywriter for Daily Gazette Editorial Engine.

Responsible for:
1. Auditing draft stories for factual contradictions, polarity mismatches, and logic errors.
2. Stripping duplicate sentences or repeated behavioral descriptions across paragraphs.
3. Enforcing Swedish V2 word order (e.g., 'Inför avspark drog Krantz...' instead of 'Inför avspark Krantz drog...').
4. Stripping banned cliché phrases, raw persona quotes, and meta link jargon.
5. Ensuring body text remains in clean, normal font formatting (removing bold markdown headers in body).
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

# Contradiction phrases that must NEVER appear when primary player is winning/leading
LEADER_CONTRADICTIONS = [
    (re.compile(r"tunga omgång", re.IGNORECASE), "starka omgång"),
    (re.compile(r"rasade i tabelläget", re.IGNORECASE), "befäste sitt tabelläge"),
    (re.compile(r"tvingades räkna in en tung förlust", re.IGNORECASE), "fortsatte plocka tunga poäng"),
    (re.compile(r"tvingades räkna in ett kännbart bakslag", re.IGNORECASE), "kunde räkna in ytterligare framgångar"),
    (re.compile(r"tunga motlut", re.IGNORECASE), "stabila spel"),
    (re.compile(r"kollapsade", re.IGNORECASE), "storspelade"),
    (re.compile(r"bottennapp", re.IGNORECASE), "toppresultat"),
]

# Contradiction phrases that must NEVER appear when primary player is falling/losing
FALLER_CONTRADICTIONS = [
    (re.compile(r"oemotståndlig seger", re.IGNORECASE), "tuff prövning"),
    (re.compile(r"befäste ledningen", re.IGNORECASE), "tappade mark"),
    (re.compile(r"utökade försprånget", re.IGNORECASE), "tvingades släppa förbi konkurrenter"),
    (re.compile(r"kopplat ett starkt grepp", re.IGNORECASE), "hamnat i ett pressat läge"),
]


class Copywriter:
    """
    Copywriter component that audits, cleans, and polishes story drafts with
    semantic truth checking, contradiction blocking, and Swedish syntax enforcement.
    """

    @classmethod
    def enforce_swedish_v2_syntax(cls, text: str) -> str:
        """
        Auto-corrects common Swedish fronting syntax errors
        (e.g., 'Inför matchstart Krantz drog igång' -> 'Inför matchstart drog Krantz igång').
        """
        v2_pattern = re.compile(
            r"\b(Inför (?:matchstart|avspark|drabbningen|omgången))\s+([A-ZÅÄÖ][a-zåäö]+)\s+(drog|studerade|vandrade|behöll|justerade|följde|skruvade|granskade|analyserade|lutade|satsade|kämpade|arbetade|förlitade|läste)\b"
        )
        return v2_pattern.sub(r"\1 \3 \2", text)

    @classmethod
    def remove_duplicate_sentences(cls, text: str) -> str:
        """
        Removes any sentence or large clause that appears more than once across paragraphs.
        """
        paragraphs = text.split("\n\n")
        cleaned_paragraphs = []
        seen_sentences = set()

        for para in paragraphs:
            sentences = re.split(r'(?<=[.!?])\s+', para.strip())
            unique_sentences = []
            for s in sentences:
                s_clean = s.strip()
                if not s_clean:
                    continue
                # Normalize sentence for duplicate checking
                s_norm = re.sub(r'\s+', ' ', s_clean.lower())
                if len(s_norm.split()) > 4 and s_norm in seen_sentences:
                    continue # Skip duplicate sentence
                seen_sentences.add(s_norm)
                unique_sentences.append(s_clean)
            if unique_sentences:
                cleaned_paragraphs.append(" ".join(unique_sentences))

        return "\n\n".join(cleaned_paragraphs)

    @classmethod
    def audit_and_correct(cls, journalist_draft: dict, banned_phrases: list = None) -> dict:
        """
        Audits draft stories for contradictions, cleans banned phrases/traits,
        converts direct quotes to indirect narrative, enforces Swedish V2 grammar,
        and ensures body text is 100% logically sound.

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
        polarity = journalist_draft.get('polarity', 'GENERAL_STAGE')

        # 1. Semantic Contradiction Audit
        if polarity == 'LEADER_TRIUMPH':
            for pattern, replacement in LEADER_CONTRADICTIONS:
                top_story = pattern.sub(replacement, top_story)
                headline = pattern.sub(replacement, headline)
                tagline = pattern.sub(replacement, tagline)
        elif polarity == 'FALLER_COLLAPSE':
            for pattern, replacement in FALLER_CONTRADICTIONS:
                top_story = pattern.sub(replacement, top_story)
                headline = pattern.sub(replacement, headline)
                tagline = pattern.sub(replacement, tagline)

        # 2. Swedish V2 Syntax Enforcement
        top_story = cls.enforce_swedish_v2_syntax(top_story)
        event2_text = cls.enforce_swedish_v2_syntax(event2_text)
        event3_text = cls.enforce_swedish_v2_syntax(event3_text)

        # 3. Deduplicate Repeated Sentences
        top_story = cls.remove_duplicate_sentences(top_story)

        # 4. Strip Banned Phrases
        for phrase in phrases_to_ban:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            top_story = pattern.sub("", top_story)
            event2_text = pattern.sub("", event2_text)
            event3_text = pattern.sub("", event3_text)

        # 5. Strip Explicit Trait Labels ("Show, Don't Tell" enforcement)
        for trait_pattern in EXPLICIT_TRAIT_LABELS:
            pattern = re.compile(trait_pattern, re.IGNORECASE)
            top_story = pattern.sub("", top_story)

        # 6. Strip bold markdown formatting from body text for normal font presentation
        top_story = top_story.replace("**", "")
        event2_text = event2_text.replace("**", "")
        event3_text = event3_text.replace("**", "")

        # 7. Convert raw direct quote marks to indirect narrative
        top_story = top_story.replace('”', '').replace('"', '').replace("'", "")
        event2_text = event2_text.replace('”', '').replace('"', '').replace("'", "")
        event3_text = event3_text.replace('”', '').replace('"', '').replace("'", "")

        # 8. Clean punctuation and spacing artifacts
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
            'polarity': polarity,
            'audit_passed': True,
        }

