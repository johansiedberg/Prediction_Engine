"""
art_director.py
---------------
Role 5: Art Director for Daily Gazette Editorial Engine.

Responsible for:
1. Classifying events into 4 Editorial Arcs:
   - Arc 1: The Betting & Build-Up Arc (Analyst, Clutch, Rival-left, Rival-right)
   - Arc 2: The Frustration & Protest Arc (Badbeat, Shame, Facepalm, Italian, Referee, Protest, What)
   - Arc 3: The General Victory Arc (LastManStanding, ComebackKing, Fist, Roar, Chest, Superman, Jersey)
   - Arc 4: The Signature Celebrations Arc (Zen, Bane, Siuuu, Messi, Sharpshooter, Knee, Silence, Heart, Hear)
2. Selecting visual artwork and avatar postures matching the HEADLINE event.
3. Determining visual layout mode (RIVALRY_PANEL for face-offs, SINGLE_AVATAR, or ART_BANNER).
"""

from tournament.editorial_engine.posture_engine import pick_rivalry_avatars, POSTURE_ARCS


class ArtDirector:
    """
    Art Director component that decides the visual layout, posture expression, and editorial arc.
    """

    @staticmethod
    def classify_editorial_arc(posture: str) -> str:
        """
        Classifies a posture into one of the 4 Editorial Arcs.
        """
        for arc, postures in POSTURE_ARCS.items():
            if posture in postures:
                return arc
        return "BUILD_UP"

    @classmethod
    def select_visuals(cls,
                       primary_persona: dict = None,
                       rival_persona: dict = None,
                       event_type: str = 'DEFAULT',
                       context_tags: set = None,
                       content_format: str = 'STANDARD_COLUMN') -> dict:
        """
        Main entry point for Art Director visual selection.

        Returns:
            Structured dictionary with image paths, postures, editorial arc, and layout metadata.
        """
        is_rivalry = (content_format == 'WINNERS_LOSERS') or (rival_persona is not None)

        rivalry_avatars = pick_rivalry_avatars(
            primary_persona=primary_persona,
            rival_persona=rival_persona,
            event_type=event_type,
            context_tags=context_tags,
            rivalry_mode=is_rivalry
        )

        primary_path = rivalry_avatars.get('primary', {}).get('path')
        rival_path = rivalry_avatars.get('rival', {}).get('path')
        primary_posture = rivalry_avatars.get('primary', {}).get('posture')
        rival_posture = rivalry_avatars.get('rival', {}).get('posture')

        editorial_arc = cls.classify_editorial_arc(primary_posture)

        if is_rivalry and primary_path and rival_path:
            visual_mode = 'RIVALRY_PANEL'
            image_url = primary_path
        elif primary_path:
            visual_mode = 'SINGLE_AVATAR'
            image_url = primary_path
        else:
            visual_mode = 'ART_BANNER'
            if content_format == 'INTERVIEW':
                image_url = "/static/tournament/img/gazette_interview_art.jpg"
            elif content_format == 'PUB_QUOTES':
                image_url = "/static/tournament/img/gazette_pub_art.jpg"
            else:
                image_url = "/static/tournament/img/gazette_editorial_art.jpg"

        return {
            'visual_mode': visual_mode,
            'editorial_arc': editorial_arc,
            'image_url': image_url,
            'rivalry_panel': rivalry_avatars,
            'primary_posture': primary_posture,
            'rival_posture': rival_posture,
            'primary_avatar_path': primary_path,
            'rival_avatar_path': rival_path,
        }

    @classmethod
    def select_three_avatar_special_edition_visuals(cls, featured_players: list) -> dict:
        """
        Art Director layout selection for Special Edition 3-Avatar merged illustrations.
        Assigns 3 distinct individual postures (e.g. Knee, Crossed-Arms, Point-Up).
        """
        postures = ['Knee', 'Crossed-Arms', 'Point-Up', 'Zen', 'Roar', 'Sharpshooter']
        avatars = []
        
        for idx, player_info in enumerate(featured_players[:3]):
            p_name = player_info.get('name', f'Spelare {idx+1}')
            p_role = player_info.get('role', 'CONTENDER')
            p_posture = postures[idx % len(postures)]
            avatars.append({
                'name': p_name,
                'role': p_role,
                'posture': p_posture,
                'avatar_path': f"/static/tournament/img/avatars/{p_name.lower().replace(' ', '_')}_{p_posture.lower()}.png"
            })

        prompt_summary = (
            f"Editorial magazine 3-avatar composite artwork featuring {avatars[0]['name']} ({avatars[0]['posture']}), "
            f"{avatars[1]['name']} ({avatars[1]['posture']}), and {avatars[2]['name']} ({avatars[2]['posture']}) "
            f"in individual distinct postures with purple accent lighting and magazine header styling."
        )

        return {
            'visual_mode': 'THREE_AVATAR_COMPOSITE',
            'editorial_arc': 'SPECIAL_MAGAZINE',
            'avatars': avatars,
            'image_prompt': prompt_summary,
            'image_url': "/static/tournament/img/gazette_special_edition_art.jpg",
        }
