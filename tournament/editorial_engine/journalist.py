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

        p_name = primary_persona.get('full_name', 'Tipparen') if primary_persona else 'Tipparen'
        r_name = rival_persona.get('full_name', '') if rival_persona else ''
        p_nick = cls.get_nickname(primary_persona)
        r_nick = cls.get_nickname(rival_persona) if rival_persona else ''

        # Format Bold Names
        p_bold_nick = f"**{p_nick}**"
        r_bold_nick = f"**{r_nick}**" if r_nick else ""
        p_bold_full = f"**{p_name}** ({p_bold_nick})" if p_name != p_nick else p_bold_nick
        r_bold_full = f"**{r_name}** ({r_bold_nick})" if (r_name and r_name != r_nick) else r_bold_nick

        p_pre_match = cls.get_behavior_v2(primary_persona, "pre_match")
        p_in_action = cls.get_behavior_v2(primary_persona, "in_action")
        r_pre_match = cls.get_behavior_v2(rival_persona, "pre_match") if rival_persona else ""
        r_in_action = cls.get_behavior_v2(rival_persona, "in_action") if rival_persona else ""

        # Check Gemini LLM Availability for generative story
        from tournament.services.gemini_scout_service import GeminiScoutService
        if GeminiScoutService.is_available():
            try:
                llm_prompt = f"""
Du är en stjärnkrönikör för 'Dagliga Gazetten' i fotbollsturneringen för ett slutet kompisgäng (Toarps Herrklubb).
Skriv en underhållande, cynisk och engagerande sportsida på svenska baserad på följande fakta:

Typ av händelse: {h_type}
Layoutformat: {fmt}
Huvudhändelse: {p_desc}
Sekundär händelse: {s_desc}
Tredje händelse: {t_desc}

Primär spelare: {p_name} (Smeknamn: {p_nick})
Rival/Motspelare: {r_name} (Smeknamn: {r_nick})
Historik: {', '.join(ind_notes + riv_notes)}

STRIKTA REGLER:
1. Skriv på svenska med torr, skandinavisk sportjournalistisk humor och pub-jargong.
2. ALLA spelarnamn och smeknamn MÅSTE formateras med fetstil markdown, t.ex. **{p_nick}** eller **{p_name}**.
3. Om händelsen gäller ENGLAND: Kom ihåg gängets grundlag – ingen i gänget vill se England gå långt. Skadeglädje vid förlust, och hårt hån mot den som tog "smutsiga poäng" genom att tippa på England.
4. Om händelsen gäller STORMAKT/GAMLA MERITER: Håna slentrianmässigt och "profillöst" tipsande på historiska mästare.
5. Inga påhittade matchfakta – håll dig strikt till matchresultaten och poängen ovan.

Svara med ett giltigt JSON-objekt:
{{
  "headline": "Kort, slagkraftig tidningsrubrik med versaler",
  "tagline": "Tre punkter med sammanfattning separerade med punkt •",
  "top_story": "En komplett krönika i 4-6 stycken med blankrad mellan varje stycke.",
  "event2_text": "2-3 meningar med analys av sekundärhändelsen.",
  "event3_text": "2-3 meningar med analys av tredje händelsen."
}}
"""
                llm_result = GeminiScoutService.generate_json(llm_prompt)
                if llm_result and 'headline' in llm_result and 'top_story' in llm_result:
                    return {
                        'headline': llm_result['headline'],
                        'tagline': llm_result.get('tagline', f"Krönika • {p_bold_nick} i fokus • Omgångens analys"),
                        'top_story': llm_result['top_story'],
                        'event2_text': llm_result.get('event2_text', s_desc),
                        'event3_text': llm_result.get('event3_text', t_desc),
                        'primary_nick': p_nick,
                        'rival_nick': r_nick,
                        'polarity': h_type,
                        'historical_notes': ind_notes + riv_notes,
                    }
            except Exception as e:
                pass

        # ---------------------------------------------------------------------
        # Dynamic Swedish Generative Fallback for All 22 Archetypes
        # ---------------------------------------------------------------------
        fact_sentence = p_desc.strip()
        if not fact_sentence.endswith('.'):
            fact_sentence += '.'

        if h_type == 'ENGLAND_BANTER':
            if 'havererat' in fact_sentence.lower() or 'tappade' in fact_sentence.lower() or 'slutade' in fact_sentence.lower():
                headline_title = f"ENGLAND-KOMPLEXET: SKADEGLÄDJEN TOTAL KRING PUBBORDET!"
                tagline = f"Three Lions i diket • {p_bold_nick} njuter av haveriet • Krönika från omgången"
                p1 = f"Det är en av de mest orubbliga grundlagarna i gänget: ingen – absolut ingen – vill se England ta sig för långt i något mästerskap. Matchfakta: {fact_sentence}"
                p2 = f"Inför avspark {p_pre_match}, medan förhoppningarna om ett engelskt magplask var det enda som förenade sällskapet."
                p3 = f"När slutresultatet spikades utbröt ett ohämmat firande kring bordet. {p_bold_nick} konstaterade med ett svalt leende att 'fotbollen är räddad för den här gången'."
                p4 = f"De få som i smyg hoppats på engelsk framgång fick snabbt krypa till korset när kommentarerna i gruppchatten haglade utan nåd."
                p5 = f"Omgången visade återigen att mästerskapets bästa stunder ofta inte mäts i poäng, utan i ren och skär skadeglädje."
                p6 = f"Nu väntar nästa kapitel i turneringen där gänget samlat blickar framåt mot nya dramatiska drabbningar."
            else:
                headline_title = f"ENGLAND TAR SEGERN — MEN VAR DE SMUTSIGA POÄNGEN VÄRDA DET?"
                tagline = f"Engelsk vinst skakar bordet • {p_bold_nick} hånas för tipsraden • Omgångens analys"
                p1 = f"England lyckades kriga till sig ett resultat, men stämningen i ligan var allt annat än munter. Matchfakta: {fact_sentence}"
                p2 = f"Inför avspark {p_pre_match}, ovetande om den hårda kritik som väntade vid slutsignalen."
                p3 = f"Att plocka poäng på en engelsk seger betraktas i ligan närmast som ett etiskt haveri. {p_bold_nick} inkasserade visserligen siffrorna, men blickarna från kompisarna var iskalla."
                p4 = f"Frågan som ekade kring pubbordet var glasklar: Var de där 'smutsiga poängen' verkligen värda att sälja själen för?"
                p5 = f"Tabellen ger poängen, men hedern i gänget går inte att köpa tillbaka i första taget."
                p6 = f"Nu krävs det ett taktiskt genidrag i nästa omgång för att tvätta bort stämpeln inför fortsättningen."

        elif h_type == 'PAST_MERITS_SKEPTIC':
            headline_title = f"PROFILLÖST ATT LEVA PÅ GAMLA MERITER: STORMAKTEN SVEK IGEN!"
            tagline = f"Historiska meriter sågas • {p_bold_nick} kräver mer mod • Taktisk krönika"
            p1 = f"Den slentrianmässiga tron på att gamla meriter och historiska stormakter per automatik vinner matcher fick sig en rejäl örfil i omgången. Matchfakta: {fact_sentence}"
            p2 = f"Inför matcherna {p_pre_match}, medan snacket gick om vem som vågade gå emot etablissemanget."
            p3 = f"Att fegt luta sig mot historieböckerna betraktas i gänget som direkt profillöst tipsande. {p_bold_nick} konstaterade krasst att historiska titlar inte gör ett enda mål på planen."
            p4 = f"De som blint litade på stornationens gamla glans fick se kalkylerna krascha brutalt mot den bistra verkligheten."
            p5 = f"Mästerskapet har visat att mod, fingertoppskänsla och taktisk analys alltid trumfar trötta gamla sanningar."
            p6 = f"Läxan är tydlig inför nästa omgång: våga sticka ut hakan eller se tabelltoppen glida ur händerna."

        elif h_type == 'FAILED_BANKER':
            headline_title = f"KOLLEKTIV SPIKKRASCH: MASSORNAS FAVORIT FÖLL MED DUNDER OCH BRAK!"
            tagline = f"Storfavoriten föll tungt • {p_bold_nick} räknar förlusterna • Omgångens chock"
            p1 = f"Omgången bjöd på ett totalt haveri för ligans samlade expertis. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, övertygad om att kvällens bankare var kassaskåpssäker."
            p3 = f"Under matchens gång {p_in_action}, men när skrällen var ett faktum stod det klart att majoriteten av gängets kuponger hamnat i papperskorgen."
            p4 = f"{p_bold_nick} försökte med sedvanligt lugn kalkylera bort skadan, men poängtappet sved ordentligt i sammandraget."
            p5 = f"Det taktiska bakslaget förändrar förutsättningarna i toppen och öppnar dörren på vid gavel för utmanarna."
            p6 = f"Reaktionerna bland tipparna lät inte vänta på sig när omgångens bittra facit nagelfors inför nästa drabbning."

        elif h_type in ('THREE_FULLPOTTS', 'CORRECT_EXACT_SCORE'):
            headline_title = f"PRICKSKYTTEN SLÅR TILL: {p_bold_nick.upper()} BOMBAR IN FULLPOTTAR!"
            tagline = f"Kirurgisk precision • {p_bold_nick} i absolut toppform • Rekordjakt i ligan"
            p1 = f"Omgången bjöd på en uppvisning i absolut fingertoppskänsla som fick konkurrenterna att häpna. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, med ett självförtroende som lyste lång väg."
            p3 = f"Under matchernas gång {p_in_action}, och när slutsignalerna ljöd satt de exakta resultaten som en smäck."
            p4 = f"Den kirurgiska precisionen som {p_bold_full} visade upp belönades med maximal utdelning och skickade chockvågor genom ligan."
            p5 = f"Konkurrenterna kunde bara titta på med avund när poängskörden bärgades med kirurgisk elegans."
            p6 = f"Med det här rycket sätter {p_bold_nick} enorm press på övriga fältet inför kommande matcher."

        elif h_type == 'OUTLIER_VICTORY':
            headline_title = f"ENSAMVARGEN TRIUMFERAR: {p_bold_nick.upper()} CHOCKAR HELA LIGAN!"
            tagline = f"Soloseger mot strömmen • {p_bold_nick} mot alla odds • Taktiskt mästerdrag"
            p1 = f"När hela gänget gick åt vänster valde en ensam spelare att gå åt höger – och fick full pott. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, trots att oddsen och gruppens samlade tyckare talade emot kalkylen."
            p3 = f"Medan övriga tippare fick se sina rader grusas {p_in_action}, vilket gav en monumental seger i sammandraget."
            p4 = f"Att ensam spika ett sådant resultat är inget annat än ett taktiskt mästerstycke av {p_bold_full} som kommer att diskuteras länge."
            p5 = f"Triumfen ger inte bara dyrbara poäng utan framför allt en odiskutabel 'vad var det jag sa'-rättighet vid pubbordet."
            p6 = f"Nu är frågan om {p_bold_nick} kan behålla kylan när jakten intensifieras i nästa omgång."

        elif h_type == 'RIVALRY_DUEL':
            headline_title = f"TITELDERBYT KOKAR: {p_bold_nick.upper()} MOT {r_bold_nick.upper()} I ELEKTRISK DUELL!"
            tagline = f"Nervkittlande toppmöte • {p_bold_nick} vs {r_bold_nick} • Marginalerna avgör"
            p1 = f"Toppstriden i ligan har förvandlats till ett stenhårt tvåmansderby där ingen viker en tum. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, medan {r_bold_nick} laddade upp på sitt eget kompromisslösa vis."
            p3 = f"Under matchernas mest intensiva skede {p_in_action}, samtidigt som {r_bold_nick} pressade på för att stänga avståndet."
            p4 = f"Prestigekampen mellan {p_bold_full} och {r_bold_full} sätter färg på hela turneringen och skapar elektrisk stämning i gänget."
            p5 = f"Med endast en handfull poäng som skiljer herrarna åt är varje enskilt domslut och mål direkt avgörande för guldstriden."
            p6 = f"Alla blickar riktas nu mot nästa omgång där nästa kapitel i denna episka holmgång ska skrivas."

        elif h_type == 'IS_TOURNAMENT_LEADER':
            headline_title = f"MÄSTARTRONEN SKAKAR INTE: {p_bold_nick.upper()} RYCKER I TABELLTOPPEN!"
            tagline = f"Mäktig ledning • {p_bold_nick} kontrollerar fältet • Guldfavoritens grepp"
            p1 = f"Tabelltoppen har fått en suverän ledare som just nu dominerar mästerskapet med järnhand. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, med den pondus som bara en serieledare kan utstråla."
            p3 = f"Under omgångens alla matcher {p_in_action}, vilket gav full utdelning och ytterligare drygade ut avståndet nedåt."
            p4 = f"Med ett försprång i tabellen som växer för varje matchdag har {p_bold_full} satt sig i ett drömläge inför avgörandet."
            p5 = f"Bakom ledaren sprider sig paniken i det jagande kopplet som desperat letar efter luckor i ledarens rader."
            p6 = f"Kan någon hota {p_bold_nick} när turneringen går in i sitt absoluta slutskede?"

        elif h_type == 'BOTTOM_RANK':
            headline_title = f"TRÄSLEVS-KRIGET I BOTTEN: {p_bold_nick.upper()} KÄMPAR FÖR ATT UNDVIKA SKAMPÅLEN!"
            tagline = f"Dramatik i botten • {p_bold_nick} vägrar ge upp • Kampen om hedern"
            p1 = f"Längst ner i tabellen pågår en minst lika intensiv kamp som i toppen – kampen om att slippa förnedringen. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, i ett desperat försök att hitta en vändning i poängskörden."
            p3 = f"Trots hård motvind {p_in_action}, fast besluten att inte bli den som tvingas ta emot årets träslev vid bokslutet."
            p4 = f"För {p_bold_full} handlar varje match nu om ren självbevarelsedrift och heder gentemot de hånfulla kompisarna."
            p5 = f"Marginalerna i bottenstriden är brutala och ett enda felsteg kan cementera placeringen inför sista omgången."
            p6 = f"Räkna med total attack och desperata chansningar från {p_bold_nick} i nästa drabbning."

        elif h_type == 'LOW_BLOCK_GRIND':
            headline_title = f"BETONGFÖRSVARETS SEGER: CYNISK DEFENSIV KROSSADE MÅLOPTIMISTERNA!"
            tagline = f"0-0 kamp • {p_bold_nick} hyllar taktiken • Cynisk triumf"
            p1 = f"Det bjöds inte på någon champagnefotboll, men väl en taktisk triumf för de defensiva kalkylerna. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, medan måloptimisterna i gruppen hoppades på fest."
            p3 = f"När matchen låste sig totalt {p_in_action}, väl medveten om att stängda spjäll ger sköna poäng i tabellen."
            p4 = f"{p_bold_nick} kunde nöjt konstatera att cynism och disciplin återigen visade sig vara ett vinnande koncept."
            p5 = f"Omgången blev en hård påminnelse om att mästerskap ofta avgörs i det tysta slitets tecken snarare än i anfallsfrossa."
            p6 = f"Nu återstår att se om de defensiva murarna håller när matchtempot skruvas upp ytterligare."

        elif h_type == 'GOAL_FEST':
            headline_title = f"PROPAGANDAFOTBOLL & MÅLFEST: {p_bold_nick.upper()} I CENTRUM FÖR KAOSMATCHEN!"
            tagline = f"Målexplosion • Total offensiv • {p_bold_nick} analyserar dramatiken"
            p1 = f"Försvarsspelet kastades i papperskorgen när lagen bjöd på en fullständig målexplosion. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, ovetande om det sanslösa målkalas som väntade."
            p3 = f"Medan målen rullade in i parti och minut {p_in_action}, samtidigt som tipsraderna levde sitt eget vilda liv."
            p4 = f"Det totala kaoset på planen rörde om ordentligt i tabellen och gav {p_bold_full} välbehövliga poäng."
            p5 = f"Matchen kommer att gå till historien som en av mästerskapets mest underhållande och svårkontrollerade drabbningar."
            p6 = f"Publiken jublade, men tipparna lär behöva lugnande te inför nästa omgång."

        else: # DEFAULT / GENERAL_DRAMA / DELUSION_INDEX
            headline_title = f"{p_bold_nick.upper()} I FÖRARSÄTET NÄR OMGÅNGEN AVGJORDS!"
            tagline = f"Ledarryck • {p_bold_nick} i centrum • Analys av omgångens utfall"
            p1 = f"Omgången bjöd på ett tätt och fascinerande skede i mästerskapet som satte djupa spår i tabellen. Matchfakta: {fact_sentence}"
            p2 = f"Inför avspark {p_pre_match}, medan förväntningarna var uppskruvade till max i gruppchatten."
            p3 = f"Under matchernas gång {p_in_action}, vilket gav fin utdelning när poängen räknades samman och tabelläget befästes."
            p4 = f"För {p_bold_full} innebär utgången att greppet om toppstriden hårdnar inför fortsättningen."
            p5 = f"Det taktiska spelet kring tipsraderna fick omedelbara konsekvenser i sammandraget, där varje poäng väger bly."
            p6 = f"Reaktionerna bland övriga tippare lät inte vänta på sig när gänget analyserade de faktiska matchresultaten inför nästa drabbning."

        top_story = f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}\n\n{p5}\n\n{p6}"

        s_fact = s_desc.strip()
        if not s_fact.endswith('.'):
            s_fact += '.'
        event2_text = (
            f"Faktiskt Matchresultat & Analys: {s_fact} Händelsen skakade om hela toppstriden och utlöste en storm av reaktioner i ligan. "
            f"Flera tippare tvingades se sina förhandstips rasa samman när matchens slutskede bjöd på oväntad dramatik och poängtapp."
        )

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
            'polarity': h_type,
            'historical_notes': ind_notes + riv_notes,
        }

