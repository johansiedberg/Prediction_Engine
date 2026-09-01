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
    "FRUSTRATION": ["Badbeat", "Shame", "Facepalm", "What", "Me"],
    "VICTORY": ["Fist", "Roar", "Chest", "Jersey", "Knee"],
    "SIGNATURE_CELEBRATION": ["Zen", "Bane", "Siuuu", "Messi", "Sharpshooter", "Silence", "Heart", "Hear"]
}

# Context tag -> posture trigger rules (checked top to bottom in priority order)
CONTEXT_TAG_RULES = [
    # Tier 1: Exceptional round achievements & heroic predictions
    ('OUTLIER_VICTORY',       'Siuuu'),                 # Single hero win / Ensamvarg
    ('THREE_FULLPOTTS',       'Roar'),                  # Multiple exact fullpotts in round
    ('CORRECT_EXACT_SCORE',   'Sharpshooter'),          # Exact score sniper
    ('TOP_SCORER',            'Sharpshooter'),          # Top score of round
    ('EXPLOSIVE_JOY',         'Fist'),                  # Overhead punch celebration
    ('TRIUMPHANT_ROAR',       'Roar'),                  # Triumphant roar
    ('COMEBACK_VICTORY',      'Knee'),                  # Comeback knee slide
    ('BIG_MOVER_UP',          'Knee'),                  # Rocket climb up the table
    ('LONE_SURVIVOR',         'Chest'),                 # Lone survivor / chest pound
    ('CHEST_POUND',           'Chest'),                 # Chest pounding pride
    ('JERSEY_PULL',           'Jersey'),                # Club loyalty / shirt pull

    # Tier 2: Agony, disaster, shock & blame deflection
    ('FAILED_BANKER',         'Badbeat'),               # Spikkrasch / failed banker
    ('PREDICTION_AGED_POORLY','Badbeat'),               # Prediction collapsed late
    ('QUESTIONING_LOSS',      'What'),                  # Unbelievable defeat / shock upset
    ('CONTROVERSIAL_DECISION','What'),                  # Disputed call / disbelief
    ('REFEREE_PROTEST',       'What'),                  # Shocked protest
    ('ANIMATED_PROTEST',      'What'),                  # Frustrated disbelief
    ('EMBARRASSING_MISTAKE',  'Facepalm'),              # Obvious blunder / zero points
    ('BLUNDER',               'Facepalm'),              # Costly misjudgment
    ('SCAPEGOATED',           'Me'),                    # "Who, me?!" — blamed / comical denial
    ('BOTTOM_RANK',           'Me'),                    # Bottom rank / last place defense
    ('DEVASTATING_LOSS',      'Shame'),                 # Kneeling in shame
    ('BIG_MOVER_DOWN',        'Shame'),                 # Rapid fall down table
    ('ELIMINATION',           'Shame'),                 # Knocked out of contention

    # Tier 3: Dominance, composure, swagger & signature poses
    ('IS_TOURNAMENT_LEADER',  'Bane'),                  # Overall leader swagger
    ('RUNAWAY_LEAD',          'Bane'),                  # Massive lead / boss posture
    ('IS_STANDINGS_TOP3',     'Zen'),                   # Top 3 calm composure
    ('DOUBTED_BUT_WON',       'Silence'),               # Shushing doubters
    ('SPIRITUAL_WINNER',      'Messi'),                 # Graceful top scorer
    ('CROWD_PLEASER',         'Heart'),                 # Fan favorite / making heart
    ('HEAR_THE_NOISE',        'Hear'),                  # Hand to ear / listening to chatter

    # Tier 4: Pre-match & build-up
    ('PRE_MATCH_NERVOUS',     'Clutch'),                # High-stakes nervous
    ('PRE_MATCH',             'Analyst'),               # Pre-match thinking
]

# Event type -> posture fallback
EVENT_TYPE_RULES = {
    'OUTLIER_VICTORY':        'Siuuu',
    'THREE_FULLPOTTS':        'Roar',
    'GOAL_FEST':              'Roar',
    'FAILED_BANKER':          'Badbeat',
    'PREDICTION_AGED_POORLY': 'Badbeat',
    'ELIMINATION':            'Shame',
    'BIG_MOVER_UP':           'Knee',
    'BIG_MOVER_DOWN':         'Badbeat',
    'GENERAL_DRAMA':          'Hear',
    'BLUNDER':                'Facepalm',
    'DISBELIEF':              'What',
    'SCAPEGOAT':              'Me',
    'DEFAULT':                'Analyst',
}

RIVAL_POSTURE = 'Rival-left'

EXPRESSION_STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'tournament', 'static', 'tournament', 'images', 'avatars', 'Expressions'
)
# Legacy aliases kept for ArtDirector._path_exists_on_disk compatibility
MEDIA_EXPRESSION_DIR = EXPRESSION_STATIC_DIR
MEDIA_URL_PREFIX = '/static/tournament/images/avatars/Expressions'
EXTENSIONS = ['.jpg', '.JPG', '.jpeg', '.JPEG', '.png', '.PNG']


# ---------------------------------------------------------------------------
# Portrait URL Resolution (real member photos from static)
# ---------------------------------------------------------------------------

# Base directory of actual member portrait photos
PORTRAIT_STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'tournament', 'static', 'tournament', 'images', 'avatars'
)
PORTRAIT_URL_PREFIX = '/static/tournament/images/avatars'


def resolve_portrait_url(full_name: str, avatar_filename: str = None) -> str:
    """
    Resolves the static portrait URL for a Toarps Herrklubb player.

    Looks inside `tournament/static/tournament/images/avatars/` for a photo
    matching `avatar_filename` from player_personas.json (e.g. 'Johan Siedberg.jpg').
    Falls back to searching by first/last name if the filename hint isn't found.

    Returns a /static/... URL on success, or an empty string if not found.
    """
    # Primary: try avatar_filename from persona definition
    if avatar_filename:
        for ext in EXTENSIONS:
            base = avatar_filename.rsplit('.', 1)[0] if '.' in avatar_filename else avatar_filename
            for suffix in [avatar_filename, f"{base}{ext}"]:
                candidate = os.path.join(PORTRAIT_STATIC_DIR, suffix)
                if os.path.isfile(candidate):
                    return f"{PORTRAIT_URL_PREFIX}/{suffix}"

    # Secondary: try full_name directly with various extensions
    if full_name:
        for ext in EXTENSIONS:
            filename = f"{full_name}{ext}"
            candidate = os.path.join(PORTRAIT_STATIC_DIR, filename)
            if os.path.isfile(candidate):
                return f"{PORTRAIT_URL_PREFIX}/{filename}"

    return ''



def resolve_posture_path(initials: str, posture_name: str) -> str:
    """
    Resolves the static URL for an expression pose image.

    Tries many filename variants to cover the quirks present in the
    Expressions folder (double underscore, case variants, Rivel typos,
    double-dot extension, capitalisation of Rival-Right, etc.).
    Returns the URL on success; returns a guessed URL (which will render
    as a broken image) if no file is found.
    """
    if not initials or not posture_name:
        return f"{MEDIA_URL_PREFIX}/placeholder.jpg"

    # Build a rich candidate list covering every known quirk in the folder
    p = posture_name
    p_lower = p.lower()
    p_upper_first = p[0].upper() + p[1:] if p else p

    candidates = [
        f"{initials}_{p}",            # Standard: MK_Roar
        f"{initials}__{p}",           # Double underscore: MK__Analyst
        f"{initials}_{p_lower}",      # Lowercase: TK_chest
        f"{initials}_{p_upper_first}", # Capitalised: TL_Chest
        f"{initials}-{p}",            # Dash separator: JSV-Rival-left
    ]

    # Rival / Rivel variants
    if 'Rival' in p or 'rival' in p:
        # Rival-Right capitalisation (TL)
        candidates.append(f"{initials}_{p.replace('Rival-right', 'Rival-Right').replace('Rival-left', 'Rival-Left')}")
        # Rivel typo (JSI)
        candidates.append(f"{initials}_{p.replace('Rival', 'Rivel')}")

    for cand in candidates:
        for ext in EXTENSIONS:
            # Normal extension: JSV_Rival-right.jpg
            filename = f"{cand}{ext}"
            if os.path.isfile(os.path.join(EXPRESSION_STATIC_DIR, filename)):
                return f"{MEDIA_URL_PREFIX}/{filename}"
            # Double-dot extension: JSV_Rival-right..jpg (known typo in some files)
            filename2 = f"{cand}.{ext}"
            if os.path.isfile(os.path.join(EXPRESSION_STATIC_DIR, filename2)):
                return f"{MEDIA_URL_PREFIX}/{filename2}"

    # Fallback — returns guessed URL (browser shows broken image)
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
    rivalry_mode: bool = False,
    winner_loser_mode: bool = False,
) -> dict:
    """
    Returns posture selections for both primary player and rival.
    If winner_loser_mode is True, primary gets an expressive victory posture
    and rival gets an agony/frustration posture.
    If rivalry_mode is True, both use face-to-face dueling postures (Rival-right and Rival-left).
    """
    result = {}
    context_tags = context_tags or set()

    if primary_persona:
        primary_initials = primary_persona.get('initials', '')
        if winner_loser_mode:
            # Winner celebration
            win_tags = context_tags | {'TRIUMPHANT_ROAR', 'EXPLOSIVE_JOY'}
            posture_name, path = pick_posture(primary_persona, event_type, win_tags)
        elif rivalry_mode:
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
        if winner_loser_mode:
            # Loser frustration / agony / "Who, me?!"
            lose_tags = {'DEVASTATING_LOSS', 'BOTTOM_RANK', 'FAILED_BANKER'}
            posture_name, rival_path = pick_posture(rival_persona, 'FAILED_BANKER', lose_tags)
        elif rivalry_mode:
            posture_name = RIVAL_POSTURE  # 'Rival-left'
            rival_path = resolve_posture_path(rival_initials, posture_name)
        else:
            posture_name, rival_path = pick_posture(rival_persona, event_type, context_tags)
        result['rival'] = {
            'posture': posture_name,
            'path': rival_path,
            'name': rival_persona.get('full_name', ''),
            'nick': (rival_persona.get('nicknames') or [''])[0],
            'initials': rival_initials,
        }
    else:
        result['rival'] = {'posture': None, 'path': None, 'name': '', 'nick': '', 'initials': ''}

    return result

