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

from tournament.editorial_engine.posture_engine import pick_rivalry_avatars, POSTURE_ARCS, resolve_portrait_url


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
        is_winner_loser = (content_format == 'WINNERS_LOSERS')
        is_rivalry = (content_format in ('HEAD_TO_HEAD_DUEL', 'RIVALRY_PANEL', 'RIVALRY')) and (rival_persona is not None)

        rivalry_avatars = pick_rivalry_avatars(
            primary_persona=primary_persona,
            rival_persona=rival_persona,
            event_type=event_type,
            context_tags=context_tags,
            rivalry_mode=is_rivalry,
            winner_loser_mode=is_winner_loser
        )

        primary_path = rivalry_avatars.get('primary', {}).get('path')
        rival_path = rivalry_avatars.get('rival', {}).get('path')
        primary_posture = rivalry_avatars.get('primary', {}).get('posture')
        rival_posture = rivalry_avatars.get('rival', {}).get('posture')

        # --- Portrait fallback for Toarps Herrklubb ---
        import os
        from tournament.editorial_engine.posture_engine import (
            EXPRESSION_STATIC_DIR, MEDIA_EXPRESSION_DIR, PORTRAIT_STATIC_DIR
        )

        def _path_exists_on_disk(url_path: str) -> bool:
            """Check if a /static/... or /media/... URL actually has a file on disk."""
            if not url_path:
                return False
            if '/static/tournament/images/avatars/Expressions/' in url_path:
                filename = url_path.split('/static/tournament/images/avatars/Expressions/')[-1]
                return os.path.isfile(os.path.join(EXPRESSION_STATIC_DIR, filename))
            if '/media/avatars/Expression/' in url_path:
                filename = url_path.split('/media/avatars/Expression/')[-1]
                return os.path.isfile(os.path.join(MEDIA_EXPRESSION_DIR, filename))
            if '/static/tournament/images/avatars/' in url_path:
                filename = url_path.split('/static/tournament/images/avatars/')[-1]
                return os.path.isfile(os.path.join(PORTRAIT_STATIC_DIR, filename))
            return True

        def _resolve_with_portrait_fallback(avatar_dict: dict) -> str:
            path = avatar_dict.get('path')
            if _path_exists_on_disk(path):
                return path
            # Expression pose missing — try portrait photo
            full_name = avatar_dict.get('name', '')
            portrait = resolve_portrait_url(full_name)
            return portrait if portrait else path

        if rivalry_avatars.get('primary'):
            primary_path = _resolve_with_portrait_fallback(rivalry_avatars['primary'])
            rivalry_avatars['primary']['path'] = primary_path
        if rivalry_avatars.get('rival'):
            rival_path = _resolve_with_portrait_fallback(rivalry_avatars['rival'])
            rivalry_avatars['rival']['path'] = rival_path
        # -----------------------------------------------

        editorial_arc = cls.classify_editorial_arc(primary_posture)

        if is_rivalry and primary_path and rival_path:
            visual_mode = 'RIVALRY_PANEL'
            image_url = primary_path
        elif primary_path:
            visual_mode = 'SINGLE_AVATAR'
            image_url = primary_path
        else:
            visual_mode = 'ART_BANNER'
            image_url = "/static/tournament/img/gazette_default_cover.jpg"

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
