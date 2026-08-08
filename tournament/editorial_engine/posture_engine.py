"""
posture_engine.py
-----------------
Deterministic posture selection engine for the Daily Gazette avatar system.

Organized into 4 Editorial Arcs:
1. The Betting & Build-Up Arc (Analyst, Clutch, Rival-left, Rival-right)
2. The Frustration & Protest Arc (Badbeat, Shame, Facepalm, Italian, Referee, Protest, What)
3. The General Victory Arc (LastManStanding, ComebackKing, Fist, Roar, Chest, Superman, Jersey)
4. The Signature Celebrations Arc (Zen, Bane, Siuuu, Messi, Sharpshooter, Knee, Silence, Heart, Hear)

File naming convention:
  media/avatars/Expression/[INITIALS]_[Posture].[jpg|JPG|jpeg|png]
"""

import os

# ---------------------------------------------------------------------------
# Editorial Arcs Definition
# ---------------------------------------------------------------------------

POSTURE_ARCS = {
    "BUILD_UP": ["Analyst", "Clutch", "Rival-left", "Rival-right"],
    "FRUSTRATION": ["Badbeat", "Shame", "Facepalm", "Italian", "Referee", "Protest", "What"],
    "VICTORY": ["LastManStanding", "ComebackKing", "Fist", "Roar", "Chest", "Superman", "Jersey"],
    "SIGNATURE_CELEBRATION": ["Zen", "Bane", "Siuuu", "Messi", "Sharpshooter", "Knee", "Silence", "Heart", "Hear"]
}

# Context tag -> posture trigger rules (checked top to bottom)
CONTEXT_TAG_RULES = [
    ('IS_TOURNAMENT_LEADER',  'Bane'),                  # Overall leader
    ('IS_STANDINGS_TOP3',     'Zen'),                   # Top 3 calm composure
    ('CORRECT_EXACT_SCORE',   'Sharpshooter'),          # Exact score hit
    ('OUTLIER_VICTORY',       'Siuuu'),                 # Single hero win
    ('DOUBTED_BUT_WON',       'Silence'),               # Silence the doubters
    ('CROWD_PLEASER',         'Heart'),                 # Crowd favorite
    ('SPIRITUAL_WINNER',      'Messi'),                 # Graceful top scorer
    ('PRE_MATCH_NERVOUS',     'Clutch'),                # High-stakes nervous
    ('PRE_MATCH',             'Analyst'),               # Pre-match thinking
    ('CONTROVERSIAL_DECISION','Italian'),               # Italian gesture of frustration
    ('REFEREE_PROTEST',       'Referee'),               # Referee protest
    ('ANIMATED_PROTEST',      'Protest'),               # Animated protest
    ('QUESTIONING_LOSS',      'What'),                  # Unbelievable defeat
    ('LONE_SURVIVOR',         'LastManStanding'),       # Last man standing
    ('COMEBACK_VICTORY',      'ComebackKing'),          # Comeback victory
    ('EXPLOSIVE_JOY',         'Fist'),                  # Overhead punch
    ('TRIUMPHANT_ROAR',       'Roar'),                  # Triumphant roar
    ('CHEST_POUND',           'Chest'),                 # Chest pounding pride
    ('RUNAWAY_LEAD',          'Superman'),              # Airplane run celebration
    ('JERSEY_PULL',           'Jersey'),                # Jersey pull celebration
    ('DEVASTATING_LOSS',      'Shame'),                 # Kneeling in shame
    ('EMBARRASSING_MISTAKE',  'Facepalm'),              # Facepalm embarrassment
]

# Event type -> posture fallback
EVENT_TYPE_RULES = {
    'FAILED_BANKER':          'Badbeat',
    'PREDICTION_AGED_POORLY': 'Badbeat',
    'ELIMINATION':            'Shame',
    'OUTLIER_VICTORY':        'Siuuu',
    'THREE_FULLPOTTS':        'Roar',
    'BIG_MOVER_UP':           'Knee',
    'BIG_MOVER_DOWN':         'Badbeat',
    'GENERAL_DRAMA':          'Hear',
    'DEFAULT':                'Analyst',
}

RIVAL_POSTURE = 'Rival-left'

MEDIA_EXPRESSION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'media', 'avatars', 'Expression'
)

MEDIA_URL_PREFIX = '/media/avatars/Expression'
EXTENSIONS = ['.jpg', '.JPG', '.jpeg', '.JPEG', '.png', '.PNG']


def resolve_posture_path(initials: str, posture_name: str) -> str:
    """
    Resolves URL path for avatar initials and posture name.
    Tries physical file resolution; if not found, returns standard URL path
    so that browser renders broken image icon as requested.
    """
    if not initials or not posture_name:
        return f"{MEDIA_URL_PREFIX}/placeholder.jpg"

    clean_posture = posture_name.replace('The-', '').replace('The ', '')

    candidates = [
        f"{initials}_{posture_name}",
        f"{initials}_{clean_posture}",
        f"{initials}_{posture_name.lower()}",
        f"{initials}-{posture_name}",
        f"{initials}__{posture_name}",
    ]
    if posture_name.startswith('Rival'):
        typo = posture_name.replace('Rival', 'Rivel')
        candidates.append(f"{initials}_{typo}")
        candidates.append(f"{initials}-{typo}")

    for cand in candidates:
        for ext in EXTENSIONS:
            # Check standard extension (.jpg) and double dot extension (..jpg)
            for file_suffix in [ext, f".{ext.lstrip('.')}"]:
                filename = f"{cand}{file_suffix}"
                full_path = os.path.join(MEDIA_EXPRESSION_DIR, filename)
                if os.path.isfile(full_path):
                    return f"{MEDIA_URL_PREFIX}/{filename}"

    # Return expected path even if file is missing (browser renders broken image icon)
    return f"{MEDIA_URL_PREFIX}/{initials}_{posture_name}.jpg"


def pick_posture(persona: dict, event_type: str, context_tags: set = None) -> tuple[str, str]:
    """
    Pick the best posture for a persona given the event type and context tags.
    """
    initials = persona.get('initials', '')
    context_tags = context_tags or set()

    for tag, posture in CONTEXT_TAG_RULES:
        if tag in context_tags:
            path = resolve_posture_path(initials, posture)
            return posture, path

    posture = EVENT_TYPE_RULES.get(event_type, EVENT_TYPE_RULES['DEFAULT'])
    path = resolve_posture_path(initials, posture)
    return posture, path


def pick_rivalry_avatars(
    primary_persona: dict,
    rival_persona: dict,
    event_type: str,
    context_tags: set = None,
    rivalry_mode: bool = False
) -> dict:
    """
    Returns posture selections for both primary player and rival.
    """
    result = {}

    if primary_persona:
        primary_initials = primary_persona.get('initials', '')
        if rivalry_mode:
            posture_name = 'Rival-right'
            path = resolve_posture_path(primary_initials, posture_name)
        else:
            posture_name, path = pick_posture(primary_persona, event_type, context_tags)
        result['primary'] = {
            'posture': posture_name,
            'path': path,
            'name': primary_persona.get('full_name', ''),
            'nick': (primary_persona.get('nicknames') or [''])[0],
            'initials': primary_initials,
        }
    else:
        result['primary'] = {'posture': None, 'path': None, 'name': '', 'nick': '', 'initials': ''}

    if rival_persona:
        rival_initials = rival_persona.get('initials', '')
        rival_path = resolve_posture_path(rival_initials, RIVAL_POSTURE)
        result['rival'] = {
            'posture': RIVAL_POSTURE,
            'path': rival_path,
            'name': rival_persona.get('full_name', ''),
            'nick': (rival_persona.get('nicknames') or [''])[0],
            'initials': rival_initials,
        }
    else:
        result['rival'] = {'posture': None, 'path': None, 'name': '', 'nick': '', 'initials': ''}

    return result
