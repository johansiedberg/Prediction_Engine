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
    """Load player personas from JSON definition file."""
    base_dir = os.path.dirname(__file__)
    json_path = os.path.join(base_dir, 'player_personas.json')
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
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

