/**
 * 🌍 i18n.js — Campaign-aware language module for The Lore Weaver's Cauldron
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
  let _lang = 'en'; // English-first: UI är engelska; svenska bara via DM-språk-toggle i karaktärsskapandet
  let _initialized = false;

  // Originals saved before translation, so switching back to 'sv' restores them.
  const _origText = new WeakMap();   // text node -> original Swedish text
  const _origAttr = new WeakMap();   // element -> { attr: originalValue }
  let _origTitle = null;

  // ═══════════════════════════════════════
  // TRANSLATION DICTIONARY: Swedish → English
  // Keys are the exact Swedish strings as they appear in the HTML/JS.
  // ═══════════════════════════════════════
  const T = {
    // ── Global / brand / navigation ──
    'The Lore Weaver\'s Cauldron': 'The Lore Weaver\'s Cauldron',
    '🐉 The Lore Weaver\'s Cauldron': 'The Lore Weaver\'s Cauldron',
    'Stig in i mörkret': 'What will the Cauldron Foretell?',
    'Stig in i mörkret…': 'What will the Cauldron Foretell?',
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
    'Tillbaka till porten': 'Back to the Cauldron',
    'Välkommen tillbaka, ': 'Welcome back, ',
    'snabb': 'fast',
    'lokal': 'local',

    // ── Page titles ──
    '⚔️ The Lore Weaver\'s Cauldron — Stig in': 'The Lore Weaver\'s Cauldron — Enter',
    '⚔️ The Lore Weaver\'s Cauldron — Vägskälet': 'The Lore Weaver\'s Cauldron — The Crossroads',
    '⚔️ The Lore Weaver\'s Cauldron — Välj ditt öde': 'The Lore Weaver\'s Cauldron — Choose Your Fate',
    '⚔️ The Lore Weaver\'s Cauldron — Vid bordet': 'The Lore Weaver\'s Cauldron — At the Table',
    '⚔️ The Lore Weaver\'s Cauldron — Karaktärsark': 'The Lore Weaver\'s Cauldron — Character Sheet',
    '⚔️ The Lore Weaver\'s Cauldron — Hur spelar man?': 'The Lore Weaver\'s Cauldron — How to Play?',
    '⚔️ The Lore Weaver\'s Cauldron — Loggbok': 'The Lore Weaver\'s Cauldron — Logbook',
    '📚 The Lore Weaver\'s Cauldron — Minnesarkivet': 'The Lore Weaver\'s Cauldron — The Memory Archive',
    // ── login.html ──
    'Vem vågar stiga in i mörkret?': 'Where legends are brewed.',
    'Lösenord': 'Password',
    'Ditt namn, modige…': 'Your name, brave one…',
    'Det hemliga ordet…': 'The secret word…',
    '⚔ Stig in i mörkret': '⚔ What will the Cauldron Foretell?',
    '⏳ Porten prövar dig…': '⏳ The Gate is testing you…',
    '⚠ Porten förblir stängd. Fel namn eller lösenord.': '⚠ The Gate remains closed. Wrong name or password.',
    'Driven av Qwen · Kampanjer sparas lokalt · ': 'Powered by Qwen, DeepSeek &amp; StepFun · Campaigns are saved locally · ',
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
    '🌐 Välj kampanjspråk först!': '🌐 Select a campaign language first!',
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
    'Sällskap': 'Party',
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
    'Inga journalanteckningar ännu…': 'No journal entries yet…',
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
    'FÖRDEL': 'ADVANTAGE',
    'NACKDEL': 'DISADVANTAGE',
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
    'THE LORE WEAVER\'S CAULDRON — COMMANDS': 'THE LORE WEAVER\'S CAULDRON — COMMANDS',
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
    'Hjälten': 'The hero',
    'Öppna': 'Open',
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
    'Arkivets hyllor': 'The Archive Shelves',
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
    // ── Native English UI (comprehensive) ──
    'Beskriv din värld…\n\nExempel:\n- En mörk dal där askan aldrig slutar falla\n- En stad byggd på ryggen av en död gud\n- Tre fraktioner som krigar om den sista vattenkällan\n- En förbannelse som sprider sig genom drömmar\n\nJu mer du ger, desto rikare blir världen. Men Dungeon Master fyller i luckorna — inget behöver vara komplett.': 'Describe your world…\n\nExamples:\n- A dark valley where ash never stops falling\n- A city built on the back of a dead god\n- Three factions warring over the last water source\n- A curse spreading through dreams\n\nThe more you give, the richer the world becomes. But the Dungeon Master fills in the gaps — nothing needs to be complete.',
    'Typsnitt: Pixel (klicka för att byta)': 'Font: Pixel (click to switch)',
    'Klicka för att byta bild': 'Click to change image',
    'Kampanj: The Lore Weaver\'s Cauldron': 'Campaign: The Lore Weaver\'s Cauldron',
    'Ingen har dykt upp ännu…': 'No one has appeared yet…',
    'Äventyraren': 'The Adventurer',
    'ÄVENTYRAREN': 'THE ADVENTURER',
    'DM begär:': 'DM requests:',
    'Slå': 'Roll',
    'Skriv istället': 'Type instead',
    'SLÅ ELLER SKRIV?': 'ROLL OR TYPE?',
    'Kastet avböjt — spelaren agerar fritt': 'Roll declined — the player acts freely',
    'Utför': 'Execute',
    'UTFÖR': 'EXECUTE',
    'Vad gör Äventyraren? Skriv fritt — slå, smyg, tala, kasta en besvärjelse…': 'What does the Adventurer do? Write freely — fight, sneak, talk, cast a spell…',
    'Spela upp ljud': 'Play audio',
    'FÖRDEL': 'ADVANTAGE',
    'NACKDEL': 'DISADVANTAGE',
    'Namnlös äventyrare': 'Nameless adventurer',
    'Inga besvärjelseplatser — karaktären kastar inte besvärjelser': 'No spell slots — this character does not cast spells',
    'TÅL': 'CON',
    'Inga egenskaper noterade ännu…': 'No traits recorded yet…',
    'Inga sparade sparningskast ännu…': 'No saving throws saved yet…',
    'Inga transaktioner ännu — horden växer med äventyret.': 'No transactions yet — the hoard grows with the adventure.',
    'Inga bilagor ännu.': 'No attachments yet.',
    '# Min karaktär\n\nSkriv fritt här — bakgrundshistoria, mål, relationer, teorier om': '# My Character\n\nWrite freely here — backstory, goals, relationships, theories about',
    // ── help.html ──
    'skriv fritt: slå, smyg, tala, utforska': 'write freely: fight, sneak, talk, explore',
    '[FÖREMÅL:Svärd|Vapen|rare]': '[ITEM:Sword|Weapon|rare]',
    '[QUEST:Rädda byn|Beskrivning|100 gp]': '[QUEST:Save the village|Description|100 gp]',
    'standard, snabb, reasoning-modell (tänker innan den svarar)': 'standard, fast, reasoning model (thinks before answering)',
    'snabb, används för atmosfär/ASCII-art': 'fast, used for atmosphere/ASCII art',
    'via Ollama (kräver lokal server)': 'via Ollama (requires local server)',
    'om du är osäker på D&D-regler': 'if you are unsure about D&D rules',
    'för att se platser och restider': 'to see locations and travel times',
    'Läs Loggboken (': 'Read the Logbook (',
    'för en sammanfattning av äventyret': 'for a summary of the adventure',
    'Spara din karaktär i Valvet (': 'Save your character in the Vault (',
    'för att återanvända den': 'to reuse it',
    'för att ladda ner hela kampanjen som ZIP': 'to download the entire campaign as a ZIP',
    'Skapa din karaktär: välj arketyp eller skriv fritt, välj modell': 'Create your character: choose an archetype or write freely, choose a model',
    'Välj äventyrstyp: Förbered (bygg värld), Importera (ladda upp filer), eller Nytt (freestyle)': 'Choose adventure type: Prepare (build world), Import (upload files), or New (freestyle)',
    'Utforska Kartan (': 'Explore the Map (',
    'Exportera (': 'Export (',
    'Lokala modeller': 'Local models',
    'Kast: 1d20 + modifierare vs DC (Difficulty Class)': 'Roll: 1d20 + modifier vs DC (Difficulty Class)',
    'Strid: initiative → turordning → attack → skada → upprepa': 'Combat: initiative → turn order → attack → damage → repeat',
    'Vila: kort vila (1h) = återställ HP, lång vila (8h) = full HP + spell slots': 'Rest: short rest (1h) = restore HP, long rest (8h) = full HP + spell slots',
    'Tillbaka till porten': 'Back to the gate',
    'Vad gör du här?': 'What are you doing here?',
    'Exempel: @Lyra Vane': 'Example: @Lyra Vane',
    '— skriv fritt: slå, smyg, tala, utforska': '— write freely: fight, sneak, talk, explore',
    '— standard, snabb, reasoning-modell (tänker innan den svarar)': '— standard, fast, reasoning model (thinks before answering)',
    '— snabb, används för atmosfär/ASCII-art': '— fast, used for atmosphere/ASCII art',
    '— via Ollama (kräver lokal server)': '— via Ollama (requires local server)',
    'Tillförlitlighet': 'Reliability',
    'Du har inte mött några gestalter ännu.': "You haven't met any characters yet.",
    'De väntar i mörkret…': 'They wait in the dark…',
    'Gestalter': 'Characters',
    'Minnets hall': 'Hall of Memory',
    '0 gestalter': '0 characters',
    'gestalter': 'characters',
    'Du har inte mött några gestalter ännu. De väntar i mörkret…': "You haven't met any characters yet. They wait in the dark…",
    // ── platser.html / valvet.html JS strings ──
    'En plats i mörkret.': 'A place in the darkness.',
    '🗺️ Platsen finns inte på kartan ännu': '🗺️ The place is not on the map yet',
    'Okänd plats': 'Unknown location',
    'okänd terräng': 'unknown terrain',
    'är nu din aktiva karaktär!': 'is now your active character!',
    'Kunde inte aktivera karaktären': 'Could not activate the character',
    'har lämnat valvet': 'has left the vault',
    'Namnlös': 'Nameless',
    'Okänd ras': 'Unknown race',
    'Okänd klass': 'Unknown class',
    '⚠ Kunde inte öppna valvet': '⚠ Could not open the vault',
    'Vill du verkligen radera': 'Do you really want to delete',
    'ur valvet? Detta kan inte ångras.': 'from the vault? This cannot be undone.',
    'Kunde inte radera': 'Could not delete',
    'Mörkrets Rike': 'The Lore Weaver\'s Cauldron',    // ── npcs.html filter labels ──
    'Alla': 'All',
    'Allierade': 'Allies',
    'Uppdrag': 'Quests',
    'Fiender': 'Enemies',
    'Fallna': 'Fallen',
    '⚑ Uppdrag': '⚑ Quest',
    ' av ': ' of ',
    'Minneskodex · Kända gestalter': 'Memory Codex · Known Characters',
    'Inga gestalter matchar…': 'No characters match…',
    'Inga hjältar vilar här ännu. Skapa en karaktär och spara den till valvet — så överlever den även när äventyret tar slut.': 'No heroes rest here yet. Create a character and save it to the vault — that way it survives even when the adventure ends.',
    'Kampanj:': 'Campaign:',
    'Tur': 'Turn',
    '# Min karaktär\n\nSkriv fritt här — bakgrundshistoria, mål, relationer, teorier om världen…\n\nMarkdown stöds inte i renderingen, men strukturen är din.': '# My Character\n\nWrite freely here — backstory, goals, relationships, theories about the world…\n\nMarkdown is not supported in rendering, but the structure is yours.',
    'Ingen aktiv kampanj — skapa ett äventyr först': 'No active campaign — create an adventure first',
    'Karaktärsarket fylls på när spelledaren väckt världen till liv.': 'The character sheet fills in once the Dungeon Master has brought the world to life.',
    '✦ Skapa äventyr': '✦ Create Adventure',
    'Kampanjen kunde inte laddas — kontrollera anslutningen och försök igen.': 'The campaign could not be loaded — check your connection and try again.',
    'The Lore Weaver\'s Cauldron': 'The Lore Weaver\'s Cauldron',
    '🐉 The Lore Weaver\'s Cauldron': 'The Lore Weaver\'s Cauldron',
    '⚔️ The Lore Weaver\'s Cauldron — Vägskälet': 'The Lore Weaver\'s Cauldron — The Crossroads',
    '⚔️ The Lore Weaver\'s Cauldron — Vid bordet': 'The Lore Weaver\'s Cauldron — At the Table',
    '⚔️ The Lore Weaver\'s Cauldron — Karaktärsark': 'The Lore Weaver\'s Cauldron — Character Sheet',
    '⚔️ The Lore Weaver\'s Cauldron — Välj ditt öde': 'The Lore Weaver\'s Cauldron — Choose Your Fate',
    '⚔️ The Lore Weaver\'s Cauldron — Loggbok': 'The Lore Weaver\'s Cauldron — Logbook',
    '📚 The Lore Weaver\'s Cauldron — Minnesarkivet': 'The Lore Weaver\'s Cauldron — The Memory Archive',
    '⚔️ The Lore Weaver\'s Cauldron — Gestalter': 'The Lore Weaver\'s Cauldron — Characters',
    '⚔️ The Lore Weaver\'s Cauldron — Kartan': 'The Lore Weaver\'s Cauldron — The Map',
    '🏰 The Lore Weaver\'s Cauldron — Valvet': 'The Lore Weaver\'s Cauldron — The Vault',
    'Vem vågar stiga in i mörkret?': 'Who dares to step into the dark?',
    'Äventyrare': 'Adventurer',
    'Lösenord': 'Password',
    'Glömt lösenordet?': 'Forgotten your password?',
    '⚔ Stig in i mörkret': '⚔ What will the Cauldron Foretell?',
    'ÄVENTYRARE': 'ADVENTURER',
    'LÖSENORD': 'PASSWORD',
    'STIG IN I MÖRKRET': 'WHAT WILL THE CAULDRON FORETELL?',
    'Vägskälet': 'The Crossroads',
    'Steg ett av fyra': 'Step one of four',
    'Varje äventyr börjar med ett val. Vilken väg tar du?': 'Every adventure begins with a choice. Which road will you take?',
    'Ditt pågående äventyr': 'Your ongoing adventure',
    'Fortsätt äventyret': 'Continue the adventure',
    'Avsluta äventyret': 'End the adventure',
    'Skapa karaktär & börja': 'Create character & begin',
    'Bygg världen': 'Build the world',
    'Prepare din värld': 'Prepare your world',
    'Qwen läser in din värld…': 'Qwen is reading your world…',
    'Qwen extraherar karaktärer, NPCs, platser och lore…': 'Qwen is extracting characters, NPCs, locations and lore…',
    'Beskriv din värld…': 'Describe your world…',
    'Världen sparas och': 'The world is saved and',
    'använder den som grund för äventyret': 'uses it as the foundation for the adventure',
    'Världen sparas och <b>Qwen</b> använder den som grund för äventyret': 'The world is saved and <b>Qwen</b> uses it as the foundation for the adventure',
    'Endast <b>ett</b> äventyr kan pågå åt gången — nya vägar låses tills detta är avslutat.': 'Only <b>one</b> adventure can run at a time — new roads stay locked until this one ends.',
    'Freestyle · Direkt': 'Freestyle · Instant',
    'Karaktärer': 'Characters',
    'Dra in dina kampanjfiler eller <b>klicka för att bläddra</b>': 'Drag in your campaign files or <b>click to browse</b>',
    'Dra in filer eller <b>klicka för att bläddra</b>': 'Drag in files or <b>click to browse</b>',
    'Okänd hjälte': 'Unknown hero',
    'Importera äventyr': 'Import adventure',
    'Nytt äventyr': 'New adventure',
    'Förbered äventyr': 'Prepare adventure',
    'Välj ditt öde': 'Choose Your Fate',
    'Steg ett av tre': 'Step one of three',
    'Välj en arketyp — eller skriv din egen legend. Dungeon Master väver din karaktär till liv.': 'Choose an archetype — or write your own legend. The Dungeon Master weaves your character to life.',
    'Kampanjspråk': 'Campaign language',
    'Ödesväven': 'The Loom of Fate',
    'Din hjälte': 'Your hero',
    'Dungeon Master väver din ödesväv…': 'The Dungeon Master weaves your fate…',
    'Frammana karaktär': 'Summon character',
    '🔮 Frammana karaktär': '🔮 Summon Character',
    'Slå om ödet': 'Reroll fate',
    '🔄 Slå om ödet': '🔄 Reroll Fate',
    'Återkalla': 'Recall',
    '⚔️ Återkalla': '⚔️ Recall',
    'Valvet — återkalla en sparad hjälte': 'The Vault — recall a saved hero',
    'TOM PERGAMENT': 'BLANK SCROLL',
    '✦ TOM PERGAMENT': '✦ BLANK SCROLL',
    'FRAMMANA KARAKTÄR': 'SUMMON CHARACTER',
    'Kort svärd': 'Short sword',
    'Kortsvärd': 'Shortsword',
    'Långsvärd': 'Longsword',
    'Sköld': 'Shield',
    'Sköld (med runor)': 'Shield (runed)',
    'Vid bordet': 'At the Table',
    'THE LORE WEAVER\'S CAULDRON — COMMANDS': 'THE LORE WEAVER\'S CAULDRON — COMMANDS',
    'Sällskapet': 'The Party',
    'Kända NPCs': 'Known NPCs',
    'Inga uppdrag ännu…': 'No quests yet…',
    'Fråga': 'Ask',
    'fråga om 5e-regler': 'ask about 5e rules',
    'kända NPCs': 'known NPCs',
    'platser & resvägar': 'locations & routes',
    'Alla kommandon körs direkt utan DM.': 'All commands run directly, no DM involved.',
    'Öppnar maskinrummet… loggar strömmar in live.': 'Opening the engine room… logs streaming in live.',
    'skicka': 'send',
    'ny rad': 'new line',
    'Fästa sanningar:': 'Pinned truths:',
    'Hämtar fästa sanningar…': 'Fetching pinned truths…',
    'Lägger till lore…': 'Adding lore…',
    'Sanning fäst:': 'Truth pinned:',
    'Visar kommandohjälp…': 'Showing command help…',
    'Okänt kommando. Skriv': 'Unknown command. Type',
    'okänt fel': 'unknown error',
    'Du känner nya krafter!': 'You feel new powers surging!',
    '✦ Nya krafter väcks ✦': '✦ New powers awaken ✦',
    '🎲 DM begär:': '🎲 DM requests:',
    '📦 Nytt föremål:': '📦 New item:',
    '🗑️ Föremål förlorat:': '🗑️ Item lost:',
    '🤝 Relation ändrad:': '🤝 Relationship changed:',
    '✅ Uppdrag slutfört:': '✅ Quest complete:',
    'är död.': 'has died.',
    'för att slå en tärning': 'to roll a die',
    '— Fäst en permanent sanning': '— Pin a permanent truth',
    '— Lägg till en lore-post': '— Add a lore entry',
    '— Slå en tärning': '— Roll a die',
    '— Ta bort en fäst sanning': '— Remove a pinned truth',
    '— Visa alla fästa sanningar': '— Show all pinned truths',
    'Väver berättelsen…': 'Weaving the tale…',
    'Okänd plats': 'Unknown location',
    'Karaktärsark': 'Character Sheet',
    'Karaktär': 'Character',
    '⚔ Karaktär': '⚔ Character',
    'Hälsopoäng': 'Hit Points',
    '❤ Hälsopoäng': '❤ Hit Points',
    'Erfarenhet': 'Experience',
    '⭐ Erfarenhet': '⭐ Experience',
    'Utrustning': 'Equipment',
    '🎒 Utrustning': '🎒 Equipment',
    'Förmågor': 'Abilities',
    'Besvärjelseplatser': 'Spell Slots',
    '🔮 Besvärjelseplatser': '🔮 Spell Slots',
    'Skattkammare': 'Treasury',
    '🪙 Skattkammare': '🪙 Treasury',
    'Anteckningar': 'Notes',
    '📜 Anteckningar': '📜 Notes',
    'Spara anteckningar': 'Save notes',
    '💾 Spara anteckningar': '💾 Save Notes',
    'Spara i valvet': 'Save to the vault',
    '🏰 Spara i valvet': '🏰 Save to the Vault',
    'Valvet': 'The Vault',
    '🏰 Valvet': '🏰 The Vault',
    'Till bordet': 'To the Table',
    '⚔ Till bordet': '⚔ To the Table',
    'Lägg till': 'Add',
    '✦ Lägg till': '✦ Add',
    'Magisk': 'Magical',
    '✦ Magisk': '✦ Magical',
    'Föremål:': 'Items:',
    'Föremål': 'Item',
    'Mynt & Ädelstenar': 'Coins & Gems',
    'Hordens totala värde': 'Total hoard value',
    'Klicka en runa för att spendera / återställa': 'Click a rune to spend / restore',
    'Väskan är tom… än så länge.': 'The bag is empty… for now.',
    'Sällsynt': 'Rare',
    '— skriv fritt om din karaktär, världen, dina mål…': '— write freely about your character, the world, your goals…',
    'Min karaktär': 'My character',
    'Hela': 'Heal',
    'Skada': 'Damage',
    'Thalindra Mörkeld': 'Thalindra Darkflame',
    'Halvälva · Eldbesvärjare · Nivå 7': 'Half-Elf · Fire Mage · Level 7',
    'Gestalter': 'Characters',
    '📖 Gestalter': '📖 Characters',
    'Kartan': 'The Map',
    '🗺️ Kartan': '🗺️ The Map',
    'Loggbok': 'Logbook',
    '📜 Loggbok': '📜 Logbook',
    'För in bild': 'Import image',
    '📷 För in bild': '📷 Import Image',
    'Hur spelar man?': 'How to Play',
    '⚔ Hur spelar man?': '⚔ How to Play',
    'En guide till äventyret — från första inloggning till sista tärningskastet.': 'A guide to the adventure — from first login to the final dice roll.',
    'Regler (D&amp;D 5e, förenklat)': 'Rules (D&amp;D 5e, simplified)',
    'Välj äventyrstyp:': 'Choose adventure type:',
    'DM begär ett kast:': 'The DM calls for a roll:',
    'Du får autocomplete när du skriver': 'You get autocomplete as you type',
    'Du kan också skriva': 'You can also type',
    'i chatten för att rikta dig direkt till en NPC.': 'in chat to address an NPC directly.',
    'alla kända NPCs listas.': 'all known NPCs are listed.',
    'du får erfarenhetspoäng': 'you gain experience points',
    'nytt föremål i inventariet': 'new item in your inventory',
    'skriv fritt: slå, smyg, tala, utforska': 'write freely: fight, sneak, talk, explore',
    'snabb, används för atmosfär/ASCII-art': 'fast, used for atmosphere/ASCII art',
    'kraftfull, bra på kreativ narration': 'powerful, great at creative narration',
    'ljudeffekter av/på (tärningar, mynt, strid, level-up)': 'sound effects on/off (dice, coins, combat, level-up)',
    'musik av/på (stämningsbaserade loopar: natt, dag, strid, stad, vila, fängelsehål)': 'music on/off (mood-based loops: night, day, combat, town, rest, dungeon)',
    'DM begär kast vid osäkerhet, du slår': 'the DM calls for rolls when uncertain, you roll',
    'kort vila (1h) = återställ HP, lång vila (8h) = full HP + spell slots': 'short rest (1h) = restore HP, long rest (8h) = full HP + spell slots',
    '= erfarenhetspoäng, level-up vid trösklar (300, 900, 2700...)': '= experience points, level-up at thresholds (300, 900, 2700...)',
    '= death saves (1d20, 3 lyckade = stabil, 3 misslyckade = död)': '= death saves (1d20, 3 successes = stable, 3 failures = death)',
    '= lätt,': '= easy,',
    '= svårt': '= hard',
    '(bygg värld)': '(build world)',
    '(🔒) tills DM begär ett kast': '(🔒) until the DM calls for a roll',
    'Tärningsbrickan längst ner är': 'The dice tray at the bottom is',
    'DM vaknar': 'The DM awakens',
    'Tärningar': 'Dice',
    'Vad gör du här?': 'What do you do here?',
    'Prata med NPCs': 'Talk to NPCs',
    'Loggbok — Äventyrsjournal': 'Logbook — Adventure Journal',
    '📜 Loggbok — Äventyrsjournal': '📜 Logbook — Adventure Journal',
    'Krönikören sammanfattar ditt äventyr, dag för dag': 'The chronicler summarizes your adventure, day by day',
    'Uppdatera krönikan': 'Refresh the chronicle',
    '✦ Uppdatera krönikan': '✦ Refresh the Chronicle',
    'Äventyret hittills': 'The adventure so far',
    '✦ Äventyret hittills ✦': '✦ The Adventure So Far ✦',
    'Ingen loggbok ännu.': 'No logbook yet.',
    'Äventyret väntar på att skrivas…': 'The adventure awaits being written…',
    'Krönikören bläddrar i minnets hallar…': 'The chronicler leafs through the halls of memory…',
    'Vad världen vet om ditt äventyr': 'What the world knows about your adventure',
    'Ingen aktiv kampanj — skapa ett äventyr först': 'No active campaign — create an adventure first',
    'Ingen aktiv kampanj': 'No active campaign',
    'Minneskodex · Kända gestalter': 'Memory Codex · Known Characters',
    'Alla gestalter du mött längs vägen': 'Every character you\'ve met along the way',
    'Du har inte mött några gestalter ännu.': 'You haven\'t met any characters yet.',
    'Du har inte mött några gestalter ännu. De väntar i mörkret…': 'You haven\'t met any characters yet. They wait in the dark…',
    'Välj en gestalt ur minnets hall…': 'Choose a character from the hall of memory…',
    'Inget nedtecknat ännu. Anteckningar sparas automatiskt från chatten.': 'Nothing recorded yet. Notes are saved automatically from chat.',
    'Samtal sparas automatiskt från chatten.': 'Conversations are saved automatically from chat.',
    'Belöning:': 'Reward:',
    'Okänd': 'Unknown',
    'Vänlig': 'Friendly',
    'okänd': 'unknown',
    'vänlig': 'friendly',
    'Platser du besökt och vägar du kan vandra': 'Places you\'ve visited and roads you can walk',
    'världskarta': 'world map',
    '✦ världskarta ✦': '✦ world map ✦',
    'Du har inte besökt några platser ännu.': 'You haven\'t visited any places yet.',
    'Världen väntar bortom horisonten…': 'The world waits beyond the horizon…',
    'Aktivt uppdrag här': 'Active quest here',
    '⚑ Aktivt uppdrag här': '⚑ Active quest here',
    'Sevärdheter': 'Sights',
    'slätt': 'plain',
    'Karaktärsvalvet': 'The Character Vault',
    'Hjältar som väntar på nästa äventyr': 'Heroes waiting for their next adventure',
    'Sparade själar — redo att kastas in i nya världar': 'Saved souls — ready to be cast into new worlds',
    'Valvet är tomt': 'The vault is empty',
    'Inga hjältar vilar här ännu. Skapa en karaktär och spara den till valvet — så öppnas portarna.': 'No heroes rest here yet. Create a character and save it to the vault — and the gates will open.',
    'Öppnar valvets portar…': 'Opening the vault gates…',
    'Skapa en hjälte': 'Create a hero',
    '✨ Skapa en hjälte': '✨ Create a Hero',
    'Senaste äventyr:': 'Latest adventure:',
    '· Senaste äventyr:': '· Latest adventure:',
    'häxa': 'witch',
    'jägare': 'hunter',
    'väktare': 'warden',
    'Lämna': 'Leave',
    '🚪 Lämna': '🚪 Leave',
    '🧙 Karaktär': '🧙 Character',
    '🚪 Vägskälet': '🚪 The Crossroads',
    // ── adventure.html: campaign list (JS-generated) ──
    'Ingen hjälte än': 'No hero yet',
    'vändor': 'turns',
    'Senast spelad:': 'Last played:',
    'Fortsätt': 'Continue',
    '⚔️ Fortsätt': '⚔️ Continue',
    'Avsluta': 'End',
    'Kunde inte bygga världen: ': 'Could not build the world: ',
    'Kunde inte importera: ': 'Could not import: ',
    'Kunde inte aktivera kampanj: ': 'Could not activate campaign: ',
    ' Kunde inte radera': ' Could not delete',

    'Äventyret, världen och transkriptet försvinner för alltid. 💡 Tips: spara din karaktär i Valvet först.': 'The adventure, world and transcript will be gone forever. 💡 Tip: save your character in the Vault first.',
    '🔥 Radera': '🔥 Delete',
    'Behåll': 'Keep',
    '🕯️ Äventyret raderat': '🕯️ Adventure deleted',
    'Kunde inte skapa kampanj': 'Could not create campaign',
    'Dina äventyr': 'Your Adventures',
    '⚔️ Dina äventyr': '⚔️ Your Adventures',
    'Välj ett äventyr att fortsätta, eller skapa ett nytt nedan.': 'Choose an adventure to continue, or create a new one below.',
    'Ge ditt äventyr ett namn — eller låt det vara namnlöst och börja direkt.': 'Give your adventure a name — or leave it unnamed and begin right away.',
    'Ett namnlöst äventyr…': 'An unnamed adventure…',
    'Börja äventyret': 'Begin the adventure',
    '⚔️ Börja äventyret': '⚔️ Begin the adventure',
    'DM freestylar en öppningsscen åt dig': 'The DM freestyles an opening scene for you',
    'NIVÅ': 'LEVEL',

    // ── chat.html: effectText fragments (JS-generated) ──
    'Du helas ': 'You are healed ',
    'Fick: ': 'Obtained: ',
    'Förlorade: ': 'Lost: ',
    'Nytt uppdrag: ': 'New quest: ',
    'Uppdrag slutfört: ': 'Quest completed: ',
    'Uppdrag misslyckat: ': 'Quest failed: ',
    'Relation ändrad: ': 'Relationship changed: ',
    'Ny gestalt: ': 'New character: ',
    'Identitet avslöjad: ': 'Identity revealed: ',
    'Karaktärsuppdatering': 'Character update',
    'Ny plats: ': 'New location: ',
    'Du är nu i: ': 'You are now at: ',
    'Tid: ': 'Time: ',
    'Fick': 'Obtained',
    'Förlorade': 'Lost',

    // ── chat.html: console & misc JS strings ──
    'Hämtar loggar…': 'Fetching logs…',
    'Konsolen rensad.': 'Console cleared.',
    'Rullar…': 'Rolling…',
    'Alla': 'All',
    'Slutfört': 'Completed',
    'Misslyckat': 'Failed',
    'Aktivt': 'Active',
    'uppdrag': 'quest',

    // ── chat.html: mobile nav labels ──
    'Sällskap': 'Party',
    'Verktyg': 'Tools',

    // ── adventure.html: naming panel ──
    'Namnge ditt äventyr': 'Name your adventure',

    // ── chat.html: oracle error ──
    'Oraklet tiger: ': 'The oracle is silent: ',
    'okänt fel': 'unknown error',

    // ── chat.html: reason / DM monolog ──
    'DM:ns inre monolog': "The DM's inner monologue",
    ' ord': ' words',
    'Tärningen rullar…': 'The die is rolling…',

    // ── chat.html: model switch ──
    'Dungeon Master byter röst: ': 'The Dungeon Master changes voice: ',
    ' körs lokalt': ' · runs locally',
    'Kunde inte radera': 'Could not delete',
    'Kunde inte ladda upp: ': 'Could not upload: ',

    // ── character.html: item sheet rows ──
    'AC-bonus': 'AC bonus',
    'Laddningar': 'Charges',
    'Magisk bonus': 'Magic bonus',
    'Räckvidd': 'Range',
    '⚔ Utrusta': '⚔ Equip',
    '🎒 I väska': '🎒 In bag',
    '🎒 Packa ner': '🎒 Pack away',
    '🗑 Släng': '🗑 Discard',

  };

  // ═══════════════════════════════════════
  // CORE API
  // ═══════════════════════════════════════

  function getLang() { return _lang; }

  /**
   * Set the active language and translate the current page.
   * Called by each page with the campaign's language. Missing/undefined
   * language → English (UI är engelska-först; svenska väljs explicit).
   * Re-entrant: safe to call multiple times.
   */
  function init(lang) {
    _lang = (!lang || lang === 'en') ? 'en' : 'sv';
    _initialized = true;
    document.documentElement.lang = _lang;
    if (_lang === 'en') {
      applyAll();
    } else {
      restoreAll();
    }
  }

  /** Translate a single Swedish string. Returns the input unchanged for 'sv'. */
  function t(svString) {
    if (_lang !== 'en' || typeof svString !== 'string') return svString;
    return T[svString] !== undefined ? T[svString] : svString;
  }

  /**
   * Restore all previously translated text nodes, attributes and the title
   * back to their original Swedish. Safe to call when nothing was translated.
   */
  function restoreAll() {
    // Text nodes
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const n = walker.currentNode;
      if (_origText.has(n)) n.textContent = _origText.get(n);
    }
    // Attributes
    const ATTRS = ['placeholder', 'title', 'alt', 'aria-label', 'label'];
    for (const attr of ATTRS) {
      for (const el of document.querySelectorAll('[' + attr + ']')) {
        const orig = _origAttr.get(el);
        if (orig && orig[attr] !== undefined) el.setAttribute(attr, orig[attr]);
      }
    }
    // Title
    if (_origTitle !== null) { document.title = _origTitle; _origTitle = null; }
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
        if (val && T[val]) {
          if (!_origAttr.has(el)) _origAttr.set(el, {});
          const orig = _origAttr.get(el);
          if (orig[attr] === undefined) orig[attr] = val;
          el.setAttribute(attr, T[val]);
        }
      }
    }

    // 3) document.title (including "— suffix" titles)
    if (_origTitle === null) _origTitle = document.title;
    if (T[document.title]) {
      document.title = T[document.title];
    } else {
      // Replace ALL matching Swedish fragments in the title
      let t = document.title;
      for (const [sv, en] of Object.entries(T)) {
        if (sv.length > 3 && t.includes(sv)) {
          t = t.split(sv).join(en);
        }
      }
      document.title = t;
    }
  }

  /** Translate one text node — exact match first, then partial fragments. */
  function _translateTextNode(node) {
    const raw = node.textContent;
    const key = raw.trim();
    if (T[key]) {
      if (!_origText.has(node)) _origText.set(node, raw);
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
    if (out !== raw) {
      if (!_origText.has(node)) _origText.set(node, raw);
      node.textContent = out;
    }
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
  // AUTO-INIT — pages without an explicit I18N.init() call default to 'en'
  // ═══════════════════════════════════════
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { if (!_initialized) init('en'); });
  } else if (!_initialized) {
    init('en');
  }

  return { T, init, t, applyAll, restoreAll, getLang, speak, stopSpeaking };
})();
