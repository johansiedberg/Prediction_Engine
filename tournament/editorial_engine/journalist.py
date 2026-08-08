"""
journalist.py
-------------
Role 2: Journalist for Daily Gazette Editorial Engine.

Responsible for:
1. Researching historical news background and weaving it organically into the narrative.
2. Translating player traits into vivid behavioral actions ("Show, Don't Tell").
3. Prominently featuring actual match result facts and side-by-side head-to-head comparisons for rivalries (comparing both Dahl & Svensson).
4. Drafting doubled-length story texts for HEADLINE (6 paragraphs), EVENT 1, and EVENT 2.
"""

from tournament.models import StorylineMemory, DailyGazette

BEHAVIOR_DESCRIPTIONS = {
    "Johan Siedberg": "studerade kalkylerna in i minsta detalj och analyserade sannolikhetsmatriser långt in på småtimmarna",
    "Mikael Dahl": "vandrade fram och tillbaka med hög energi, fylld av speliver och snabba utspel kring oddsen",
    "Andreas Larsson": "behöll sitt orubbliga pokersinnen och granskade läget med jägarens tålamod",
    "Johan Svensson": "justerade kaffemaskinens tryck med millimeterprecision samtidigt som han levererade sina torra slutsatser",
    "Johan Meldo": "följde gruppens alla turer med sjukgymnastens skarpa blick och tålmodiga lugn",
    "Erik Svensson": "skruvade upp den tunga hårdrocken på högsta volym för att dränka ljudet av omgångens alla bakslag",
    "Christoffer Ericsson": "granskade siffrorna med den norske fjälldirektörens svala och skarpa distans",
    "Martin Gustafsson": "drev på sina analyser med den idrottsrektorlika disciplin som krävs i branta uppförsbackar",
    "Tommy Lycen": "reflekterade över fotbollstaktiken på uteserveringen med den tailored elegans som kännetecknar en ex-elitanfallare",
    "Tommy Källberg": "lutade sig tillbaka med en kall öl och en pizza i lugn och ro medan rörläggarkalkylerna stämdes av",
    "Martin Krantz": "drog igång en medryckande och dramatisk berättelse fylld av italiensk fotbollspassion",
}


class Journalist:
    """
    Journalist component that builds doubled-length news stories with behavior-based character portrayals,
    actual match result facts, side-by-side rivalry comparisons, and organic historical news integration.
    """

    @staticmethod
    def get_nickname(persona: dict) -> str:
        """Extracts primary nickname from persona dict."""
        if not persona:
            return "Tipparen"
        nicks = persona.get('nicknames', [])
        if nicks and len(nicks) > 0 and nicks[0]:
            return nicks[0]
        return persona.get('full_name', 'Tipparen')

    @staticmethod
    def get_behavior(persona: dict) -> str:
        """Translates persona traits into active behavior descriptions."""
        if not persona:
            return "följde matchutvecklingen med stort intresse"
        full_name = persona.get('full_name', '')
        return BEHAVIOR_DESCRIPTIONS.get(full_name, "granskade tipsraderna noggrant inför slutsignalen")

    @classmethod
    def research_historical_background(cls, tournament=None, primary_persona: dict = None, rival_persona: dict = None) -> dict:
        """
        Researches past gazette news and storyline memory for primary player
        and past rivalry battles between primary & rival.
        """
        individual_history = []
        rivalry_history = []

        p_name = primary_persona.get('full_name') if primary_persona else None
        r_name = rival_persona.get('full_name') if rival_persona else None
        p_nick = cls.get_nickname(primary_persona)
        r_nick = cls.get_nickname(rival_persona) if rival_persona else None

        if p_name:
            p_memories = StorylineMemory.objects.filter(player_name=p_name, is_active=True).order_by('-last_updated')[:2]
            for mem in p_memories:
                individual_history.append(mem.narrative)

        if p_name and r_name and tournament:
            past_gazettes = DailyGazette.objects.filter(tournament=tournament).order_by('-publish_date')[:5]
            for g in past_gazettes:
                content_lower = g.content.lower() + " " + g.headline.lower()
                if (p_name.lower() in content_lower or p_nick.lower() in content_lower) and \
                   (r_name.lower() in content_lower or (r_nick and r_nick.lower() in content_lower)):
                    rivalry_history.append(f"från {g.publish_date} gällande '{g.headline}'")

        return {
            'individual_history': individual_history,
            'rivalry_history': rivalry_history,
        }

    @classmethod
    def draft_edition_stories(cls, publisher_layout: dict, primary_persona: dict = None, rival_persona: dict = None, tournament=None) -> dict:
        """
        Drafts doubled-length stories featuring actual match scoreline facts and side-by-side rivalry comparisons.
        """
        p_desc = publisher_layout.get('headline_description', '')
        s_desc = publisher_layout.get('event2_description', '')
        t_desc = publisher_layout.get('event3_description', '')
        fmt = publisher_layout.get('content_format', 'STANDARD_COLUMN')

        # Research historical news coverage
        history = cls.research_historical_background(tournament, primary_persona, rival_persona)
        ind_notes = history['individual_history']
        riv_notes = history['rivalry_history']

        p_name = primary_persona.get('full_name', 'Tipparen') if primary_persona else "Tipparen"
        p_nick = cls.get_nickname(primary_persona)
        p_behavior = cls.get_behavior(primary_persona)

        r_nick = cls.get_nickname(rival_persona) if rival_persona else None
        r_behavior = cls.get_behavior(rival_persona) if rival_persona else None

        # Build Organic Background Context
        organic_history_text = ""
        if riv_notes and r_nick:
            past_ref = riv_notes[0]
            organic_history_text = (
                f" Kampen mellan {p_nick} och {r_nick} bygger vidare på en lång historisk rivalitet i gänget, "
                f"där tidigare drabbningar {past_ref} satte tonen för kvällens uppgörelse."
            )
        elif ind_notes:
            past_ref = ind_notes[0]
            organic_history_text = (
                f" Detta utgör nästa kapitel i den följetong som inleddes när {past_ref} senast uppmärksammades i ligan."
            )

        # Headline Title & Tagline Drafting
        if fmt == 'WINNERS_LOSERS' and r_nick:
            headline_title = f"RIVALITETEN KOKAR: {p_nick.upper()} MOT {r_nick.upper()}!"
            tagline = f"Historisk uppgörelse • {p_nick} vs {r_nick} • Analys av omgångens utfall"
        elif fmt == 'INTERVIEW':
            headline_title = f"EXKLUSIVT MED {p_nick.upper()}: 'HISTORIEN UPPREPAR SIG!'"
            tagline = f"Intervju efter omgången • Med {p_nick}"
        else:
            headline_title = f"{p_nick.upper()} I CENTRUM NÄR OMGÅNGEN AVGJORDS!"
            tagline = f"Dramatik på hög nivå • Analys av omgångens alla nyckelhändelser • Med {p_nick}"

        # Clean Factual Match Result Sentence
        fact_sentence = p_desc.strip()
        if not fact_sentence.endswith('.'):
            fact_sentence += '.'

        # Doubled Headline Article Text (6 full paragraphs with actual match facts and rival comparison)
        p1 = f"Omgången bjöd på ett enastående drama som satte djupa spår i tabellen. Matchfakta: {fact_sentence}"
        p2 = f"Inför matchstart {p_nick} {p_behavior}, medan förväntningarna var uppskruvade till max i gruppchatten."

        if r_nick and r_behavior:
            p3 = (
                f"I direkt kontrast till {p_nick}s tunga omgång utnyttjade {r_nick} situationen till sin fulla fördel. "
                f"Medan {p_nick} {p_behavior}, klättrade {r_nick} stabilt i tabellen och plockade viktiga poäng. "
                f"Inför avspark {r_nick} {r_behavior}, vilket skapade en extremt laddad stämning kring pubbordet."
            )
            p4 = (
                f"Jämförelsen mellan herrarna visar en dramatisk skillnad i omgångens utfall: medan {p_nick} rasade i tabelläget "
                f"och tvingades räkna in en tung förlust, lyckades {r_nick} hålla kalkylen intakt och rycka i poängstriden. "
                f"Maktkampen mellan {p_nick} och {r_nick} tätnade för varje spelad minut när slutresultatet spikades.{organic_history_text}"
            )
        else:
            p3 = f"När slutsignalen väl ljöd stod det klart att alla förhandskalkyler ställdes helt på ända av matchresultatet, vilket utlöste livliga diskussioner kring pubbordet."
            p4 = f"Ingen i hela ligan kunde förutse den dramatiska vändning som utspelade sig under kvällens sista spelminuter när resultatet registrerades.{organic_history_text}"

        p5 = f"Det taktiska chanstagandet kring matchresultatet fick omedelbara konsekvenser i sammandraget, där marginalerna mellan jubel och djup besvikelse visade sig vara försvinnande små."
        p6 = f"Reaktionerna bland övriga tippare lät inte vänta på sig, och kommentarerna haglade tätt när gänget analyserade de faktiska matchresultaten och poängtabellen inför nästa drabbning."

        top_story = f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}\n\n{p5}\n\n{p6}"

        # Doubled EVENT 1 Text with actual match facts
        s_fact = s_desc.strip()
        if not s_fact.endswith('.'):
            s_fact += '.'
        event2_text = (
            f"Faktiskt Matchresultat & Analys: {s_fact} Händelsen skakade om hela toppstriden och utlöste en storm av reaktioner i gänget. "
            f"Flera tippare tvingades se sina förhandstips rasa samman när matchens slutskede bjöd på oväntad dramatik och poängtapp."
        )

        # Doubled EVENT 2 Text with actual match facts
        t_fact = t_desc.strip()
        if not t_fact.endswith('.'):
            t_fact += '.'
        event3_text = (
            f"Statistisk Resultatanalys: {t_fact} Statistiken visar att detta var en av de mest svårtippade händelserna under hela turneringen. "
            f"Den analytiska avvikelsen rörde om hårt i poängtabellen och förändrade förutsättningarna inför de kommande avgörande omgångarna."
        )

        return {
            'headline': headline_title,
            'tagline': tagline,
            'top_story': top_story,
            'event2_text': event2_text,
            'event3_text': event3_text,
            'primary_nick': p_nick,
            'rival_nick': r_nick,
            'historical_notes': ind_notes + riv_notes,
        }
