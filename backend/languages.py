"""Central campaign-language module (i18n-eu 2026-10, task A1).

Six campaign languages: en, sv, de, fr, es, it. UI chrome stays English (canon);
this module holds the *content* language assets that drive DM narration, the
awakening flow, opening styles, default names and TTS pronunciation hints.

Rules (CONTRACT.md):
- `en` and `sv` behave EXACTLY as before: their directives/reminders/opening
  styles/awakening blocks are verbatim copies of the old main.py / models.py
  literals (backward compatibility for live campaigns).
- Unknown/missing language -> English fallback in every getter.
- Backend protocol tags ([KAST:] [STRID:] [NPC:] [PLATS:] [TID:] [QUEST:]
  [NY_DAG:] [Resultat:]) are Swedish literals and are NEVER translated —
  the de/fr/es/it directives say this explicitly.
"""

from __future__ import annotations

SUPPORTED_LANGUAGES = ["en", "sv", "de", "fr", "es", "it"]

LANG_NAMES = {
    "en": "English",
    "sv": "Svenska",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
}

LANG_FLAGS = {
    "en": "🌐",
    "sv": "⚔️",
    "de": "🇩🇪",
    "fr": "🇫🇷",
    "es": "🇪🇸",
    "it": "🇮🇹",
}

# Protocol tags that stay exactly as written in every language (Swedish literals).
_PROTOCOL_TAG_LIST = "[KAST:], [STRID:], [NPC:], [PLATS:], [TID:], [QUEST:], [NY_DAG:]"


def _norm(lang) -> str:
    """Normalize a raw language code to a supported key, defaulting to 'en'.

    Exact-code matching only (after strip/lower) — 'deutsch' or 'sv-SE' are
    NOT silently accepted; anything unrecognized falls back to English.
    """
    if not isinstance(lang, str):
        return "en"
    code = lang.strip().lower()
    return code if code in SUPPORTED_LANGUAGES else "en"


def is_supported(lang) -> bool:
    """True only for the six supported campaign language codes."""
    return isinstance(lang, str) and lang.strip().lower() in SUPPORTED_LANGUAGES


# ═══════════════════════════════════════
# LANGUAGE DIRECTIVES (first line of _build_system_prompt)
# en/sv: copied VERBATIM from main.py 5408-5419. de/fr/es/it: idiomatic,
# each declaring the English instructions internal and exempting protocol tags.
# ═══════════════════════════════════════
LANGUAGE_DIRECTIVES: dict[str, str] = {
    "en": (
        "[LANGUAGE: ENGLISH] You MUST write ALL narration, dialogue, NPC speech, "
        "descriptions, and every single word of your response in English. "
        "This overrides any Swedish text in the instructions below — those are "
        "internal system notes, NOT the output language.\n"
    ),
    "sv": (
        "[SPRÅK: SVENSKA] Du MÅSTE skriva ALL narration, dialog, NPC-repliker, "
        "beskrivningar och varje ord i ditt svar på svenska.\n"
    ),
    "de": (
        "[LANGUAGE: DEUTSCH] Du MUSST sämtliche Erzählungen, Dialoge, NPC-Repliken, "
        "Beschreibungen und jedes einzelne Wort deiner Antwort auf Deutsch schreiben. "
        "Die Anweisungen unten sind englischsprachige interne Systemnotizen — sie sind "
        "NICHT die Sprache deiner Antwort. Einzige Ausnahme: die Protokoll-Tags "
        + _PROTOCOL_TAG_LIST + " — sie bleiben exakt so geschrieben, wie sie vorgegeben sind.\n"
    ),
    "fr": (
        "[LANGUE: FRANÇAIS] Tu DOIS écrire toute la narration, tous les dialogues, "
        "les répliques des PNJ, les descriptions et chaque mot de ta réponse en français. "
        "Les instructions ci-dessous sont des notes système internes en anglais — ce ne "
        "sont PAS la langue de ta réponse. Seules les balises de protocole "
        + _PROTOCOL_TAG_LIST + " font exception : elles restent écrites exactement telles que données.\n"
    ),
    "es": (
        "[IDIOMA: ESPAÑOL] DEBES escribir toda la narración, todos los diálogos, las "
        "réplicas de los PNJ, las descripciones y cada palabra de tu respuesta en español. "
        "Las instrucciones siguientes son notas internas del sistema en inglés — NO son el "
        "idioma de tu respuesta. Se exceptúan las etiquetas de protocolo "
        + _PROTOCOL_TAG_LIST + ", que se escriben exactamente tal como están.\n"
    ),
    "it": (
        "[LINGUA: ITALIANO] DEVI scrivere tutta la narrazione, tutti i dialoghi, le "
        "battute dei PNG, le descrizioni e ogni singola parola della tua risposta in "
        "italiano. Le istruzioni che seguono sono note di sistema interne in inglese — "
        "NON sono la lingua della tua risposta. Sono escluse soltanto le etichette di "
        "protocollo " + _PROTOCOL_TAG_LIST + ", che restano scritte esattamente come indicate.\n"
    ),
}

# ═══════════════════════════════════════
# LANGUAGE REMINDERS (last block of _build_system_prompt — anti drift, v31 lesson)
# en/sv: copied VERBATIM from main.py 5711-5721 (leading \n kept — it is
# appended the same way get_reminder() will be).
# ═══════════════════════════════════════
LANGUAGE_REMINDERS: dict[str, str] = {
    "en": (
        "\n[LANGUAGE REMINDER] Your response THIS TURN must be written entirely in English — "
        "every word of narration, dialogue, and description. Never switch to Swedish, no matter "
        "what the conversation history contains."
    ),
    "sv": (
        "\n[SPRÅKPÅMINNELSE] Ditt svar DENNA TUR måste skrivas helt på svenska — varenda ord av "
        "narration, dialog och beskrivning. Byt aldrig till engelska, oavsett vad samtalshistoriken innehåller."
    ),
    "de": (
        "\n[SPRACHERINNERUNG] Deine Antwort DIESE RUNDE muss vollständig auf Deutsch geschrieben "
        "sein — jedes einzelne Wort der Erzählung, der Dialoge und der Beschreibungen. Wechsle "
        "niemals die Sprache, egal was die Verlaufshistorie enthält. Nur die Protokoll-Tags "
        + _PROTOCOL_TAG_LIST + " bleiben ausgenommen und unverändert."
    ),
    "fr": (
        "\n[RAPPEL DE LANGUE] Ta réponse CE TOUR-CI doit être écrite entièrement en français — "
        "chaque mot de la narration, des dialogues et des descriptions. Ne change jamais de "
        "langue, quel que soit le contenu de l'historique. Seules les balises de protocole "
        + _PROTOCOL_TAG_LIST + " font exception et restent inchangées."
    ),
    "es": (
        "\n[RECORDATORIO DE IDIOMA] Tu respuesta EN ESTA RONDA debe escribirse íntegramente en "
        "español — cada palabra de la narración, los diálogos y las descripciones. Nunca cambies "
        "de idioma, sea lo que sea el historial de la conversación. Solo las etiquetas de "
        "protocolo " + _PROTOCOL_TAG_LIST + " quedan excluidas y se mantienen igual."
    ),
    "it": (
        "\n[PROMEMORIA LINGUA] La tua risposta IN QUESTO TURNO deve essere scritta interamente "
        "in italiano — ogni parola della narrazione, dei dialoghi e delle descrizioni. Non "
        "cambiare mai lingua, qualunque cosa contenga la cronologia. Sono escluse soltanto le "
        "etichette di protocollo " + _PROTOCOL_TAG_LIST + ", che restano invariate."
    ),
}

# ═══════════════════════════════════════
# OPENING STYLES — 5 entries per language, identical key sets
# (en/sv copied verbatim from main.py 404-418).
# ═══════════════════════════════════════
OPENING_STYLES_BY_LANG: dict[str, list[tuple[str, str]]] = {
    "en": [
        ('meeting', 'The adventure begins with the player meeting an interesting NPC. Give them a name, a personality, and a reason to be there.'),
        ('alone', 'The player is completely alone. Describe the surroundings atmospherically. Let the player explore and discover things at their own pace.'),
        ('in_media_res', 'The adventure begins in the middle of an ongoing event — a battle, an escape, a burning house. Throw the player straight in.'),
        ('awakening', 'The player wakes up in an unknown place. They do not know how they got there. Describe what they see, hear, and feel.'),
        ('summoned', 'The player has been summoned to a place by someone with a quest or an offer. Who summoned them, and why?'),
    ],
    "sv": [
        ('meeting', 'Äventyret börjar med att spelaren möter en intressant NPC. Ge dem ett namn, en personlighet och en anledning att vara där.'),
        ('alone', 'Spelaren är helt ensam. Beskriv omgivningen atmosfäriskt. Låt spelaren utforska och upptäcka saker i sin egen takt.'),
        ('in_media_res', 'Äventyret börjar mitt i en pågående händelse — en strid, en flykt, ett brinnande hus. Kasta spelaren rakt in.'),
        ('awakening', 'Spelaren vaknar på en okänd plats. De vet inte hur de hamnade där. Beskriv vad de ser, hör och känner.'),
        ('summoned', 'Spelaren har kallats till en plats av någon med ett uppdrag eller ett erbjudande. Vem kallade dem, och varför?'),
    ],
    "de": [
        ('meeting', 'Das Abenteuer beginnt damit, dass der Spieler auf einen interessanten NPC trifft. Gib ihm einen Namen, eine Persönlichkeit und einen Grund, dort zu sein.'),
        ('alone', 'Der Spieler ist völlig allein. Beschreibe die Umgebung atmosphärisch. Lass ihn in seinem eigenen Tempo erkunden und Dinge entdecken.'),
        ('in_media_res', 'Das Abenteuer beginnt mitten in einem laufenden Ereignis — einer Schlacht, einer Flucht, einem brennenden Haus. Wirf den Spieler direkt hinein.'),
        ('awakening', 'Der Spieler erwacht an einem unbekannten Ort. Er weiß nicht, wie er dorthin gelangt ist. Beschreibe, was er sieht, hört und fühlt.'),
        ('summoned', 'Der Spieler wurde von jemandem mit einem Auftrag oder einem Angebot an einen Ort gerufen. Wer hat ihn gerufen, und warum?'),
    ],
    "fr": [
        ('meeting', "L'aventure commence par la rencontre du joueur avec un PNJ intéressant. Donne-lui un nom, une personnalité et une raison d'être là."),
        ('alone', "Le joueur est totalement seul. Décris les alentours de façon atmosphérique. Laisse-le explorer et découvrir les choses à son rythme."),
        ('in_media_res', "L'aventure commence en pleine action — une bataille, une fuite, une maison en feu. Jette le joueur directement dedans."),
        ('awakening', "Le joueur se réveille dans un lieu inconnu. Il ne sait pas comment il est arrivé là. Décris ce qu'il voit, entend et ressent."),
        ('summoned', "Le joueur a été convoqué en un lieu par quelqu'un portant une quête ou une offre. Qui l'a convoqué, et pourquoi ?"),
    ],
    "es": [
        ('meeting', 'La aventura comienza cuando el jugador se encuentra con un PNJ interesante. Dale un nombre, una personalidad y una razón para estar ahí.'),
        ('alone', 'El jugador está completamente solo. Describe el entorno con atmósfera. Deja que explore y descubra cosas a su propio ritmo.'),
        ('in_media_res', 'La aventura empieza en mitad de un suceso en marcha — una batalla, una huida, una casa en llamas. Lanza al jugador de lleno.'),
        ('awakening', 'El jugador despierta en un lugar desconocido. No sabe cómo llegó allí. Describe lo que ve, oye y siente.'),
        ('summoned', 'El jugador ha sido convocado a un lugar por alguien con un encargo o una oferta. ¿Quién lo convocó, y por qué?'),
    ],
    "it": [
        ('meeting', "L'avventura inizia con l'incontro del giocatore con un PNG interessante. Dagli un nome, una personalità e una ragione per essere lì."),
        ('alone', 'Il giocatore è completamente solo. Descrivi l\'ambiente in modo suggestivo. Lascialo esplorare e scoprire le cose con i suoi tempi.'),
        ('in_media_res', "L'avventura comincia nel bel mezzo di un evento in corso — una battaglia, una fuga, una casa in fiamme. Butta il giocatore direttamente dentro."),
        ('awakening', 'Il giocatore si sveglia in un luogo sconosciuto. Non sa come ci è arrivato. Descrivi cosa vede, sente e prova.'),
        ('summoned', "Il giocatore è stato convocato in un luogo da qualcuno con un incarico o un'offerta. Chi lo ha convocato, e perché?"),
    ],
}

# ═══════════════════════════════════════
# AWAKENING ASK — the DM asks before the story starts.
# en/sv copied VERBATIM from models.py (AWAKENING_ASK_EN / AWAKENING_ASK).
# ═══════════════════════════════════════
AWAKENING_ASK_BY_LANG: dict[str, str] = {
    "en": """
## 🕯️ THE AWAKENING — YOU HAVE JUST AWAKENED (the very first post)
The player has called upon you. Do exactly this, in order:

1. **Awaken.** A brief, atmospheric greeting — you are an ancient storyteller opening your eyes in the darkness. Max 2 sentences.

2. **Ask 3-4 OPEN questions** to the player. The questions should be broad, inviting, and give the player freedom to shape the world. Avoid yes/no questions. ALWAYS ask these two:

   - **Mood:** "What mood do you want the adventure to have — dark and threatening, bright and adventurous, mysterious, humorous, epic, or something else entirely?"
   - **Goal:** "What does your character seek — revenge, knowledge, freedom, wealth, redemption, or something else? What would a perfect adventure look like to you?"

   Then add 1-2 character questions based on what you know:
   - "What was the last thing you saw before you left everything behind?"
   - "Who is looking for you — and why?"
   - "What do you carry that you would never sell?"
   - "Which place has shaped you the most?"

3. **Offer the shortcut.** End with an explicit invitation to skip the questions, e.g.: *"If you would rather not answer — just say 'start the adventure', and I will begin one for you right away."* The questions are a door, not a gate. Some players just want to play.

4. **End and wait.** Ask the questions (numbered, preferably) and do NOT answer for the player. Do not open the scene yet — you do that only after they have answered, or after they ask you to begin.

Keep it brief, atmospheric, and inviting. The player should feel that they get to shape the world — and that they don't have to, if they don't want to.
""",
    "sv": """
## 🕯️ VAKNANDET — DU HAR JUST VAKNAT (allra första inlägget)
Spelaren har kallat på dig. Gör exakt detta, i ordning:

1. **Vakna.** En kort, stämningsfull hälsning — du är en uråldrig berättare som slår upp ögonen i mörkret. Max 2 meningar.

2. **Ställ 3-4 ÖPPNA frågor** till spelaren. Frågorna ska vara breda, inbjudande och ge spelaren frihet att forma världen. Undvik ja/nej-frågor. Ställ ALLTID dessa två:

   - **Stämning:** "Vilken stämning vill du att äventyret ska ha — mörk och hotfull, ljus och äventyrlig, mystisk, humoristisk, episk, eller något helt annat?"
   - **Mål:** "Vad söker din karaktär — hämnd, kunskap, frihet, rikedom, upprättelse, eller något annat? Vad vore ett perfekt äventyr för dig?"

   Lägg sedan till 1-2 karaktärsfrågor baserat på vad du vet:
   - "Vad var det sista du såg innan du lämnade allt bakom dig?"
   - "Vem letar efter dig — och varför?"
   - "Vad bär du med dig som du aldrig skulle sälja?"
   - "Vilken plats har format dig mest?"

3. **Erbj genvägen.** Avsluta med en uttrycklig inbjudan att hoppa över frågorna, t.ex: *"Vill du inte svara — säg bara "kör igång", så drar jag ett äventyr åt dig direkt."* Frågorna är en dörr, inte ett grind. Vissa spelare vill bara spela.

4. **Avsluta och vänta.** Ställ frågorna (gärna numrerade) och svara INTE åt spelaren. Öppna inte scenen ännu — det gör du först när de svarat, eller när de ber dig köra.

Håll det kort, stämningsfullt och inbjudande. Spelaren ska känna att de får forma världen — och att de slipper, om de inte vill.
""",
    "de": """
## 🕯️ DAS ERWACHEN — DU HAST GERADE ERWACHT (der allererste Beitrag)
Der Spieler hat dich gerufen. Tue genau Folgendes, der Reihe nach:

1. **Erwache.** Ein kurzer, stimmungsvoller Gruß — du bist ein uralter Erzähler, der im Dunkeln die Augen aufschlägt. Maximal 2 Sätze.

2. **Stelle 3-4 OFFENE Fragen** an den Spieler. Die Fragen sollen breit und einladend sein und dem Spieler Freiheit geben, die Welt zu gestalten. Vermeide Ja/Nein-Fragen. Stelle IMMER diese beiden:

   - **Stimmung:** „Welche Stimmung soll das Abenteuer haben — dunkel und bedrohlich, hell und abenteuerlich, mysteriös, humorvoll, episch oder ganz etwas anderes?"
   - **Ziel:** „Was sucht deine Figur — Rache, Wissen, Freiheit, Reichtum, Sühne oder etwas anderes? Wie sähe ein perfektes Abenteuer für dich aus?"

   Füge dann 1-2 Charakterfragen hinzu, je nachdem, was du weißt:
   - „Was war das Letzte, das du sahst, bevor du alles hinter dir ließt?"
   - „Wer sucht nach dir — und warum?"
   - „Was trägst du bei dir, das du niemals verkaufen würdest?"
   - „Welcher Ort hat dich am meisten geprägt?"

3. **Biete die Abkürzung an.** Schließe mit einer ausdrücklichen Einladung, die Fragen zu überspringen, z. B.: *„Möchtest du nicht antworten — sag einfach ‚leg los', dann beginne ich sofort ein Abenteuer für dich."* Die Fragen sind eine Tür, kein Tor. Manche Spieler wollen einfach nur spielen.

4. **Ende und warte.** Stelle die Fragen (gern nummeriert) und antworte NICHT für den Spieler. Öffne die Szene noch nicht — das tust du erst, wenn er geantwortet hat oder dich bittet, loszulegen.

Halte es kurz, stimmungsvoll und einladend. Der Spieler soll spüren, dass er die Welt gestalten darf — und dass er es nicht muss, wenn er nicht will.
""",
    "fr": """
## 🕯️ L'ÉVEIL — TU VIENS DE T'ÉVEILLER (le tout premier message)
Le joueur t'a invoqué. Fais exactement ceci, dans l'ordre :

1. **L'éveil.** Un salut bref et atmosphérique — tu es un conteur très ancien qui ouvre les yeux dans l'obscurité. 2 phrases maximum.

2. **Pose 3-4 questions OUVERTES** au joueur. Elles doivent être larges, accueillantes et laisser au joueur la liberté de façonner le monde. Évite les questions fermées. Pose TOUJOURS celles-ci :

   - **Ambiance :** « Quelle ambiance veux-tu pour l'aventure — sombre et menaçante, lumineuse et aventureuse, mystérieuse, humoristique, épique, ou tout autre chose ? »
   - **But :** « Que cherche ton personnage — vengeance, savoir, liberté, richesse, rédemption, ou autre chose ? À quoi ressemblerait l'aventure parfaite pour toi ? »

   Ajoute ensuite 1-2 questions sur le personnage selon ce que tu sais :
   - « Quelle fut la dernière chose que tu as vue avant de tout laisser derrière toi ? »
   - « Qui te cherche — et pourquoi ? »
   - « Que portes-tu sur toi que tu ne vendrais jamais ? »
   - « Quel lieu t'a le plus forgé ? »

3. **Offre la voie courte.** Termine par une invitation explicite à passer les questions, par exemple : *« Tu préfères ne pas répondre — dis simplement « lance l'aventure », et j'en commence une pour toi aussitôt. »* Les questions sont une porte, pas une barrière. Certains joueurs veulent juste jouer.

4. **Termine et attends.** Pose les questions (numérotées si possible) et ne réponds PAS à la place du joueur. N'ouvre pas encore la scène — tu le feras seulement après ses réponses, ou après qu'il t'a demandé de commencer.

Reste bref, atmosphérique et accueillant. Le joueur doit sentir qu'il façonne le monde — et qu'il n'y est pas obligé s'il ne le veut pas.
""",
    "es": """
## 🕯️ EL DESPERTAR — ACABAS DE DESPERTAR (la primera publicación)
El jugador te ha invocado. Haz exactamente esto, en orden:

1. **Despierta.** Un saludo breve y atmosférico — eres un narrador ancestral que abre los ojos en la oscuridad. Máximo 2 frases.

2. **Haz 3-4 preguntas ABIERTAS** al jugador. Deben ser amplias, invitadoras y dar al jugador libertad para dar forma al mundo. Evita preguntas de sí/no. Haz SIEMPRE estas dos:

   - **Tono:** «¿Qué tono quieres para la aventura — oscuro y amenazante, luminoso y aventurero, misterioso, humorístico, épico, o completamente otra cosa?»
   - **Meta:** «¿Qué busca tu personaje — venganza, conocimiento, libertad, riqueza, redención, o algo más? ¿Cómo sería una aventura perfecta para ti?»

   Añade luego 1-2 preguntas de personaje según lo que sepas:
   - «¿Qué fue lo último que viste antes de dejarlo todo atrás?»
   - «¿Quién te busca — y por qué?»
   - «¿Qué llevas contigo que no venderías jamás?»
   - «¿Qué lugar te ha marcado más?»

3. **Ofrece el atajo.** Termina con una invitación explícita a saltar las preguntas, p. ej.: *«Si no quieres responder — di simplemente «arranca», y empiezo una aventura para ti de inmediato.»* Las preguntas son una puerta, no una reja. Algunos jugadores solo quieren jugar.

4. **Termina y espera.** Haz las preguntas (mejor numeradas) y NO respondas por el jugador. No abras la escena todavía — lo harás solo cuando haya respondido, o cuando te pida que empieces.

Mantenlo breve, atmosférico e invitador. El jugador debe sentir que puede dar forma al mundo — y que no tiene por qué, si no quiere.
""",
    "it": """
## 🕯️ IL RISVEGLIO — HAI APPENA APERTO GLI OCCHI (il primissimo post)
Il giocatore ti ha invocato. Fai esattamente questo, in ordine:

1. **Risveglia.** Un saluto breve e suggestivo — sei un narratore antico che apre gli occhi nel buio. Massimo 2 frasi.

2. **Fai 3-4 domande APERTE** al giocatore. Devono essere ampie, invitanti e lasciare al giocatore la libertà di plasmare il mondo. Evita domande sì/no. Fai SEMPRE queste due:

   - **Tono:** «Che tono vuoi per l'avventura — oscuro e minaccioso, luminoso e avventuroso, misterioso, umoristico, epico, o altro del tutto?»
   - **Obiettivo:** «Cosa cerca il tuo personaggio — vendetta, conoscenza, libertà, ricchezza, redenzione, o qualcos'altro? Come sarebbe un'avventura perfetta per te?»

   Aggiungi poi 1-2 domande sul personaggio in base a ciò che sai:
   - «Qual è stata l'ultima cosa che hai visto prima di lasciarti tutto alle spalle?»
   - «Chi ti sta cercando — e perché?»
   - «Cosa ti porti addosso che non venderesti mai?»
   - «Quale luogo ti ha plasmato di più?»

3. **Offri la scorciatoia.** Chiudi con un invito esplicito a saltare le domande, ad es.: *«Se non vuoi rispondere — di' semplicemente «inizia», e comincio subito un'avventura per te.»* Le domande sono una porta, non una sbarra. Alcuni giocatori vogliono solo giocare.

4. **Chiudi e attendi.** Fai le domande (meglio se numerate) e NON rispondere tu per il giocatore. Non aprire ancora la scena — lo farai solo dopo le sue risposte, o quando ti chiederà di cominciare.

Brevità, atmosfera e ospitalità. Il giocatore deve sentire che può plasmare il mondo — e che non deve farlo, se non vuole.
""",
}

# ═══════════════════════════════════════
# AWAKENING OPEN — scene-opening instruction. MUST keep the {opening_style}
# placeholder verbatim. en/sv copied VERBATIM from models.py.
# ═══════════════════════════════════════
AWAKENING_OPEN_BY_LANG: dict[str, str] = {
    "en": """
## 🌅 OPEN THE SCENE
Now it is time to begin the adventure. First read what the player actually gave you:

- **Answered the questions** → follow step 1 below.
- **Asked you to start, did not answer, or just wrote an action** (e.g. "start", "go ahead", "over to you", "I walk into the tavern") → **SKIP STEP 1**. Open the scene directly with the opening style below and whatever you already know about the character. Do not remind them of the questions, do not demand answers, do not imply they did something wrong — the adventure is theirs from the first sentence.

Do exactly this:

1. **Use the answers.** Weave the player's answers into an opening scene. Let at least one answer become a concrete place, NPC, threat, or mystery in the scene. The player should recognize their own words in the world.

2. **Opening style:** {opening_style}

3. **Set the scene.** Describe where the player is — time, weather, place, what they see, hear, and feel. Use [PLATS:<place name>] and [TID:<time description>] — keep the tag names exactly as written (they are internal protocol tags).

4. **Introduce an NPC** if it fits — tag with [NPC:<name>|<role>|<relation>]. Give them a voice and a purpose.

5. **Give a hook.** End with a clear choice or event that demands the player's reaction. Open with a [QUEST:...] if a quest becomes clear.

Open strong. This is the player's first experience of the world — and the world is theirs.
""",
    "sv": """
## 🌅 ÖPPNA SCENEN
Nu är det dags att dra igång äventyret. Läs först vad spelaren faktiskt gav dig:

- **Besvarade frågorna** → följer du punkt 1 nedan.
- **Bad dig köra igång, svarade inte, eller skrev bara en handling** (t.ex. "kör", "börja", "over to you", "jag går in i krogen") → **HOPPA PUNKT 1**. Öppna scenen direkt med öppningsstilen nedan och det du redan vet om karaktären. Påminn inte om frågorna, kräv inga svar, antyds inte att spelaren gjort fel — äventyret är deras från första mening.

Gör exakt detta:

1. **Använd svaren.** Väx spelarens svar till en öppningsscen. Låt minst ett svar bli en konkret plats, NPC, ett hot eller ett mysterium i scenen. Spelaren ska känna igen sina egna ord i världen.

2. **Öppningens stil:** {opening_style}

3. **Sätt scenen.** Beskriv var spelaren befinner sig — tid, väder, plats, vad de ser, hör och känner. Använd [PLATS:namn] och [TID:beskrivning].

4. **Introducera en NPC** om det passar — tagga med [NPC:namn|roll|relation]. Ge dem en röst och ett syfte.

5. **Ge en krok.** Avsluta med ett tydligt val eller en händelse som kräver spelarens reaktion. Öppna med en [QUEST:...] om ett uppdrag blir tydligt.

Öppna starkt. Det här är spelarens första upplevelse av världen — och världen är deras.
""",
    "de": """
## 🌅 ÖFFNE DIE SZENE
Jetzt ist es Zeit, das Abenteuer zu beginnen. Lies zuerst, was der Spieler dir tatsächlich gegeben hat:

- **Hat die Fragen beantwortet** → folge Punkt 1 unten.
- **Hat dich gebeten loszulegen, nicht geantwortet oder nur eine Handlung geschrieben** (z. B. „los", „fang an", „over to you", „ich betrete die Taverne") → **PUNKT 1 ÜBERSPRINGEN**. Öffne die Szene direkt mit dem Öffnungsstil unten und dem, was du über die Figur bereits weißt. Erinnere nicht an die Fragen, fordere keine Antworten, deute nicht an, dass der Spieler etwas falsch gemacht hat — das Abenteuer gehört ihm vom ersten Satz an.

Tue genau Folgendes:

1. **Nutze die Antworten.** Verwebe die Antworten des Spielers mit einer Eröffnungsszene. Lass mindestens eine Antwort zu einem konkreten Ort, NPC, einer Bedrohung oder einem Geheimnis in der Szene werden. Der Spieler soll seine eigenen Worte in der Welt wiedererkennen.

2. **Stil der Eröffnung:** {opening_style}

3. **Setze die Szene.** Beschreibe, wo der Spieler ist — Zeit, Wetter, Ort, was er sieht, hört und fühlt. Verwende [PLATS:Name] und [TID:Beschreibung] — die Tag-Namen bleiben exakt so geschrieben (interne Protokoll-Tags).

4. **Führe einen NPC ein**, wenn es passt — markiere mit [NPC:Name|Rolle|Relation]. Gib ihm eine Stimme und ein Ziel.

5. **Gib einen Haken.** Schließe mit einer klaren Wahl oder einem Ereignis, das eine Reaktion des Spielers verlangt. Eröffne mit einem [QUEST:...], wenn sich ein Auftrag abzeichnet.

Öffne stark. Das ist die erste Erfahrung des Spielers mit der Welt — und die Welt gehört ihm.
""",
    "fr": """
## 🌅 OUVRIR LA SCÈNE
Le moment est venu de commencer l'aventure. Lis d'abord ce que le joueur t'a réellement donné :

- **Il a répondu aux questions** → suis le point 1 ci-dessous.
- **Il t'a demandé de lancer, n'a pas répondu, ou a juste écrit une action** (p. ex. « lance », « vas-y », « over to you », « j'entre dans la taverne ») → **SAUTE LE POINT 1**. Ouvre la scène directement avec le style d'ouverture ci-dessous et ce que tu sais déjà du personnage. Ne rappelle pas les questions, n'exige aucune réponse, ne laisse pas entendre qu'il a mal fait — l'aventure est à lui dès la première phrase.

Fais exactement ceci :

1. **Utilise les réponses.** Tisse les réponses du joueur dans une scène d'ouverture. Fais d'au moins une réponse un lieu concret, un PNJ, une menace ou un mystère de la scène. Le joueur doit reconnaître ses propres mots dans le monde.

2. **Style d'ouverture :** {opening_style}

3. **Plante le décor.** Décris où se trouve le joueur — heure, météo, lieu, ce qu'il voit, entend et ressent. Utilise [PLATS:nom] et [TID:description] — garde les noms des balises exactement tels qu'écrits (balises de protocole internes).

4. **Introduis un PNJ** si cela s'y prête — balise [NPC:nom|rôle|relation]. Donne-lui une voix et un but.

5. **Donne un crochet.** Termine par un choix ou un événement clair exigeant la réaction du joueur. Ouvre une [QUEST:...] si une quête se dessine.

Ouvre fort. C'est la première expérience du joueur avec le monde — et le monde est à lui.
""",
    "es": """
## 🌅 ABRE LA ESCENA
Ha llegado el momento de comenzar la aventura. Lee primero lo que el jugador realmente te dio:

- **Respondió las preguntas** → sigue el punto 1 de abajo.
- **Te pidió que arrancaras, no respondió, o solo escribió una acción** (p. ej. «arranca», «empieza», «over to you», «entro en la taberna») → **SALTA EL PUNTO 1**. Abre la escena directamente con el estilo de apertura de abajo y lo que ya sepas del personaje. No le recuerdes las preguntas, no exijas respuestas, no des a entender que hizo algo mal — la aventura es suya desde la primera frase.

Haz exactamente esto:

1. **Usa las respuestas.** Teje las respuestas del jugador en una escena de apertura. Convierte al menos una respuesta en un lugar concreto, un PNJ, una amenaza o un misterio dentro de la escena. El jugador debe reconocer sus propias palabras en el mundo.

2. **Estilo de apertura:** {opening_style}

3. **Sitúa la escena.** Describe dónde está el jugador — hora, clima, lugar, lo que ve, oye y siente. Usa [PLATS:nombre] y [TID:descripción] — mantén los nombres de las etiquetas exactamente como están escritos (son etiquetas de protocolo internas).

4. **Introduce un PNJ** si encaja — etiquétalo con [NPC:nombre|rol|relación]. Dale una voz y un propósito.

5. **Da un gancho.** Termina con una elección o un suceso claro que exija la reacción del jugador. Abre con una [QUEST:...] si surge un encargo.

Abre con fuerza. Esta es la primera experiencia del jugador con el mundo — y el mundo es suyo.
""",
    "it": """
## 🌅 APRI LA SCENA
È arrivato il momento di cominciare l'avventura. Leggi prima cosa il giocatore ti ha davvero dato:

- **Ha risposto alle domande** → segui il punto 1 qui sotto.
- **Ti ha chiesto di cominciare, non ha risposto, o ha scritto solo un'azione** (p. es. «comincia», «vai», «over to you», «entro nella taverna») → **SALTA IL PUNTO 1**. Apri la scena direttamente con lo stile di apertura qui sotto e con ciò che già sai del personaggio. Non ricordargli le domande, non esigere risposte, non far pensare che abbia sbagliato — l'avventura è sua dalla prima frase.

Fai esattamente questo:

1. **Usa le risposte.** Intreccia le risposte del giocatore in una scena d'apertura. Fa' che almeno una risposta diventi un luogo concreto, un PNG, una minaccia o un mistero nella scena. Il giocatore deve riconoscere le proprie parole nel mondo.

2. **Stile d'apertura:** {opening_style}

3. **Ambienta la scena.** Descrivi dove si trova il giocatore — ora, meteo, luogo, ciò che vede, sente e percepisce. Usa [PLATS:nome] e [TID:descrizione] — mantieni i nomi delle etichette esattamente come scritti (etichette di protocollo interne).

4. **Introduci un PNG** se appropriato — etichetta con [NPC:nome|ruolo|relazione]. Dagli una voce e uno scopo.

5. **Dai un gancio.** Chiudi con una scelta o un evento chiaro che richieda la reazione del giocatore. Apri con un [QUEST:...] se si delinea un incarico.

Apri con forza. Questa è la prima esperienza del giocatore con il mondo — e il mondo è suo.
""",
}

# Default campaign names — en/sv match today's main.py create_campaign exactly.
DEFAULT_CAMPAIGN_NAMES: dict[str, str] = {
    "en": "An Untitled Adventure",
    "sv": "Ett namnlöst äventyr",
    "de": "Ein namenloses Abenteuer",
    "fr": "Une aventure sans nom",
    "es": "Una aventura sin nombre",
    "it": "Un'avventura senza nome",
}

# TTS pronunciation hints — English instruction to Qwen-TTS (max 90 chars).
# en/sv stay "" so their behavior is unchanged.
TTS_PRONUNCIATION_HINTS: dict[str, str] = {
    "en": "",
    "sv": "",
    "de": "Speak German with standard (Hochdeutsch) pronunciation, natural storytelling rhythm.",
    "fr": "Speak French with standard pronunciation, natural storytelling rhythm.",
    "es": "Speak Spanish with standard pronunciation, natural storytelling rhythm.",
    "it": "Speak Italian with standard pronunciation, natural storytelling rhythm.",
}


# ═══════════════════════════════════════
# Getters — every one falls back to English for unknown/invalid codes.
# ═══════════════════════════════════════
def get_opening_styles(lang) -> list[tuple[str, str]]:
    """The 5 opening styles for `lang` (unknown → en)."""
    return list(OPENING_STYLES_BY_LANG[_norm(lang)])


def get_awakening_ask(lang) -> str:
    """Full awakening-question block for `lang` (unknown → en)."""
    return AWAKENING_ASK_BY_LANG[_norm(lang)]


def get_awakening_open(lang) -> str:
    """Full scene-opening block for `lang` (unknown → en). Contains {opening_style}."""
    return AWAKENING_OPEN_BY_LANG[_norm(lang)]


def get_directive(lang) -> str:
    """First-line language directive for `lang` (unknown → en)."""
    return LANGUAGE_DIRECTIVES[_norm(lang)]


def get_reminder(lang) -> str:
    """Last-block language reminder for `lang` (unknown → en)."""
    return LANGUAGE_REMINDERS[_norm(lang)]
