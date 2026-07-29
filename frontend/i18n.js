/**
 * 🌍 i18n.js — Campaign-aware language module for Mörkrets Rike
 *
 * The campaign's language is chosen once at campaign creation (newgame.html)
 * and stored server-side in state.meta.language. Every page initialises this
 * module with that language; pre-campaign pages default to Swedish.
 *
 * Swedish is the original — when lang === 'sv' no translation is applied.
 * English is applied by walking the DOM and swapping Swedish strings from
 * the dictionary below. No data-i18n attributes are required in the HTML.
 *
 * API:
 *   I18N.init(lang)       — set the language ('sv' | 'en') and translate the page
 *   I18N.t(svString)      — translate a single string (returns input when lang is 'sv')
 *   I18N.applyAll()       — re-run the DOM translation pass
 *   I18N.getLang()        — current language code
 *   I18N.speak(text, lang)— Browser SpeechSynthesis TTS
 *   I18N.stopSpeaking()   — cancel any ongoing speech
 */
const I18N = (() => {
  let _lang = 'sv';
  let _initialized = false;

  // ═══════════════════════════════════════
  // TRANSLATION DICTIONARY: Swedish → English
  // Keys are the exact Swedish strings as they appear in the HTML/JS.
  // ═══════════════════════════════════════
  const T = {
    // ── Global / brand / navigation ──
    'Ett svenskt D&D-äventyr': 'A Swedish D&D Adventure',
    '🐉 Ett svenskt D&D-äventyr': '🐉 A Swedish D&D Adventure',
    'Stig in i mörkret': 'Enter the Darkness',
    'Stig in i mörkret…': 'Enter the darkness…',
    'Till vägskälet': 'Back to the Crossroads',
    '← Till vägskälet': '← Back to the Crossroads',
    'Till bordet': 'To the Table',
    '⚔ Till bordet': '⚔ To the Table',
    '⚔️ Till bordet': '⚔️ To the Table',
    'Lämna': 'Leave',
    '🚪 Lämna': '🚪 Leave',
    'Läser in': 'Loading',
    'Ljud av/på': 'Sound on/off',
    'Musik av/på': 'Music on/off',
    'Vägskälet': 'The Crossroads',
    '🚪 Vägskälet': '🚪 The Crossroads',
    'Karaktär': 'Character',
    '🧙 Karaktär': '🧙 Character',
    'Kartan': 'The Map',
    '🗺️ Kartan': '🗺️ The Map',
    'Loggbok': 'Logbook',
    '📜 Loggbok': '📜 Logbook',
    'Gestalter': 'Personages',
    '📖 Gestalter': '📖 Personages',
    'Valvet': 'The Vault',
    '🏰 Valvet': '🏰 The Vault',
    'Arkivet': 'The Archive',
    'Platser': 'Locations',
    'Uppdrag': 'Quests',
    '⚑ Uppdrag': '⚑ Quests',
    'Karaktärer': 'Characters',
    'Namn': 'Name',
    'Dag': 'Day',
    'Nivå': 'Level',
    'Session': 'Session',
    'Plats': 'Location',
    'Okänd': 'Unknown',
    'Okänd plats': 'Unknown location',
    '🗺 Okänd plats': '🗺 Unknown location',
    'Okänd hjälte': 'Unknown hero',
    'Namnlös': 'Nameless',
    'Namnlös kampanj': 'Unnamed campaign',
    'Namnlös äventyrare': 'Nameless adventurer',
    'Namnlöst uppdrag': 'Unnamed quest',
    'Äventyrare': 'Adventurer',
    'Föremål': 'Items',
    'Händelser': 'Events',
    'Löften': 'Promises',
    'Världen': 'The World',
    '🗺️ Världen': '🗺️ The World',
    'Relationer': 'Relationships',
    'Alla': 'All',
    'Rensa': 'Clear',
    'Stäng': 'Close',
    '✕ Stäng': '✕ Close',
    'Fråga': 'Ask',
    'Exportera': 'Export',
    'Radera': 'Delete',
    'Ta bort': 'Remove',
    'Öppna kartan': 'Open the map',
    'Öppna dossier': 'Open dossier',
    'Öppna karaktärsark': 'Open character sheet',
    'Tillbaka till porten': 'Back to the Gate',
    'Välkommen tillbaka, ': 'Welcome back, ',
    'snabb': 'fast',
    'lokal': 'local',

    // ── Page titles ──
    '⚔️ Ett svenskt D&D-äventyr — Stig in': '⚔️ A Swedish D&D Adventure — Enter',
    '⚔️ Ett svenskt D&D-äventyr — Vägskälet': '⚔️ A Swedish D&D Adventure — The Crossroads',
    '⚔️ Ett svenskt D&D-äventyr — Välj ditt öde': '⚔️ A Swedish D&D Adventure — Choose Your Fate',
    '⚔️ Ett svenskt D&D-äventyr — Vid bordet': '⚔️ A Swedish D&D Adventure — At the Table',
    '⚔️ Ett svenskt D&D-äventyr — Karaktärsark': '⚔️ A Swedish D&D Adventure — Character Sheet',
    '⚔️ Ett svenskt D&D-äventyr — Hur spelar man?': '⚔️ A Swedish D&D Adventure — How to Play?',
    '⚔️ Ett svenskt D&D-äventyr — Loggbok': '⚔️ A Swedish D&D Adventure — Logbook',
    '📚 Ett svenskt D&D-äventyr — Minnesarkivet': '📚 A Swedish D&D Adventure — The Memory Archive',

    // ── login.html ──
    'Vem vågar stiga in i mörkret?': 'Who dares enter the darkness?',
    'Lösenord': 'Password',
    'Ditt namn, modige…': 'Your name, brave one…',
    'Det hemliga ordet…': 'The secret word…',
    '⚔ Stig in i mörkret': '⚔ Enter the Darkness',
    '⏳ Porten prövar dig…': '⏳ The Gate is testing you…',
    '⚠ Porten förblir stängd. Fel namn eller lösenord.': '⚠ The Gate remains closed. Wrong name or password.',
    'Driven av Qwen · Kampanjer sparas lokalt · ': 'Powered by Qwen · Campaigns are saved locally · ',
    'Glömt lösenordet?': 'Forgot your password?',

    // ── adventure.html ──
    'Steg ett av fyra': 'Step one of four',
    'Varje äventyr börjar med ett val. Vilken väg tar du?': 'Every adventure begins with a choice. Which path will you take?',
    '⚔️ Ditt pågående äventyr': '⚔️ Your Ongoing Adventure',
    '⚔️ Fortsätt äventyret': '⚔️ Continue Adventure',
    '🕯️ Avsluta äventyret': '🕯️ End Adventure',
    'Endast ': 'Only ',
    'ett': 'one',
    ' äventyr kan pågå åt gången — nya vägar låses tills detta är avslutat.': ' adventure can run at a time — new paths are locked until this one ends.',
    'Förbered äventyr': 'Prepare Adventure',
    'Skriv worldbuilding-prompt eller ladda upp .md/.pdf/bilder. Qwen extraherar världen åt dig.': 'Write a worldbuilding prompt or upload .md/.pdf/images. Qwen extracts the world for you.',
    'Prompt + Import': 'Prompt + Import',
    'Importera äventyr': 'Import Adventure',
    'Har du redan en kampanj? Dra in filer — Qwen läser in karaktärer, NPCs, platser och lore.': 'Already have a campaign? Drag in files — Qwen reads characters, NPCs, locations and lore.',
    '.md · .pdf · Bilder': '.md · .pdf · Images',
    'Nytt äventyr': 'New Adventure',
    'Ingen prep. Dungeon Master freestylar ihop en öppningsscen och kastar dig in i mörkret.': 'No prep. The Dungeon Master freestyles an opening scene and throws you into the darkness.',
    'Freestyle · Direkt': 'Freestyle · Instant',
    '📜 Förbered din värld': '📜 Prepare Your World',
    'Dra in filer eller ': 'Drag files here or ',
    'Dra in filer eller <b>klicka för att bläddra</b>': 'Drag files here or <b>click to browse</b>',
    'klicka för att bläddra': 'click to browse',
    '.md · .pdf · .jpg · .png — Qwen extraherar worldbuilding, karaktärer, platser': '.md · .pdf · .jpg · .png — Qwen extracts worldbuilding, characters, locations',
    '.md · .pdf · .jpg · .png — karaktärsark, session-loggar, worldbuilding-dokument, kartor': '.md · .pdf · .jpg · .png — character sheets, session logs, worldbuilding documents, maps',
    '🔮 Qwen läser in din värld…': '🔮 Qwen is reading your world…',
    '🔮 Qwen extraherar karaktärer, NPCs, platser och lore…': '🔮 Qwen is extracting characters, NPCs, locations and lore…',
    'Lore-fragment': 'Lore fragments',
    '⚔️ Skapa karaktär & börja': '⚔️ Create Character & Begin',
    'Världen sparas och ': 'The world is saved and ',
    ' använder den som grund för äventyret': ' uses it as the foundation for the adventure',
    '🔮 Bygg världen': '🔮 Build the World',
    'Prompt + filer skickas till ': 'Prompt + files are sent to ',
    ' som strukturerar allt': ' which structures everything',
    '📥 Importera befintlig kampanj': '📥 Import Existing Campaign',
    'Dra in dina kampanjfiler eller ': 'Drag in your campaign files or ',
    'Dra in dina kampanjfiler eller <b>klicka för att bläddra</b>': 'Drag in your campaign files or <b>click to browse</b>',
    'Importerad data merge:as in i kampanjens ': 'Imported data is merged into the campaign\'s ',
    'Filer skickas till ': 'Files are sent to ',
    ' (text) och ': ' (text) and ',
    ' (bilder)': ' (images)',
    '🔮 Extrahera & importera': '🔮 Extract & Import',
    'Avsluta äventyret?': 'End the adventure?',
    '🔥 Avsluta för alltid': '🔥 End Forever',
    '⚔️ Fortsätt spela': '⚔️ Keep Playing',
    '🕯️ Äventyret är avslutat': '🕯️ The adventure has ended',
    'Kunde inte avsluta äventyret': 'Could not end the adventure',
    '🎲 Dungeon Master förbereder en öppningsscen…': '🎲 The Dungeon Master is preparing an opening scene…',
    '⚠ Skriv en beskrivning eller ladda upp filer först': '⚠ Write a description or upload files first',
    '🔮 Världen är strukturerad!': '🔮 The world is structured!',
    '⚠ Kunde inte bygga världen: ': '⚠ Could not build the world: ',
    'okänt fel': 'unknown error',
    '⚠ Ladda upp minst en fil att importera': '⚠ Upload at least one file to import',
    '📥 Kampanj extraherad!': '📥 Campaign extracted!',
    '⚠ Kunde inte importera: ': '⚠ Could not import: ',
    'Beskriv din värld…': 'Describe your world…',

    // ── newgame.html ──
    'Steg ett av tre': 'Step one of three',
    'Välj ditt öde': 'Choose Your Fate',
    'Välj en arketyp — eller skriv din egen legend. Dungeon Master väver din karaktär till liv.': 'Choose an archetype — or write your own legend. The Dungeon Master weaves your character to life.',
    'Valvet — återkalla en sparad hjälte': 'The Vault — recall a saved hero',
    'Arketyper': 'Archetypes',
    'Ödesväven': 'The Fateweave',
    'Tom pergament': 'Blank Parchment',
    '✦ Tom pergament': '✦ Blank Parchment',
    '— skriv fritt': '— write freely',
    'Arketyp: ': 'Archetype: ',
    '🔮 Frammana karaktär': '🔮 Summon Character',
    'Dungeon Master väver din ödesväv…': 'The Dungeon Master weaves your fate…',
    'Din hjälte': 'Your Hero',
    '🔄 Slå om ödet': '🔄 Reroll Fate',
    'Spara i valvet': 'Save to Vault',
    '🏰 Spara i valvet': '🏰 Save to Vault',
    'Vald': 'Chosen',
    '⚔️ Återkalla': '⚔️ Recall',
    'vald — prompt-mall laddad': 'selected — prompt template loaded',
    '✦ Tom pergament — skriv din egen legend': '✦ Blank parchment — write your own legend',
    '⚠ Skriv en beskrivning först': '⚠ Write a description first',
    '🔮 Karaktären är vävd!': '🔮 The character is woven!',
    '⚠ Kunde inte väva karaktären: ': '⚠ Could not weave the character: ',
    '⚠ Ingen karaktär att spara ännu': '⚠ No character to save yet',
    ' vilar nu i valvet!': ' now rests in the vault!',
    'Kunde inte spara till valvet': 'Could not save to the vault',
    ' har återkallats!': ' has been recalled!',
    'Kunde inte återkalla hjälten': 'Could not recall the hero',
    ' har raderats ur valvet.': ' has been deleted from the vault.',
    'Kunde inte radera hjälten': 'Could not delete the hero',
    'Vill du radera ': 'Do you want to delete ',
    ' ur valvet? Detta kan inte ångras.': ' from the vault? This cannot be undone.',
    'En ensam vandrare med okänt förflutet.': 'A lone wanderer with an unknown past.',
    'Denna karaktärs historia är ännu oskriven. Mörkret väntar på att forma den.': 'This character\'s story is yet unwritten. The darkness awaits to shape it.',
    'Kampanjspråk': 'Campaign Language',
    'Äventyret, DM och alla svar på svenska.': 'The adventure, the DM and all replies in Swedish.',

    // ── Archetype names (newgame.html) ──
    'Den Fallne Riddaren': 'The Fallen Knight',
    'Askhäxan': 'The Ash Witch',
    'Gravjägaren': 'The Grave Hunter',
    'Viskande Tjuven': 'The Whispering Thief',
    'Edsvurna Väktaren': 'The Oathsworn Warden',
    'Ormtungans Skald': 'The Serpent-Tongued Skald',
    'En vanärad paladin som söker upprättelse — eller hämnd — i mörkret.': 'A disgraced paladin seeking redemption — or revenge — in the darkness.',
    'Eldmärkt av en förhäxelse hon aldrig bad om. Lågorna lyder henne — nästan.': 'Branded by a curse she never asked for. The flames obey her — almost.',
    'Jagar det som vägrar stanna dött. Silver armborst, kallt hjärta.': 'Hunts what refuses to stay dead. Silver crossbow, cold heart.',
    'Hör de dödas hemligheter. Låser, fickor, gravar — allt öppnar sig.': 'Hears the secrets of the dead. Locks, pockets, graves — everything opens.',
    'Vaktar en glömd grav. Eden är allt som finns kvar av hens folk.': 'Guards a forgotten tomb. The oath is all that remains of their people.',
    'Sånger som böjer sinnen. Varje vers är ett gift — eller ett botemedel.': 'Songs that bend minds. Every verse is a poison — or a cure.',
    'Människa': 'Human',
    'Paladin': 'Paladin',
    'Närstrid': 'Melee',
    'Tiefling': 'Tiefling',
    'Häxa': 'Witch',
    'Magi': 'Magic',
    'Halvälva': 'Half-elf',
    'Dödjägare': 'Undead Hunter',
    'Halvling': 'Halfling',
    'Spion': 'Spy',
    'Dvärg': 'Dwarf',
    'Väktare': 'Warden',
    'Försvar': 'Defense',
    'Älv': 'Elf',
    'Förförare': 'Seducer',

    // ── chat.html: topbar & dropdowns ──
    'Kampanj: —': 'Campaign: —',
    'Kampanj: ': 'Campaign: ',
    '⚡ Moln-API': '⚡ Cloud API',
    '🏠 Lokalt (Ollama)': '🏠 Local (Ollama)',
    'Qwen 3.6 Flash (atmosfär)': 'Qwen 3.6 Flash (atmosphere)',
    'Qwen3 8B (lokal)': 'Qwen3 8B (local)',
    'DeepSeek R1 7B (lokal)': 'DeepSeek R1 7B (local)',
    'Step 3.7 Flash (snabb)': 'Step 3.7 Flash (fast)',
    '⚙️ Verktyg': '⚙️ Tools',
    'platser & resvägar': 'locations & travel routes',
    'dina anteckningar': 'your notes',
    'kända NPCs': 'known NPCs',
    'Kända NPCs': 'Known NPCs',
    'minnen & fakta': 'memories & facts',
    'inventarium & skatter': 'inventory & treasures',
    'Regel-orakel': 'Rule Oracle',
    '📜 Regel-orakel': '📜 Rule Oracle',
    'fråga om 5e-regler': 'ask about 5e rules',
    'Maskinrummet': 'The Engine Room',
    '🛠️ Maskinrummet': '🛠️ The Engine Room',
    'live debug-loggar': 'live debug logs',
    'Hur spelar man?': 'How to Play?',
    'kommandon & tips': 'commands & tips',
    'kampanj som zip': 'campaign as zip',

    // ── chat.html: sidebar ──
    'Sällskapet': 'The Party',
    'Klicka för att byta bild': 'Click to change image',
    'Din plånbok': 'Your purse',
    'Plånbok: ': 'Purse: ',
    'Plånbok: tom': 'Purse: empty',
    'platina': 'platinum',
    'guld': 'gold',
    'silver': 'silver',
    'koppar': 'copper',
    'Inga uppdrag ännu…': 'No quests yet…',
    'Ingen har dykt upp ännu…': 'No one has shown up yet…',
    'Slutfört': 'Completed',
    'Misslyckat': 'Failed',
    'Aktivt': 'Active',
    ' uppdrag': ' quest',

    // ── chat.html: input & DM status ──
    'Vad gör du? Skriv fritt — slå, smyg, tala, kasta en besvärjelse…': 'What do you do? Write freely — fight, sneak, talk, cast a spell…',
    'Vad gör ': 'What does ',
    '? Skriv fritt — slå, smyg, tala, kasta en besvärjelse…': ' do? Write freely — fight, sneak, talk, cast a spell…',
    '⚔ Utför': '⚔ Act',
    'skicka': 'send',
    'ny rad': 'new line',
    'Skriv ': 'Type ',
    ' för att slå en tärning': ' to roll a die',
    '🧙‍♂️ Väver berättelsen…': '🧙‍♂️ Weaving the tale…',
    '🕯️ Låter skuggorna tala…': '🕯️ Letting the shadows speak…',
    '🌫️ Målar dimman över dalen…': '🌫️ Painting the fog over the valley…',
    '📜 Bläddrar i ödets bok…': '📜 Leafing through the book of fate…',
    '🎭 Visar fram nästa scen…': '🎭 Conjuring the next scene…',
    '🕰️ Tittar bakåt i tiden…': '🕰️ Looking back through time…',
    '📖 Bläddrar i minnets hallar…': '📖 Browsing the halls of memory…',
    '🔮 Söker i gamla samtal…': '🔮 Searching old conversations…',
    '🗝️ Låser upp bortglömda minnen…': '🗝️ Unlocking forgotten memories…',
    '🌒 Gräver i det som varit…': '🌒 Digging through what once was…',
    '⚖️ Rådgör med reglerna…': '⚖️ Consulting the rules…',
    '📚 Slår upp i domarens bok…': '📚 Looking it up in the judge\'s book…',
    '🎲 Väger tärningarnas dom…': '🎲 Weighing the verdict of the dice…',
    '🎭 Lånar en annans röst…': '🎭 Borrowing another\'s voice…',
    '🗣️ Viskar genom en främling…': '🗣️ Whispering through a stranger…',
    '👁️ Ser genom andras ögon…': '👁️ Seeing through other eyes…',
    '🗺️ Ritar världen på nytt…': '🗺️ Redrawing the world…',
    '🏔️ Reser berg och dalar…': '🏔️ Raising mountains and valleys…',
    '🌑 Lyssnar till mörkret…': '🌑 Listening to the darkness…',
    '🕯️ ': '🕯️ ',
    'Dungeon Master vaknar…': 'Dungeon Master awakens…',
    ' Mörkret rör på sig.': ' The darkness stirs.',
    'DM:ns inre monolog': 'The DM\'s inner monologue',
    ' ord': ' words',
    'Spela upp ljud': 'Play audio',
    '⚠ Talsyntes stöds inte i denna webbläsare': '⚠ Speech synthesis is not supported in this browser',

    // ── chat.html: dice ceremony & rolls ──
    'Tärningen rullar…': 'The die is rolling…',
    '✦ KRITISKT!': '✦ CRITICAL!',
    '✦ PATETISKT!': '✦ PATHETIC!',
    'KRITISKT': 'CRITICAL',
    'PATETISKT': 'PATHETIC',
    'DM begär: ': 'DM requests: ',
    'Slå ': 'Roll ',
    '🎲 Rullar…': '🎲 Rolling…',
    'Slår ': 'Rolling ',
    'Resultat: ': 'Result: ',

    // ── chat.html: oracle ──
    'Fråga oraklet om D&D 5e-regler utan att avbryta spelet. Svaren påverkar inte berättelsen.': 'Ask the oracle about D&D 5e rules without interrupting the game. The answers do not affect the story.',
    'T.ex. Vad är DC för att klättra?': 'E.g. What is the DC to climb?',
    '⚠ Oraklet tiger: ': '⚠ The oracle is silent: ',

    // ── chat.html: engine room console ──
    ' rader': ' lines',
    '⬇ Auto': '⬇ Auto',
    '⏸ Manuell': '⏸ Manual',
    'Öppnar maskinrummet… loggar strömmar in live.': 'Opening the engine room… logs are streaming in live.',
    'Hämtar loggar…': 'Fetching logs…',
    'Konsolen rensad.': 'Console cleared.',

    // ── chat.html: /help overlay ──
    'MÖRKRETS RIKE — KOMMANDON': 'REALM OF DARKNESS — COMMANDS',
    '— Slå en tärning': '— Roll a die',
    '— Spara kampanjen (checkpoint)': '— Save the campaign (checkpoint)',
    '— Fäst en permanent sanning': '— Pin a permanent truth',
    '— Ta bort en fäst sanning': '— Remove a pinned truth',
    '— Lägg till en lore-post': '— Add a lore entry',
    '— Avsluta kapitel (sammanfattning)': '— End chapter (summary)',
    '— Visa alla fästa sanningar': '— Show all pinned truths',
    '— Visa denna hjälp': '— Show this help',
    'Alla kommandon körs direkt utan DM.': 'All commands run directly without the DM.',
    '⌨ Visar kommandohjälp…': '⌨ Showing command help…',
    '📌 Hämtar fästa sanningar…': '📌 Fetching pinned truths…',
    '📌 Inga fästa sanningar ännu. Använd ': '📌 No pinned truths yet. Use ',
    ' för att fästa en.': ' to pin one.',
    '📌 Fästa sanningar:': '📌 Pinned truths:',
    '⚠ Kunde inte hämta sanningar: ': '⚠ Could not fetch truths: ',
    '💾 Sparar kampanj': '💾 Saving campaign',
    '💾 Kapitel sparat: ': '💾 Chapter saved: ',
    '💾 Kampanj sparat!': '💾 Campaign saved!',
    ' (tur ': ' (turn ',
    '⚠ Kunde inte spara: ': '⚠ Could not save: ',
    '📌 Fäster sanning: ': '📌 Pinning truth: ',
    '📌 Fakta fäst: ': '📌 Fact pinned: ',
    '📌 Sanning fäst:': '📌 Truth pinned:',
    '⚠ Kunde inte fästa: ': '⚠ Could not pin: ',
    '📌 Tar bort sanning: ': '📌 Removing truth: ',
    '📌 Fakta borttagen: ': '📌 Fact removed: ',
    '📌 Sanning borttagen:': '📌 Truth removed:',
    '⚠ Kunde inte ta bort: ': '⚠ Could not remove: ',
    '📜 Lägger till lore…': '📜 Adding lore…',
    '📜 Lore tillagd': '📜 Lore added',
    'Lore tillagd': 'Lore added',
    '📜 Lore tillagd:': '📜 Lore added:',
    '⚠ Kunde inte lägga till lore: ': '⚠ Could not add lore: ',
    '📖 Avslutar kapitel: ': '📖 Ending chapter: ',
    '📖 Kapitel avslutat: ': '📖 Chapter ended: ',
    '📖 Kapitel ': '📖 Chapter ',
    '⚠ Kunde inte avsluta kapitel: ': '⚠ Could not end chapter: ',
    '⚠ Okänt kommando: ': '⚠ Unknown command: ',
    '⚠ Okänt kommando. Skriv ': '⚠ Unknown command. Type ',
    ' för att se alla kommandon.': ' to see all commands.',
    '⚡ Anslutningen avbröts — svaret hämtades från transkriptet.': '⚡ Connection lost — the reply was recovered from the transcript.',
    '⚠ DM:n kunde inte svara: ': '⚠ The DM could not reply: ',
    '. Försök igen.': '. Please try again.',
    '⚠ DM:n kunde inte ge utfallet: ': '⚠ The DM could not deliver the outcome: ',

    // ── chat.html: mechanical effects ──
    'Du tar ': 'You take ',
    ' skada!': ' damage!',
    '✨ Du helas ': '✨ You are healed ',
    ' HP!': ' HP!',
    ' XP!': ' XP!',
    'Otillräckligt saldo!': 'Insufficient funds!',
    '📦 Nytt föremål: ': '📦 New item: ',
    '⚑ Nytt uppdrag: ': '⚑ New quest: ',
    '✅ Uppdrag slutfört: ': '✅ Quest completed: ',
    '❌ Uppdrag misslyckat: ': '❌ Quest failed: ',
    ' Du känner nya krafter!': ' You feel new powers!',
    '🗑️ Föremål förlorat: ': '🗑️ Item lost: ',
    '🤝 Relation ändrad: ': '🤝 Relationship changed: ',
    'NY DAG': 'NEW DAY',
    '📍 Ny plats: ': '📍 New location: ',
    ' är död.': ' is dead.',
    '✦ atmosfär ✦': '✦ atmosphere ✦',
    '🔮 Dungeon Master byter röst: ': '🔮 The Dungeon Master changes voice: ',
    ' · körs lokalt': ' · runs locally',
    '📦 Bygger kampanj-export… (zip med transkript, karaktärsark, bilagor)': '📦 Building campaign export… (zip with transcript, character sheet, attachments)',
    'Bygger kampanj-export…': 'Building campaign export…',
    '⚠ Export ej tillgänglig i mock-läge': '⚠ Export not available in mock mode',
    'Export ej tillgänglig i mock-läge': 'Export not available in mock mode',
    '🖼 Bild uppdaterad': '🖼 Image updated',
    'Bild uppdaterad': 'Image updated',
    '⚠ Kunde inte ladda upp: ': '⚠ Could not upload: ',
    'Session utgången': 'Session expired',
    'Ingen aktiv kampanj': 'No active campaign',
    'Karaktären kunde inte vävas': 'The character could not be woven',
    'Kunde inte generera ljud': 'Could not generate audio',
    'Kunde inte spela upp ljud': 'Could not play audio',

    // ── character.html ──
    'Karaktärsark': 'Character Sheet',
    'Qwen-driven Dungeon Master': 'Qwen-powered Dungeon Master',
    'Läser in kampanjens tillstånd…': 'Loading the campaign state…',
    '⚔ Karaktär': '⚔ Character',
    '🎒 Utrustning': '🎒 Equipment',
    'Utrustning': 'Equipment',
    '🪙 Skattkammare': '🪙 Treasury',
    'Skattkammare': 'Treasury',
    '📜 Anteckningar': '📜 Notes',
    'Anteckningar': 'Notes',
    'Ladda upp porträtt — Qwen kan analysera det': 'Upload a portrait — Qwen can analyze it',
    '📷 För in bild': '📷 Add image',
    'För in bild': 'Add image',
    '❤ Hälsopoäng': '❤ Hit Points',
    'Hälsopoäng': 'Hit Points',
    '−5 Skada': '−5 Damage',
    'Skada': 'Damage',
    '+5 Hela': '+5 Heal',
    'Hela': 'Heal',
    '🔮 Besvärjelseplatser': '🔮 Spell Slots',
    'Klicka en runa för att spendera / återställa': 'Click a rune to spend / restore',
    'Inga besvärjelseplatser — karaktären kastar inte besvärjelser': 'No spell slots — the character does not cast spells',
    'Plats ': 'Slot ',
    '🔮 Besvärjelse kastad': '🔮 Spell cast',
    '✨ Plats återställd': '✨ Slot restored',
    '⭐ Erfarenhet': '⭐ Experience',
    'Erfarenhet': 'Experience',
    ' till nästa nivå': ' to next level',
    'Förmågor': 'Abilities',
    'Egenskaper': 'Traits',
    'Inga egenskaper noterade ännu…': 'No traits noted yet…',
    'Sparningskast': 'Saving Throws',
    'Inga sparade sparningskast ännu…': 'No saving throws saved yet…',
    'Packning & Vapen': 'Pack & Weapons',
    'Typ': 'Type',
    'Antal': 'Qty',
    'Vikt': 'Weight',
    'Vikt (lbs)': 'Weight (lbs)',
    'Status': 'Status',
    'Föremål: ': 'Items: ',
    'Total vikt: ': 'Total weight: ',
    '⚠ ÖVERBELASTAD': '⚠ OVERLOADED',
    'Nytt föremål, t.ex. Svärd av frost…': 'New item, e.g. Sword of frost…',
    'Vapen': 'Weapon',
    'Rustning': 'Armor',
    'Dryck': 'Potion',
    'Magisk': 'Magical',
    '✦ Magisk': '✦ Magical',
    'Verktyg': 'Tool',
    'Annat': 'Other',
    'Normal': 'Normal',
    'Sällsynt': 'Rare',
    'Sällsynthet': 'Rarity',
    '✦ Lägg till': '✦ Add',
    'Lägg till': 'Add',
    '⚔ Buren': '⚔ Equipped',
    'I väska': 'In bag',
    'Släng föremålet': 'Throw the item away',
    'Väskan är tom… än så länge.': 'The bag is empty… for now.',
    ' utrustad': ' equipped',
    ' nerpackad': ' packed away',
    ' slängd': ' thrown away',
    ' tillagd i packningen': ' added to the pack',
    'Mynt & Ädelstenar': 'Coins & Gems',
    'Platina': 'Platinum',
    'Guld': 'Gold',
    'Silver': 'Silver',
    'Koppar': 'Copper',
    'Hordens totala värde': 'Total value of the hoard',
    ' guldmynt & ': ' gold coins & ',
    ' silvermynt · ': ' silver coins · ',
    ' mynt · ': ' coins · ',
    'Kontobok': 'Ledger',
    'Inga transaktioner ännu — horden växer med äventyret.': 'No transactions yet — the hoard grows with the adventure.',
    'Fria anteckningar ': 'Free Notes ',
    '— skriv fritt om din karaktär, världen, dina mål…': '— write freely about your character, the world, your goals…',
    '💾 Spara anteckningar': '💾 Save Notes',
    '✓ Sparat': '✓ Saved',
    'Bilagor': 'Attachments',
    'Dra hit filer eller ': 'Drag files here or ',
    'Dra hit filer eller <b>klicka</b>': 'Drag files here or <b>click</b>',
    'klicka': 'click',
    'Inga bilagor ännu.': 'No attachments yet.',
    '🗑️ Bilaga borttagen': '🗑️ Attachment removed',
    'Kunde inte ta bort bilagan': 'Could not remove the attachment',
    ' — endast .pdf, .md och .txt tillåts': ' — only .pdf, .md and .txt are allowed',
    ' uppladdad': ' uploaded',
    '⚠ Kunde inte ladda upp ': '⚠ Could not upload ',
    '📷 Porträtt sparat — redo för Qwen-analys': '📷 Portrait saved — ready for Qwen analysis',
    ' är medvetslös!': ' is unconscious!',
    ' skada': ' damage',
    ' helad': ' healed',
    'HP uppdaterat (syncas vid nästa chat)': 'HP updated (synced on next chat)',
    'Ingen aktiv kampanj — skapa ett äventyr först': 'No active campaign — create an adventure first',
    'Karaktärsarket fylls på när spelledaren väckt världen till liv.': 'The character sheet fills in once the Dungeon Master has awakened the world.',
    '✦ Skapa äventyr': '✦ Create Adventure',
    'Skapa äventyr': 'Create Adventure',
    'Kampanjen kunde inte laddas — kontrollera anslutningen och försök igen.': 'The campaign could not be loaded — check the connection and try again.',

    // ── help.html ──
    '⚔ Hur spelar man?': '⚔ How to Play?',
    'Hur spelar man': 'How to Play',
    'En guide till äventyret — från första inloggning till sista tärningskastet.': 'A guide to the adventure — from first login to the last dice roll.',
    'DM vaknar': 'The DM awakens',
    ' — ställer 2-3 frågor om din karaktär och världen': ' — asks 2-3 questions about your character and the world',
    'Du svarar': 'You answer',
    ' — DM väver in dina svar i öppningsscenen': ' — the DM weaves your answers into the opening scene',
    'Du agerar': 'You act',
    ' — skriv fritt: slå, smyg, tala, utforska': ' — write freely: fight, sneak, talk, explore',
    'DM svarar': 'The DM replies',
    ' — beskriver konsekvenser, NPCs, nya val': ' — describes consequences, NPCs, new choices',
    'Tärningar': 'Dice',
    ' — DM begär kast vid osäkerhet, du slår': ' — the DM requests rolls when uncertain, you roll',
    'Upprepa': 'Repeat',
    ' — storyn byggs av dina val, inget är förskrivet': ' — the story is built by your choices, nothing is scripted',
    'Kom igång': 'Getting Started',
    'Logga in med ditt användarnamn och lösenord': 'Log in with your username and password',
    'Välj äventyrstyp: ': 'Choose adventure type: ',
    'Förbered': 'Prepare',
    ' (bygg värld), ': ' (build a world), ',
    'Importera': 'Import',
    ' (ladda upp filer), eller ': ' (upload files), or ',
    'Nytt': 'New',
    ' (freestyle)': ' (freestyle)',
    'Skapa din karaktär: välj arketyp eller skriv fritt, välj modell (DeepSeek V4 Flash / Qwen 3.8 Max)': 'Create your character: choose an archetype or write freely, choose a model (DeepSeek V4 Flash / Qwen 3.8 Max)',
    'Klicka "Frammana karaktär" — AI:n genererar ett fullt karaktärsark': 'Click "Summon Character" — the AI generates a full character sheet',
    'Klicka "Till bordet" — DM vaknar och ställer sina frågor': 'Click "To the Table" — the DM awakens and asks its questions',
    'Prata med NPCs': 'Talking to NPCs',
    'Skriv ': 'Type ',
    ' i chatten för att rikta dig direkt till en NPC.': ' in the chat to address an NPC directly.',
    'Exempel: ': 'Example: ',
    '"Vad gör du här?"': '"What are you doing here?"',
    'NPC:n svarar i sin egen röst. DM kan lägga sig i med narration.': 'The NPC answers in their own voice. The DM may interject with narration.',
    'Du får autocomplete när du skriver ': 'You get autocomplete as you type ',
    ' — alla kända NPCs listas.': ' — all known NPCs are listed.',
    'DM begär ett kast: ': 'The DM requests a roll: ',
    'En knapp dyker upp i chatten — klicka för att slå': 'A button appears in the chat — click to roll',
    'Tärningsbrickan längst ner är ': 'The dice tray at the bottom is ',
    'låst': 'locked',
    ' tills DM begär ett kast': ' until the DM requests a roll',
    'Du kan också skriva ': 'You can also type ',
    ' direkt i chatten': ' directly in the chat',
    'Naturlig 20 = KRITISKT! Naturlig 1 = PATETISKT!': 'Natural 20 = CRITICAL! Natural 1 = PATHETIC!',
    'Mekaniska taggar (osynliga)': 'Mechanical tags (invisible)',
    'DM använder taggar som systemet plockar bort och omvandlar till effekter:': 'The DM uses tags that the system strips and converts into effects:',
    ' — du tar 12 skada (HP minskar)': ' — you take 12 damage (HP decreases)',
    ' — du helas 8 HP': ' — you are healed 8 HP',
    ' — du får erfarenhetspoäng': ' — you gain experience points',
    ' — du hittar guld': ' — you find gold',
    ' — nytt föremål i inventariet': ' — new item in the inventory',
    ' — nytt uppdrag': ' — new quest',
    ' — ny NPC registreras': ' — a new NPC is registered',
    ' — platsen uppdateras': ' — the location is updated',
    'Modeller': 'Models',
    'Du kan byta AI-modell mitt i äventyret via dropdownen i topbaren.': 'You can switch AI model mid-adventure via the dropdown in the top bar.',
    ' — standard, snabb, reasoning-modell (tänker innan den svarar)': ' — standard, fast, reasoning model (thinks before answering)',
    ' — kraftfull, bra på kreativ narration': ' — powerful, great at creative narration',
    ' — snabb, används för atmosfär/ASCII-art': ' — fast, used for atmosphere/ASCII art',
    'Lokala modeller': 'Local models',
    ' — via Ollama (kräver lokal server)': ' — via Ollama (requires a local server)',
    'Valet sparas i webbläsaren och gäller tills du byter.': 'The choice is saved in the browser and applies until you change it.',
    'Musik & Ljud': 'Music & Sound',
    ' — musik av/på (stämningsbaserade loopar: natt, dag, strid, stad, vila, fängelsehåla)': ' — music on/off (mood-based loops: night, day, combat, city, rest, dungeon)',
    ' — ljudeffekter av/på (tärningar, mynt, strid, level-up)': ' — sound effects on/off (dice, coins, combat, level-up)',
    'Musiken byter stämning automatiskt baserat på DM:s text': 'The music changes mood automatically based on the DM\'s text',
    'Regler (D&D 5e, förenklat)': 'Rules (D&D 5e, simplified)',
    'Kast:': 'Rolls:',
    ' = lätt, ': ' = easy, ',
    ' = medel, ': ' = medium, ',
    ' = svårt': ' = hard',
    ' = death saves (1d20, 3 lyckade = stabil, 3 misslyckade = död)': ' = death saves (1d20, 3 successes = stable, 3 failures = dead)',
    ' = erfarenhetspoäng, level-up vid trösklar (300, 900, 2700...)': ' = experience points, level-up at thresholds (300, 900, 2700...)',
    'Strid:': 'Combat:',
    'initiative → turordning → attack → skada → upprepa': 'initiative → turn order → attack → damage → repeat',
    'Vila:': 'Rest:',
    ' kort vila (1h) = återställ HP, lång vila (8h) = full HP + spell slots': ' short rest (1h) = restore HP, long rest (8h) = full HP + spell slots',
    'DM:n är den slutgiltiga domaren. Reglerna är ett ramverk, inte ett fängelse.': 'The DM is the final judge. The rules are a framework, not a prison.',
    'Tips': 'Tips',
    'Skriv fritt — du kan göra vad som helst (försöka, inte alltid lyckas)': 'Write freely — you can do anything (attempt, not always succeed)',
    'Fråga Regel-oraklet (📜) om du är osäker på D&D-regler': 'Ask the Rule Oracle (📜) if you are unsure about D&D rules',
    'Utforska Kartan (🗺️) för att se platser och restider': 'Explore the Map (🗺️) to see locations and travel times',
    'Läs Loggboken (📜) för en sammanfattning av äventyret': 'Read the Logbook (📜) for a summary of the adventure',
    'Spara din karaktär i Valvet (🏰) för att återanvända den': 'Save your character in the Vault (🏰) to reuse it',
    'Exportera (📦) för att ladda ner hela kampanjen som ZIP': 'Export (📦) to download the whole campaign as a ZIP',
    'Driven av DeepSeek & Qwen · Kampanjer sparas lokalt · ': 'Powered by DeepSeek & Qwen · Campaigns are saved locally · ',

    // ── loggbok.html ──
    '📜 Loggbok — Äventyrsjournal': '📜 Logbook — Adventure Journal',
    'Kampanjloggbok': 'Campaign Logbook',
    'Krönikören sammanfattar ditt äventyr, dag för dag': 'The Chronicler summarizes your adventure, day by day',
    '✦ Uppdatera krönikan': '✦ Update the Chronicle',
    'Krönikören bläddrar i minnets hallar…': 'The Chronicler browses the halls of memory…',
    '✦ Äventyret hittills ✦': '✦ The Adventure So Far ✦',
    '✦ Uppdaterad: ': '✦ Updated: ',
    'Ingen loggbok ännu.': 'No logbook yet.',
    'Äventyret väntar på att skrivas…': 'The adventure awaits to be written…',
    '🪶 Skriver…': '🪶 Writing…',
    '✦ Krönikan uppdaterad': '✦ Chronicle updated',
    '⚠ Kunde inte uppdatera krönikan': '⚠ Could not update the chronicle',
    'Ingen kampanj': 'No campaign',

    // ── facts.html ──
    'Minnesarkivet · Faktaregister': 'The Memory Archive · Fact Registry',
    '📚 Arkivets hyllor': '📚 The Archive Shelves',
    'Vad världen vet om ditt äventyr': 'What the world knows about your adventure',
    'Sök i arkivet…': 'Search the archive…',
    'Arkivet laddas…': 'The archive is loading…',
    ' uppgifter i arkivet': ' entries in the archive',
    '📊 Arkivets omfattning': '📊 The Scope of the Archive',
    '✦ ersatt av nyare uppgift': '✦ superseded by a newer entry',
    ' ersatta uppgifter': ' superseded entries',
    '📚 Minnesarkivet': '📚 The Memory Archive',
    ' uppgifter · extraherade ur berättelsen av DM:n': ' entries · extracted from the story by the DM',
    'Tur ': 'Turn ',
    'Tillförlitlighet ': 'Reliability ',
    'Arkivet är tomt.': 'The archive is empty.',
    'Spela vidare så extraherar DM:n fakta ur berättelsen —': 'Keep playing and the DM will extract facts from the story —',
    'NPC:er, platser, löften och händelser hamnar här.': 'NPCs, locations, promises and events end up here.',
    'Inga uppgifter matchar ': 'No entries match ',
    'detta filter': 'this filter',
    'Minnesarkivet': 'The Memory Archive',
  };

  // ═══════════════════════════════════════
  // CORE API
  // ═══════════════════════════════════════

  function getLang() { return _lang; }

  /**
   * Set the active language and translate the current page.
   * Called by each page with the campaign's language ('sv' for
   * pre-campaign pages). Re-entrant: safe to call multiple times.
   */
  function init(lang) {
    _lang = (lang === 'en') ? 'en' : 'sv';
    _initialized = true;
    document.documentElement.lang = _lang;
    applyAll();
  }

  /** Translate a single Swedish string. Returns the input unchanged for 'sv'. */
  function t(svString) {
    if (_lang !== 'en' || typeof svString !== 'string') return svString;
    return T[svString] !== undefined ? T[svString] : svString;
  }

  /**
   * Walk the DOM and translate all user-visible Swedish strings:
   * text nodes, placeholders, titles, optgroup labels, alt & aria-label.
   * Skips script/style/code/pre and the debug panel.
   */
  function applyAll() {
    if (_lang !== 'en') return; // Swedish is the original — nothing to translate

    // 1) Text nodes
    const walker = document.createTreeWalker(
      document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const p = node.parentElement;
          if (!p) return NodeFilter.FILTER_REJECT;
          const tag = p.tagName;
          if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'CODE' || tag === 'PRE') return NodeFilter.FILTER_REJECT;
          if (p.closest('#debug-panel')) return NodeFilter.FILTER_REJECT;
          return node.textContent.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
      }
    );
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const n of nodes) _translateTextNode(n);

    // 2) Attributes: placeholders, tooltips, labels
    const ATTRS = ['placeholder', 'title', 'alt', 'aria-label', 'label'];
    for (const attr of ATTRS) {
      for (const el of document.querySelectorAll('[' + attr + ']')) {
        const val = el.getAttribute(attr);
        if (val && T[val]) el.setAttribute(attr, T[val]);
      }
    }

    // 3) document.title (including "— suffix" titles)
    if (T[document.title]) {
      document.title = T[document.title];
    } else {
      for (const [sv, en] of Object.entries(T)) {
        if (sv.length > 3 && document.title.includes(sv)) {
          document.title = document.title.replace(sv, en);
          break;
        }
      }
    }
  }

  /** Translate one text node — exact match first, then partial fragments. */
  function _translateTextNode(node) {
    const raw = node.textContent;
    const key = raw.trim();
    if (T[key]) {
      node.textContent = raw.replace(key, T[key]);
      return;
    }
    // Mixed nodes (e.g. "Endast <b>ett</b> äventyr kan pågå…") — swap fragments
    let out = raw;
    for (const [sv, en] of Object.entries(T)) {
      if (sv.length > 3 && out.includes(sv)) {
        out = out.split(sv).join(en);
      }
    }
    if (out !== raw) node.textContent = out;
  }

  // ═══════════════════════════════════════
  // TTS (Browser SpeechSynthesis)
  // ═══════════════════════════════════════

  /** Speak text aloud. lang defaults to the current campaign language. */
  function speak(text, lang) {
    if (!window.speechSynthesis) return false;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = (lang || _lang) === 'en' ? 'en-US' : 'sv-SE';
    utter.rate = 0.92;
    utter.pitch = 0.9;
    // Prefer a darker voice when available
    const voices = speechSynthesis.getVoices();
    const preferred = voices.find(v =>
      v.lang.startsWith(utter.lang.split('-')[0]) &&
      /male|daniel|james|david|george/i.test(v.name)
    );
    if (preferred) utter.voice = preferred;
    speechSynthesis.speak(utter);
    return true;
  }

  function stopSpeaking() {
    if (window.speechSynthesis) speechSynthesis.cancel();
  }

  // ═══════════════════════════════════════
  // AUTO-INIT — pages without an explicit I18N.init() call default to 'sv'
  // ═══════════════════════════════════════
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { if (!_initialized) init('sv'); });
  } else if (!_initialized) {
    init('sv');
  }

  return { T, init, t, applyAll, getLang, speak, stopSpeaking };
})();
