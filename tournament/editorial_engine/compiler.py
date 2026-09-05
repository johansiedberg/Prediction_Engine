import os
import json
import random
from tournament.models import (
    Tournament, InsightEvent, StorylineMemory, StyleExample, EditorialSettings
)

VISUAL_STYLES = [
    "1920s satirical political cartoon, monochrome ink hatching",
    "gritty vintage 1970s polaroid photo with subtle film grain",
    "dramatic 1990s sports magazine cover style, high contrast",
    "minimalist Scandinavian graphic poster with retro bold typography",
    "oil painting in the style of Swedish romantic nationalism, dramatic lighting"
]

FORMAT_TYPES = [
    'STANDARD_COLUMN',
    'WINNERS_LOSERS',
    'INTERVIEW',
    'PUB_QUOTES'
]


def load_player_personas():
    """Load player personas from database table, falling back to JSON file."""
    try:
        from tournament.models import PlayerPersona
        db_personas = list(PlayerPersona.objects.filter(is_active=True))
        if db_personas:
            return [
                {
                    'id': p.id,
                    'full_name': p.full_name,
                    'nicknames': [p.nickname],
                    'occupation': p.occupation,
                    'avatar_filename': p.avatar_filename or f"{p.full_name}.jpg"
                }
                for p in db_personas
            ]
    except Exception:
        pass

    path = os.path.join(os.path.dirname(__file__), 'player_personas.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def find_persona_for_player(player_name, personas_list=None):
    """Find matching persona dict by player full name or nickname."""
    if not personas_list:
        personas_list = load_player_personas()
    if not player_name:
        return None
    
    clean_name = player_name.strip().lower()
    for persona in personas_list:
        full = persona['full_name'].lower()
        if clean_name in full or full in clean_name:
            return persona
        for nick in persona.get('nicknames', []):
            if clean_name == nick.lower():
                return persona
    return None


def is_toarps_pool(tournament: Tournament) -> bool:
    """Returns True strictly if pool/tournament belongs to Toarps Herrklubb."""
    if not tournament:
        return False
    t_name = getattr(tournament, 'name', '').lower()
    if "toarp" in t_name:
        return True
    if getattr(tournament, 'pk', None) and hasattr(tournament, 'leagues'):
        try:
            if tournament.leagues.filter(name__icontains='toarp').exists():
                return True
        except Exception:
            pass
    return False


def get_player_nick_or_name(player, personas_list=None, is_toarp=False) -> str:
    """Returns persona nickname strictly for Toarp, else clean display/first name."""
    if not player:
        return "Tipparen"
    p_name = player.get_full_name() if hasattr(player, 'get_full_name') and player.get_full_name() else (
        f"{player.first_name} {player.last_name}".strip() if getattr(player, 'first_name', '') else getattr(player, 'email', 'Spelare')
    )
    first_or_full = p_name.split()[0] if ' ' in p_name else p_name
    if is_toarp:
        if not personas_list:
            personas_list = load_player_personas()
        p_match = find_persona_for_player(p_name, personas_list)
        if p_match:
            nicks = p_match.get('nicknames', [])
            if nicks and nicks[0]:
                return nicks[0]
    return first_or_full


def compile_daily_assignment(tournament: Tournament):
    """
    Tier 2 Anti-Repetition Compiler.
    Gathers events, memory, player personas, applies format/style rotation,
    and constructs the instruction payload for Tier 3 LLM generation.
    """
    personas_list = load_player_personas()

    # 1. Gather top unused events
    unused_events = list(InsightEvent.objects.filter(tournament=tournament, is_used=False).order_by('-importance_score')[:3])
    if not unused_events:
        unused_events = list(InsightEvent.objects.filter(tournament=tournament).order_by('-importance_score')[:3])

    event_descriptions = [e.description for e in unused_events]
    featured_personas = []

    # Match player names to personas
    for e in unused_events:
        e.is_used = True
        e.save()
        if e.player_name:
            p_match = find_persona_for_player(e.player_name, personas_list)
            if p_match and p_match not in featured_personas:
                featured_personas.append(p_match)

    # 2. Gather active storyline memories
    active_memories = StorylineMemory.objects.filter(tournament=tournament, is_active=True)[:2]
    memory_notes = [f"{m.player_name}: {m.narrative}" for m in active_memories]

    # 3. Format & Visual Style Selection
    selected_format = random.choice(FORMAT_TYPES)
    selected_style = random.choice(VISUAL_STYLES)

    # 4. Fetch Editorial Settings & Tone Examples
    settings_obj = EditorialSettings.objects.first()
    banned_phrases = settings_obj.banned_phrases if settings_obj else [
        "det återstår att se", "en sak är säker", "i en oväntad vändning", "dramatiken nådde nya höjder"
    ]

    style_quotes = list(StyleExample.objects.filter(is_active=True).values_list('quote', flat=True)[:3])
    if not style_quotes:
        style_quotes = [
            "Klassisk komedi på hög nivå när alla tippade fel.",
            "Det är inte lätt när det är svårt, men detta var extra svagt.",
            "Kaffet smakar lite extra bittert efter den här omgången."
        ]

    # 5. Build JSON Payload Structure
    payload = {
        "format": selected_format,
        "visual_style_modifier": selected_style,
        "events": event_descriptions,
        "featured_personas": featured_personas,
        "storyline_memories": memory_notes,
        "banned_phrases": banned_phrases,
        "few_shot_examples": style_quotes,
        "language_directive": "Outputs MUST be 100% Swedish with dry, sarcastic Scandinavian humor. Code and keys are English."
    }

    return payload

