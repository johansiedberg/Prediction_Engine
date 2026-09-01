"""
journalist.py
-------------
Role 2: Journalist for Daily Gazette Editorial Engine.

Responsible for:
1. Researching historical news background and weaving it organically into the narrative.
2. Translating player traits into vivid behavioral actions ("Show, Don't Tell") with correct Swedish V2 word order.
3. Classifying narrative polarity (LEADER_TRIUMPH, FALLER_COLLAPSE, HEAD_TO_HEAD_DUEL, GENERAL_STAGE).
4. Generating coherent, non-contradictory 6-paragraph stories with zero duplicate sentences.
"""

from tournament.models import StorylineMemory, DailyGazette

BEHAVIORS_V2 = {
    "Johan Siedberg": {
        "pre_match": "studerade Siedberg kalkylerna in i minsta detalj och analyserade sannolikhetsmatriser",
        "in_action": "förlitade sig Siedberg på sin djupgående dataanalys och noggrant kalkylerade risker",
        "post_match": "konstaterade Siedberg med matematisk precision att siffrorna talade sitt tydliga språk",
    },
    "Mikael Dahl": {
        "pre_match": "vandrade Dahl fram och tillbaka med hög energi och snabba utspel kring oddsen",
        "in_action": "satsade Dahl med sedvanlig speliver och heta känslor i varje tipsdrag",
        "post_match": "manade Dahl på diskussionerna kring bordet med oförminskad intensitet",
    },
    "Andreas Larsson": {
        "pre_match": "behöll Larsson sitt orubbliga pokersinnen och granskade läget med jägarens tålamod",
        "in_action": "spelade Larsson iskallt och lät motståndarna ta de onödiga riskerna",
        "post_match": "summerade Larsson läget med ett svalt leende och full kontroll",
    },
    "Johan Svensson": {
        "pre_match": "justerade Svensson kaffemaskinens tryck med millimeterprecision och levererade sina torra slutsatser",
        "in_action": "litade Svensson på sin beprövade metodik och metodiska lugn",
        "post_match": "noterade Svensson krasst att tabellen aldrig ljuger",
    },
    "Johan Meldo": {
        "pre_match": "följde Meldo gruppens alla turer med sjukgymnastens skarpa blick och tålmodiga lugn",
        "in_action": "arbetade Meldo metodiskt för att hitta luckorna i topptipparnas rader",
        "post_match": "behöll Meldo lugnet och konstaterade att maratonloppet bara har börjat",
    },
    "Erik Svensson": {
        "pre_match": "skruvade Erik upp den tunga hårdrocken på högsta volym för att sätta rätt stämning",
        "in_action": "sökte Erik de tunga skrällarna med maximal attack och kompromisslös stil",
        "post_match": "lät Erik hårdrocken dåna vidare medan omgångens facit summerades",
    },
    "Christoffer Ericsson": {
        "pre_match": "granskade Ericsson siffrorna med den norske fjälldirektörens svala och skarpa distans",
        "in_action": "styrde Ericsson sina tips med kylig överblick och beräknande precision",
        "post_match": "blickade Ericsson ut över tabellen från sin strategiska position",
    },
    "Martin Gustafsson": {
        "pre_match": "drev Gustafsson på analyserna med den idrottsrektorlika disciplin som krävs i branta uppförsbackar",
        "in_action": "krävde Gustafsson hundraprocentigt fokus i varje enskild matchanalys",
        "post_match": "blåste Gustafsson av omgången med disciplinerad beslutsamhet",
    },
    "Tommy Lycen": {
        "pre_match": "reflekterade Lycén över fotbollstaktiken på uteserveringen med den tailored elegans som kännetecknar en ex-elitanfallare",
        "in_action": "läste Lycén matchbilderna med det målgöraröga som bara en ex-elitanfallare besitter",
        "post_match": "analyserade Lycén anfallsspelets finesser med sofistikerad fingertoppskänsla",
    },
    "Tommy Källberg": {
        "pre_match": "lutade sig Källberg tillbaka med en kall öl och en pizza medan rörläggarkalkylerna stämdes av",
        "in_action": "höll Källberg fast vid sina stabila grundtips utan onödig stress",
        "post_match": "tog Källberg ett djupt andetag och lät tabelläget tala för sig självt",
    },
    "Martin Krantz": {
        "pre_match": "drog Krantz igång en medryckande och dramatisk berättelse fylld av italiensk fotbollspassion",
        "in_action": "manövrerade Krantz sina tipsrader med syditaliensk glöd och kompromisslös vinnarskalle",
        "post_match": "fäktade Krantz med händerna och slog fast att mästerskapet är ett taktiskt konstverk",
    },
}

# Legacy fallback for backwards compatibility
BEHAVIOR_DESCRIPTIONS = {
    name: actions["pre_match"] for name, actions in BEHAVIORS_V2.items()
}


class Journalist:
    """
    Journalist component that builds coherent, non-contradictory news stories with
    polarity-aware narrative branches, Swedish V2 word order, and zero repetitive phrasing.
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

    @classmethod
    def get_behavior_v2(cls, persona: dict, phase: str = "pre_match") -> str:
        """Translates persona into grammatically correct Swedish V2 actions."""
        if not persona:
            if phase == "pre_match":
                return "granskade tipparen förutsättningarna med stor koncentration"
            elif phase == "in_action":
                return "bevakade tipparen varje tipsrad med taktisk blick"
            return "summerade tipparen resultaten noggrant"
        
        full_name = persona.get('full_name', '')
        if full_name in BEHAVIORS_V2:
            return BEHAVIORS_V2[full_name].get(phase, BEHAVIORS_V2[full_name]["pre_match"])
        
        nick = cls.get_nickname(persona)
        if phase == "pre_match":
            return f"granskade {nick} matcherna med stor koncentration"
        elif phase == "in_action":
            return f"kämpade {nick} taktiskt om varje poäng"
        return f"analyserade {nick} tabelläget inför fortsättningen"

    @classmethod
    def get_behavior(cls, persona: dict) -> str:
        """Legacy helper."""
        return cls.get_behavior_v2(persona, "pre_match")

    @classmethod
    def detect_narrative_polarity(cls, headline_desc: str, headline_type: str, primary_nick: str, rival_nick: str = None) -> str:
        """
        Determines the true narrative polarity to ensure story tone matches factual event data.
        """
        desc_lower = headline_desc.lower()
        
        # Check faller keywords first to prevent '0 fullpottar' from being counted as leader
        is_faller = any(k in desc_lower for k in [
            'tuff period', 'tappade', 'rasade', 'noll poäng', 'bottennapp', 'besvikelse', 'bakslag', 'tung omgång', '0 fullpott', 'inga fullpott'
        ]) or headline_type in ['FAILED_BANKER']

        has_positive_fullpott = ('fullpott' in desc_lower or 'fullpottar' in desc_lower) and '0 fullpott' not in desc_lower and 'inga fullpott' not in desc_lower
        is_leader = (
            any(k in desc_lower for k in ['leder', 'ledningen', 'toppar', 'storspelade', 'spikade', 'förstaplats', 'ensam spelare', 'kopplat grepp', '100p'])
            or has_positive_fullpott
            or headline_type in ['OUTLIER_VICTORY', 'THREE_FULLPOTTS']
        )

        if is_faller and not is_leader:
            return 'FALLER_COLLAPSE'
        elif is_leader and not is_faller:
            return 'LEADER_TRIUMPH'
        elif is_faller and is_leader:
            if any(k in desc_lower for k in ['tuff', '0 fullpott', 'rasade', 'bottennapp', 'tappade']):
                return 'FALLER_COLLAPSE'
            return 'LEADER_TRIUMPH'
        elif rival_nick:
            return 'HEAD_TO_HEAD_DUEL'
        return 'GENERAL_STAGE'

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
        Drafts coherent, non-contradictory 6-paragraph stories with polarity-aware narrative branches.
        """
        p_desc = publisher_layout.get('headline_description', '')
        s_desc = publisher_layout.get('event2_description', '')
        t_desc = publisher_layout.get('event3_description', '')
        fmt = publisher_layout.get('content_format', 'STANDARD_COLUMN')
        h_type = publisher_layout.get('headline_type', 'GENERAL_DRAMA')

        history = cls.research_historical_background(tournament, primary_persona, rival_persona)
        ind_notes = history['individual_history']
        riv_notes = history['rivalry_history']

        p_nick = cls.get_nickname(primary_persona)
        r_nick = cls.get_nickname(rival_persona) if rival_persona else None

        p_pre_match = cls.get_behavior_v2(primary_persona, "pre_match")
        p_in_action = cls.get_behavior_v2(primary_persona, "in_action")
        r_pre_match = cls.get_behavior_v2(rival_persona, "pre_match") if rival_persona else ""
        r_in_action = cls.get_behavior_v2(rival_persona, "in_action") if rival_persona else ""

        # Build Organic History Reference
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

        # Detect Narrative Polarity
        polarity = cls.detect_narrative_polarity(p_desc, h_type, p_nick, r_nick)

        # ---------------------------------------------------------------------
        # Headline & Tagline Generation
        # ---------------------------------------------------------------------
        if polarity == 'LEADER_TRIUMPH':
            headline_title = f"{p_nick.upper()} I FÖRARSÄTET NÄR OMGÅNGEN AVGJORDS!"
            tagline = f"Ledarryck • {p_nick} håller undan i tabelltoppen • Analys av omgångens utfall"
        elif polarity == 'FALLER_COLLAPSE':
            headline_title = f"TUNGT BAKSLAG FÖR {p_nick.upper()} I TABELLSTRIDEN!"
            tagline = f"Dramatiskt poängtapp • Bakslag för {p_nick} • Analys av omgångens utfall"
        elif fmt == 'WINNERS_LOSERS' and r_nick:
            headline_title = f"RIVALITETEN KOKAR: {p_nick.upper()} MOT {r_nick.upper()}!"
            tagline = f"Historisk uppgörelse • {p_nick} vs {r_nick} • Analys av omgångens utfall"
        elif fmt == 'INTERVIEW':
            headline_title = f"EXKLUSIVT MED {p_nick.upper()}: 'FOKUS PÅ NÄSTA DRABBNING!'"
            tagline = f"Intervju efter omgången • Med {p_nick}"
        else:
            headline_title = f"{p_nick.upper()} I CENTRUM NÄR OMGÅNGEN AVGJORDS!"
            tagline = f"Dramatik på hög nivå • Analys av omgångens alla nyckelhändelser • Med {p_nick}"

        # Clean Factual Match Result Sentence
        fact_sentence = p_desc.strip()
        if not fact_sentence.endswith('.'):
            fact_sentence += '.'

        # ---------------------------------------------------------------------
        # Polarity-Aware 6-Paragraph Story Construction
        # ---------------------------------------------------------------------
        if polarity == 'LEADER_TRIUMPH':
            p1 = f"Omgången bjöd på ett enastående drama som satte djupa spår i tabellen. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, medan förväntningarna var uppskruvade till max i gruppchatten."
            
            if r_nick and r_in_action:
                p3 = (
                    f"Bakom ledaren jagade {r_nick} intensivt för att inte tappa kontakten med toppen. "
                    f"Under matchens gång {r_in_action}, samtidigt som jakten på ledartröjan skapade en extremt laddad stämning kring pubbordet."
                )
                p4 = (
                    f"Jämförelsen mellan herrarna visar att {p_nick} har kopplat ett starkt grepp om tabelltoppen, "
                    f"men marginalen gör att {r_nick} vägrar ge upp jakten i poängstriden. "
                    f"Maktkampen mellan {p_nick} och {r_nick} tätnade för varje spelad minut när slutresultatet spikades.{organic_history_text}"
                )
            else:
                p3 = f"Under matchernas gång {p_in_action}, vilket gav full utdelning när poängen räknades samman och tabelläget befästes."
                p4 = f"Ledningen sätter hård press på övriga tippare i gänget inför de kommande omgångarna.{organic_history_text}"

            p5 = f"Det taktiska spelet kring tipsraderna fick omedelbara konsekvenser i sammandraget, där marginalerna mellan triumf och besvikelse visade sig vara försvinnande små."
            p6 = f"Reaktionerna bland övriga tippare lät inte vänta på sig, och kommentarerna haglade tätt när gänget analyserade de faktiska matchresultaten och poängtabellen inför nästa drabbning."

        elif polarity == 'FALLER_COLLAPSE':
            p1 = f"Omgången bjöd på oväntade motgångar som skakade om tabelläget i grunden. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, ovetande om den hårda utmaning som väntade vid slutsignalen."

            if r_nick and r_in_action:
                p3 = (
                    f"I direkt kontrast till {p_nick}s tunga omgång utnyttjade {r_nick} situationen till sin fulla fördel. "
                    f"Medan motståndet vacklade {r_in_action}, vilket gav viktiga poäng i klättringen uppåt."
                )
                p4 = (
                    f"Jämförelsen mellan herrarna visar en dramatisk skillnad i omgångens utfall: medan {p_nick} tvingades räkna in ett kännbart bakslag, "
                    f"lyckades {r_nick} hålla kalkylen intakt och rycka i poängstriden.{organic_history_text}"
                )
            else:
                p3 = f"När slutsignalen ljöd stod det klart att tipsraderna ställdes helt på ända, vilket utlöste djupa diskussioner kring pubbordet."
                p4 = f"Bakslaget förändrar förutsättningarna radikalt inför nästa matchdag.{organic_history_text}"

            p5 = f"Det taktiska chanstagandet kring matchresultatet fick omedelbara konsekvenser i sammandraget, där marginalerna visade sig vara brutala."
            p6 = f"Reaktionerna bland övriga tippare lät inte vänta på sig när tabellens nya styrkeförhållanden nagelfors inför nästa drabbning."

        else: # HEAD_TO_HEAD_DUEL or GENERAL_STAGE
            p1 = f"Omgången bjöd på ett tätt och dramatiskt skede i mästerskapet. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, medan stämningen i gruppen var fylld av spänd förväntan."

            if r_nick and r_in_action:
                p3 = (
                    f"Vid sidan av toppstriden utmanade {r_nick} med full kraft. "
                    f"Under matchens mest intensiva skede {r_in_action}, vilket satte hård press på motståndarna."
                )
                p4 = (
                    f"Duellen mellan {p_nick} och {r_nick} visade upp en fascinerande taktisk kamp där varje poäng räknas. "
                    f"Spänningen mellan herrarna tätnade för varje minut fram till slutsignalen.{organic_history_text}"
                )
            else:
                p3 = f"Under matchernas gång {p_in_action}, vilket skapade livliga diskussioner kring de taktiska vägvalen."
                p4 = f"Utgången av omgången ger ett högintressant läge inför de kommande matcherna.{organic_history_text}"

            p5 = f"Det taktiska chanstagandet kring matchresultatet fick omedelbara konsekvenser i sammandraget, där varje poäng är avgörande."
            p6 = f"Reaktionerna bland övriga tippare lät inte vänta på sig när gänget analyserade de faktiska matchresultaten inför nästa omgång."

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
            'polarity': polarity,
            'historical_notes': ind_notes + riv_notes,
        }

