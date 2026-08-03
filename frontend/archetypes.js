// ═══════════════════════════════════════
// ARKETYPER — delas mellan adventure.html (stepper) och newgame.html (skapa)
// ═══════════════════════════════════════
// Struktur: { id: { icon, name(SV), color, glow, lore(SV), tags(SV), prompt(SV-mall),
//                  en: { name, lore, tags, cls, traits, gear, prompt }, dark?: true } }
const ARCHETYPES = {
  fallen: {
    icon:'⚔️', name:'Den Fallne Riddaren', color:'#d43a4d', glow:'rgba(212,58,77,.35)',
    lore:'En vanärad paladin som söker upprättelse — eller hämnd — i mörkret.',
    tags:['Människa','Paladin','Närstrid'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Den Fallne Riddaren
Ras: Människa (variant)
Klass: Paladin (edsbruten — har förlorat sin gudomliga koppling)
Bakgrund: Vanärad adel, falskt anklagad för förräderi
Personlighet: Stoisk, plågsamt ärlig, bär på djup skuld
Mål: Återupprätta sitt namn — eller hämnas på förrädaren
Hemlighet: Edsbrottet var inte ett misstag…

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Fallen Knight', lore:'A disgraced paladin seeking redemption — or revenge — in the darkness.', tags:['Human','Paladin','Melee'], cls:'Human · Oathbroken Paladin · Level 5', traits:['Divine Sense','Oath of Vengeance','Protective Aura','Laying on Hands'], gear:'<b>Longsword</b> · <b>Shield</b> · Chain mail · Holy symbol (cracked) · 3× Healing potion · Rope · Rations', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Fallen Knight
Race: Human (variant)
Class: Paladin (oathbroken — has lost their divine connection)
Background: Disgraced nobility, falsely accused of treason
Personality: Stoic, painfully honest, carries deep guilt
Goal: Restore their name — or avenge themselves on the traitor
Secret: The broken oath was no accident…

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  witch: {
    icon:'🔮', name:'Askhäxan', color:'#8b5fd4', glow:'rgba(139,95,212,.35)',
    lore:'Eldmärkt av en förhäxelse hon aldrig bad om. Lågorna lyder henne — nästan.',
    tags:['Tiefling','Häxa','Magi'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Askhäxan
Ras: Tiefling
Klass: Warlock (Eld-pakt)
Bakgrund: Född under en askregnande komet, märkt av en uråldrig eldande
Personlighet: Skarptungad, nyfiken, rädd för sin egen kraft
Mål: Förstå varför elden valde just henne
Hemlighet: Pakten var inte hennes val — det var hennes moders

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Ash Witch', lore:'Branded by a curse she never asked for. The flames obey her — almost.', tags:['Tiefling','Warlock','Fire'], cls:'Tiefling · Fire-Pact Warlock · Level 5', traits:['Fire Resistance','Witchfire','Ash Step','Price of the Pact'], gear:'<b>Ash staff</b> · Component pouch · Spellbook (edges burned) · 2× Healing potion · 5× Torch · Coal amulet', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Ash Witch
Race: Tiefling
Class: Warlock (fire pact)
Background: Born beneath an ash-raining comet, marked by an ancient fire spirit
Personality: Sharp-tongued, curious, afraid of her own power
Goal: Understand why the fire chose her
Secret: The pact was not her choice — it was her mother's

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  hunter: {
    icon:'🏹', name:'Gravjägaren', color:'#d4691e', glow:'rgba(212,105,30,.35)',
    lore:'Jagar det som vägrar stanna dött. Silver armborst, kallt hjärta.',
    tags:['Halvälva','Ranger','Dödjägare'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Gravjägaren
Ras: Halvälva
Klass: Ranger (Dödjägare)
Bakgrund: Upplärd av en tyst orden som jagar odöda
Personlighet: Fåordig, vaksam, bär på en förlust
Mål: Utrota den vampyr som tog hens syster
Hemlighet: Hen har själv blivit biten — och räknar dagarna

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Grave Hunter', lore:'Hunts what refuses to stay dead. Silver crossbow, cold heart.', tags:['Half-Elf','Ranger','Undead Slayer'], cls:'Half-Elf · Undead Slayer · Level 5', traits:['Undead Bane','Silver Bolt','Shadow Step','Hunter\'s Mark'], gear:'<b>Crossbow (silver bolts)</b> · <b>Shortsword</b> · Leather armor · 3× Holy water · Garlic wreath · Map of graveyards', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Grave Hunter
Race: Half-Elf
Class: Ranger (undead slayer)
Background: Raised by a silent order that hunts the undead
Personality: Few words, ever watchful, carries a loss
Goal: Destroy the vampire that took their sister
Secret: They have been bitten themselves — and are counting the days

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  thief: {
    icon:'🎭', name:'Viskande Tjuven', color:'#7aa35e', glow:'rgba(122,163,94,.35)',
    lore:'Hör de dödas hemligheter. Låser, fickor, gravar — allt öppnar sig.',
    tags:['Halvling','Rogue','Spion'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Viskande Tjuven
Ras: Halvling
Klass: Rogue (Spion/Whisperer)
Bakgrund: Växte upp på en kyrkogård, lärde sig "lyssna" av de döda
Personlighet: Lättsam på ytan, alltid rädd i botten
Mål: Stjäla tillbaka något som tillhörde hens döda mor
Hemlighet: De döda ljuger ibland — och hen vet inte längre vem som viskar

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Whispering Thief', lore:'Hears the secrets of the dead. Locks, pockets, graves — everything opens.', tags:['Halfling','Rogue','Spy'], cls:'Halfling · Whisperer · Level 5', traits:['Sneak Attack','Death Whispers','Lockpicking','Shadow Dance'], gear:'<b>Shortsword</b> · <b>2× Dagger</b> · Leather armor · Thieves\' tools · 3× Smoke bomb · Amulet (mother\'s)', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Whispering Thief
Race: Halfling
Class: Rogue (spy/whisperer)
Background: Grew up in a graveyard, learned to "listen" from the dead
Personality: Light-hearted on the surface, always afraid underneath
Goal: Steal back something that belonged to their dead mother
Secret: The dead sometimes lie — and Pip no longer knows who is whispering

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  warden: {
    icon:'🛡️', name:'Edsvurna Väktaren', color:'#c9a227', glow:'rgba(201,162,39,.35)',
    lore:'Vaktar en glömd grav. Eden är allt som finns kvar av hens folk.',
    tags:['Dvärg','Väktare','Försvar'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Edsvurna Väktaren
Ras: Dvärg
Klass: Fighter (Väktare/Champion)
Bakgrund: Sista medlemmen av en orden som vaktade en glömd konungagrav
Personlighet: Orubblig, torr humor, djupt lojal
Mål: Fullborda eden — även om det blir det sista hen gör
Hemlighet: Graven är redan plundrad. Hen väktar något som inte längre finns där.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Oathsworn Warden', lore:'Guards a forgotten tomb. The oath is all that remains of their people.', tags:['Dwarf','Fighter','Defense'], cls:'Dwarf · Grave Warden · Level 5', traits:['Second Wind','Stone Skin','Oath of the Grave','Protective Stance'], gear:'<b>Warhammer</b> · <b>Shield (runed)</b> · Splint armor · 2× Healing potion · Runestone · Dwarven ale (last bottle)', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Oathsworn Warden
Race: Dwarf
Class: Fighter (warden/champion)
Background: Last member of an order that guarded a forgotten king's tomb
Personality: Unshakeable, dry humor, deeply loyal
Goal: Fulfill the oath — even if it is the last thing they do
Secret: The tomb has already been emptied. They guard something that is no longer there.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  skald: {
    icon:'🐍', name:'Ormtungans Skald', color:'#5e9aa3', glow:'rgba(94,154,163,.35)',
    lore:'Sånger som böjer sinnen. Varje vers är ett gift — eller ett botemedel.',
    tags:['Älv','Bard','Förförare'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Ormtungans Skald
Ras: Älv
Klass: Bard (Viskare/College of Whispers)
Bakgrund: Utesluten från sin hov för "farliga sånger"
Personlighet: Charmig, gåtfull, alltid tre steg före
Mål: Återupprätta sin plats vid hovet — eller bränna det
Hemlighet: En av hens sånger dödade en konung. Ingen vet. Än.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Serpent-Tongue Skald', lore:'Songs that bend minds. Every verse is a poison — or a cure.', tags:['Elf','Bard','Beguiler'], cls:'Elf · Whisper Bard · Level 5', traits:['Whispering Verse','Venomous Charm','Song of Fear','Ambiguous'], gear:'<b>Violin (hidden blade)</b> · <b>Dagger</b> · Leather armor · 2× Poison vial (sleep) · Forgery kit · Love letter (stolen)', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Serpent-Tongue Skald
Race: Elf
Class: Bard (whisperer/College of Whispers)
Background: Exiled from their court for "dangerous songs"
Personality: Charming, enigmatic, always three steps ahead
Goal: Reclaim their place at court — or burn it down
Secret: One of their songs killed a king. No one knows. Yet.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  tidecaller: {
    icon:'🌊', name:'Tidkallaren', color:'#4e8a93', glow:'rgba(78,138,147,.35)',
    lore:'Havet svarar när hen viskar. Men havet glömmer aldrig en skuld.',
    tags:['Människa','Druid','Hav'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Tidkallaren
Ras: Människa
Klass: Druid (Havets cirkel)
Bakgrund: Född under en stormflod, uppfostrad av en fyr-vaktare
Personlighet: Lugn på ytan, storm inuti, talar med havet
Mål: Hitta den sjunkna staden som hen drömmer om varje natt
Hemlighet: Hen dränkte en gång någon — och havet gav dem tillbaka, förändrad

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Tidecaller', lore:'The sea answers when they whisper. But the sea never forgets a debt.', tags:['Human','Druid','Sea'], cls:'Human · Circle of the Sea · Level 5', traits:['Tide Whisper','Storm Skin','Eye of the Deep','Salt Cure'], gear:'<b>Coral staff</b> · <b>Fishing net (reinforced)</b> · Leather armor (sea-leather) · 2× Healing potion · Lighthouse lantern · Chart of currents', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Tidecaller
Race: Human
Class: Druid (Circle of the Sea)
Background: Born during a storm surge, raised by a lighthouse keeper
Personality: Calm on the surface, storm within, speaks to the sea
Goal: Find the sunken city they dream of every night
Secret: They once drowned someone — and the sea gave them back, changed

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  plaguebearer: {
    icon:'☠️', name:'Pestbäraren', color:'#5a9a4e', glow:'rgba(90,154,78,.35)',
    lore:'Bär sjukdomen i sina ådror — och botemedlet i sin väska.',
    tags:['Halvling','Cleric','Pestläkare'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Pestbäraren
Ras: Halvling
Klass: Cleric (Pestläkare / Grave Domain)
Bakgrund: Överlevde en pest som tog hela hens by — bar smittan utan att dö
Personlighet: Mörk humor, öm om de sjuka, livrädd för att röra vid friska
Mål: Hitta botemedlet mot den pest hen bär i sitt blod
Hemlighet: Hen smittar andra — långsamt, utan att veta om det

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Plaguebearer', lore:'Carries the disease in their veins — and the cure in their bag.', tags:['Halfling','Cleric','Plague Doctor'], cls:'Halfling · Plague Doctor · Level 5', traits:['Plague Ward','Disease Sense','Healing Hands','Whisper of the Blight'], gear:'<b>Plague mask</b> · <b>Scalpel</b> · Chain mail · 3× Antidote · Herb pouch · Journal (full of symptoms)', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Plaguebearer
Race: Halfling
Class: Cleric (plague doctor / Grave Domain)
Background: Survived a plague that took their entire village — carried the infection without dying
Personality: Dark humor, tender toward the sick, terrified of touching the healthy
Goal: Find the cure for the plague they carry in their blood
Secret: They infect others — slowly, without knowing it

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  voidscribe: {
    icon:'📖', name:'Tomhetens Skrivare', color:'#9a6fe0', glow:'rgba(154,111,224,.35)',
    lore:'Skrev ett namn i en förbjuden bok. Nu skriver boken i hen.',
    tags:['Människa','Wizard','Tomhet'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Tomhetens Skrivare
Ras: Människa
Klass: Wizard (Tomhetens skola / Void Scribe)
Bakgrund: Bibliotekarie som hittade en bok som inte borde finnas
Personlighet: Frånvarande, talar i citat, skriver i sömnen
Mål: Fylla bokens tomma sidor innan den fyller hen
Hemlighet: Varje sida hen skriver raderar ett minne — hens egna, först

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Voidscribe', lore:'Wrote a name in a forbidden book. Now the book writes in them.', tags:['Human','Wizard','Void'], cls:'Human · Void Scribe · Level 5', traits:['Void Ink','Erasure','Dream Writing','Whisper of the Book'], gear:'<b>Forbidden book (chained)</b> · <b>Quill (bone)</b> · Robe (ink-stained) · 2× Healing potion · Ink bottle (blacker than black) · Reading glasses', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Voidscribe
Race: Human
Class: Wizard (Void Scribe / School of the Void)
Background: A librarian who found a book that should not exist
Personality: Absent-minded, speaks in quotes, writes in their sleep
Goal: Fill the book's empty pages before it fills them
Secret: Every page they write erases a memory — their own, first

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  // ════════════════════════════════════════════════════
  // MÖRKA ARKETYPER (dropdown) — dark:true → visas EJ som kort,
  // bara i "Dark Paths"-dropdownen under arketypgriden.
  // ════════════════════════════════════════════════════
  psycho: {
    icon:'🎭', name:'Den Antisociale Psykopaten', color:'#a32433', glow:'rgba(163,36,51,.35)', dark:true,
    lore:'Charmig mask, iskall blick. Människor är verktyg — och verktyg går sönder.',
    tags:['Människa','Rogue','Manipulatör'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Den Antisociale Psykopaten
Ras: Människa (variant)
Klass: Rogue (Mastermind) — manipulativ strateg
Bakgrund: Uppväxt bland adel och lögnare; lärde sig tidigt att empati är en svaghet
Personlighet: Charmig, karismatisk, fullständigt känslokall — ser alla som pjäser
Mål: Bygga ett nätverk av beroende människor — kontrollera stadens makt genom skuld och rädsla
Hemlighet: Har redan förstört ett liv fullständigt — och njöt av det

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Antisocial Psychopath', lore:'A charming mask, an icy gaze. People are tools — and tools break.', tags:['Human','Rogue','Manipulator'], cls:'Human · Mastermind Rogue · Level 5', traits:['Silver Tongue','Unreadable','Cold Calculation','Web of Debts'], gear:'<b>Rapier (hidden)</b> · Disguise kit · Signet ring · Blackmail letters · 2× Poison vial · Fine clothes · Thieves\' tools', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Antisocial Psychopath
Race: Human (variant)
Class: Rogue (Mastermind) — manipulative strategist
Background: Raised among nobles and liars; learned early that empathy is a weakness
Personality: Charming, charismatic, utterly cold — sees everyone as pieces on a board
Goal: Build a network of dependent people — control the city's power through guilt and fear
Secret: Has already destroyed one life completely — and enjoyed it

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  serial: {
    icon:'🗡️', name:'Seriemördaren', color:'#5e9aa3', glow:'rgba(94,154,163,.35)', dark:true,
    lore:'Metodisk. Tystlåten. Fullbordar mönster ingen annan ser.',
    tags:['Människa','Rogue','Jägare'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Seriemördaren
Ras: Människa
Klass: Rogue (Assassin) — ritualistisk jägare
Bakgrund: Lärling hos en slaktare; upptäckte att vissa nätter kräver offer
Personlighet: Artig, tyst, metodisk; samlar på troféer ingen någonsin hittar
Mål: Fullborda mönstret — det trettonde offret
Hemlighet: Polisen letar efter en vilde; ingen misstänker hen, den hjälpsamma grannen

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Serial Killer', lore:'Methodical. Quiet. Completes patterns no one else can see.', tags:['Human','Rogue','Hunter'], cls:'Human · Assassin Rogue · Level 5', traits:['Patient Predator','Ritual Mind','Trophy Keeper','Impeccable Manners'], gear:'<b>Dagger (ceremonial)</b> · <b>Shortbow</b> · Leather armor · Rope · Bone saw · Journal of dates · 2× Smoke bomb', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Serial Killer
Race: Human
Class: Rogue (Assassin) — ritualistic hunter
Background: Apprentice to a butcher; discovered that some nights demand an offering
Personality: Polite, quiet, methodical; keeps trophies no one ever finds
Goal: Complete the pattern — the thirteenth victim
Secret: The guard hunts a beast; no one suspects them, the helpful neighbour

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  sadist: {
    icon:'⛓️', name:'Sadisten', color:'#9a6fe0', glow:'rgba(154,111,224,.35)', dark:true,
    lore:'Smärta är ett språk — och hen talar det flytande.',
    tags:['Tiefling','Cleric','Plågare'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Sadisten
Ras: Tiefling
Klass: Cleric (Smärtans domän) — helare som njuter av att skada
Bakgrund: Tempelpräst som insåg att bön besvaras tydligast under plåga
Personlighet: Lugn, vårdande röst; ögonen glittrar när någon lider
Mål: Hitta den som aldrig brutits — och bryta hen
Hemlighet: Läker bara för att kunna skada igen

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Sadist', lore:'Pain is a language — and they speak it fluently.', tags:['Tiefling','Cleric','Tormentor'], cls:'Tiefling · Cleric of Pain · Level 5', traits:['Clinical Calm','Anatomy Student','Gentle Touch','Merciless Focus'], gear:'<b>Mace (spiked)</b> · <b>Chainmail</b> · Holy symbol (broken) · Scalpel set · 3× Healing potion · Manacles · Book of prayers (marginalia)', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Sadist
Race: Tiefling
Class: Cleric (Domain of Pain) — a healer who delights in harming
Background: Temple priest who realized prayers are answered most clearly through suffering
Personality: Calm, soothing voice; eyes glitter when someone is in pain
Goal: Find the one who has never been broken — and break them
Secret: Only heals so they can hurt again

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
};
