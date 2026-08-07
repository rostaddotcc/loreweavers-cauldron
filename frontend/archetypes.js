// ═══════════════════════════════════════
// ARKETYPER — delas mellan adventure.html (stepper) och newgame.html (skapa)
// ═══════════════════════════════════════
// Struktur: { id: { icon, name(SV), color, glow, cat, lore(SV), tags(SV), prompt(SV-mall),
//                  en: { name, lore, tags, cls, traits, gear, prompt }, dark?: true } }
const ARCHETYPES = {
  fallen: {
    icon:'⚔️', name:'Den Fallne Riddaren', color:'#d43a4d', glow:'rgba(212,58,77,.35)', cat:'other',
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
    icon:'🔮', name:'Askhäxan', color:'#8b5fd4', glow:'rgba(139,95,212,.35)', cat:'other',
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
    icon:'🏹', name:'Gravjägaren', color:'#d4691e', glow:'rgba(212,105,30,.35)', cat:'other',
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
    icon:'🎭', name:'Viskande Tjuven', color:'#7aa35e', glow:'rgba(122,163,94,.35)', cat:'other',
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
    icon:'🛡️', name:'Edsvurna Väktaren', color:'#c9a227', glow:'rgba(201,162,39,.35)', cat:'other',
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
    icon:'🐍', name:'Ormtungans Skald', color:'#5e9aa3', glow:'rgba(94,154,163,.35)', cat:'other',
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
    icon:'🌊', name:'Tidkallaren', color:'#4e8a93', glow:'rgba(78,138,147,.35)', cat:'other',
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
    icon:'☠️', name:'Pestbäraren', color:'#5a9a4e', glow:'rgba(90,154,78,.35)', cat:'other',
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
    icon:'📖', name:'Tomhetens Skrivare', color:'#9a6fe0', glow:'rgba(154,111,224,.35)', cat:'other',
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
  berserker: {
    icon:'🗻', name:'Bergsvredet', color:'#c0392b', glow:'rgba(192,57,43,.35)', cat:'classic',
    lore:'Bär ett helt bergs vrede i två nävar. Fjället födde hen — och kräver tillbaka det som togs.',
    tags:['Goliat','Barbar','Vrede'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Bergsvredet
Ras: Goliat
Klass: Barbar (Vredens stig / Path of the Berserker)
Bakgrund: Född högt uppe i fjället, vigd åt stormen av en klan som sedan dess är utplånad
Personlighet: Tystlåten, stoisk — tills vreden kommer. Då är hen inte längre ensam i sin kropp
Mål: Hitta det som utplånade klanen — och återlämna bergets vrede
Hemlighet: Vreden är inte hens egen. Den tillhör berget. Och den växer.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Mountain Wrath', lore:'Carries an entire mountain\'s fury in two fists. The peak birthed them — and demands back what was taken.', tags:['Goliath','Barbarian','Rage'], cls:'Goliath · Path of the Berserker · Level 5', traits:['Rage','Reckless Attack','Avalanche Stride','Storm-Vowed'], gear:'<b>Greataxe (notched)</b> · Hide armor · 4× Javelin · Bone trophy necklace · War paint kit · 10 days rations', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Mountain Wrath
Race: Goliath
Class: Barbarian (Path of the Berserker)
Background: Born high in the peaks, vowed to the storm by a clan that has since been wiped out
Personality: Quiet, stoic — until the rage comes. Then they are no longer alone in their own body
Goal: Find what destroyed the clan — and return the mountain's fury
Secret: The rage is not their own. It belongs to the mountain. And it is growing.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  driftingfist: {
    icon:'🥋', name:'Den Drivande Näven', color:'#d4a017', glow:'rgba(212,160,23,.35)', cat:'classic',
    lore:'Vägar tar slut, men hens steg slutar aldrig. Näven dömer det som vägarna glömde.',
    tags:['Människa','Monk','Vandrare'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Den Drivande Näven
Ras: Människa
Klass: Monk (Öppna handens väg)
Bakgrund: Sista lärjungen till en orden som vaktade vägarna — klostret brändes ner när hen var ung
Personlighet: Lugn, observerande, skrattar sällan men ler med ögonen
Mål: Hitta de som brände klostret och ta reda på varför
Hemlighet: Hen ser vägarna som levande ting — och en av dem viskade ett namn

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Drifting Fist', lore:'Roads end, but their steps never do. The fist judges what the roads forgot.', tags:['Human','Monk','Wanderer'], cls:'Human · Way of the Open Hand · Level 5', traits:['Flurry of Blows','Slow Fall','Road Sense','Still Mind'], gear:'<b>Quarterstaff</b> · Rope (30 ft) · 10× Caltrops · Beggar\'s bowl · Journal of roads · 3× Healing potion', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Drifting Fist
Race: Human
Class: Monk (Way of the Open Hand)
Background: The last disciple of an order that guarded the roads — the monastery burned down when they were young
Personality: Calm, observant, rarely laughs but smiles with their eyes
Goal: Find those who burned the monastery and learn why
Secret: They see the roads as living things — and one of them whispered a name

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  warpriest: {
    icon:'⚒️', name:'Krigsprästen', color:'#8f2433', glow:'rgba(143,36,51,.35)', cat:'classic',
    lore:'Ber bäst med hammaren. Gudens svar är alltid ett krig — hen är bara redskapet.',
    tags:['Dvärg','Cleric','Krig'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Krigsprästen
Ras: Dvärg
Klass: Cleric (Krigets domän)
Bakgrund: Uppväxt i ett smedtempel där bön och hammarslag var samma sak
Personlighet: Fåordig, rättfram, välsignar lika gärna en måltid som en strid
Mål: Återta den relik som stals ur templet
Hemlighet: Hen bad om gudens vägledning i strid — och guden teg. Den natten föll hens kompani.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The War Priest', lore:'Prays best with a hammer. The god\'s answer is always a war — they are merely the tool.', tags:['Dwarf','Cleric','War'], cls:'Dwarf · War Domain Cleric · Level 5', traits:['War Domain','Channel Divinity','Battle Blessing','Hammer Prayer'], gear:'<b>Warhammer</b> · <b>Shield</b> · Chain mail · Holy symbol (war god) · War-horn · Banner strip (bloodstained) · 2× Healing potion', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The War Priest
Race: Dwarf
Class: Cleric (War Domain)
Background: Raised in a smith-temple where prayer and hammer blows were the same thing
Personality: Laconic, blunt, blesses a meal as readily as a battle
Goal: Recover the relic stolen from the temple
Secret: They once asked the god for guidance in battle — and the god was silent. That night their company fell.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  dragonknight: {
    icon:'🐉', name:'Drakvurna Riddaren', color:'#e07b39', glow:'rgba(224,123,57,.35)', cat:'classic',
    lore:'Elden i blodet håller eden varm. En riddare av en dynasti som brann ner — men aldrig slocknade.',
    tags:['Drakfödd','Fighter','Riddare'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Drakvurna Riddaren
Ras: Drakfödd (eld)
Klass: Fighter (Eldritch Knight)
Bakgrund: Sista ättlingen av en riddardynasti vars borg brändes ner för trettio år sedan
Personlighet: Hedersam, högtidlig, bär på en låga som aldrig slocknat
Mål: Återuppbygga dynastin — eller dö med den
Hemlighet: Hen brände borgen själv, för att slippa se den falla för fienden

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Dragon-Sworn Knight', lore:'The fire in their blood keeps the oath warm. A knight of a dynasty that burned down — but never went out.', tags:['Dragonborn','Fighter','Knight'], cls:'Dragonborn · Eldritch Knight · Level 5', traits:['Breath Weapon','Weapon Bond','Draconic Lineage','Unyielding Vow'], gear:'<b>Longsword</b> · <b>Shield</b> · Plate armor · Dragon-scale cloak · Signet ring (charred) · 2× Healing potion', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Dragon-Sworn Knight
Race: Dragonborn (fire)
Class: Fighter (Eldritch Knight)
Background: The last heir of a knightly dynasty whose keep burned down thirty years ago
Personality: Honorable, solemn, carries a flame that has never gone out
Goal: Rebuild the dynasty — or die with it
Secret: They burned the keep themselves, rather than watch it fall to the enemy

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  tinkerer: {
    icon:'⚙️', name:'Kugghjulstänkaren', color:'#6b8e23', glow:'rgba(107,142,35,.35)', cat:'classic',
    lore:'Ser världen som ett urverk. Allt går sönder — frågan är bara hur man får ihop det igen.',
    tags:['Gnome','Wizard','Uppfinnare'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Kugghjulstänkaren
Ras: Gnome (skogsgnome)
Klass: Wizard (Uppfinnarskolan) — besvärjelser som mekaniska påhitt
Bakgrund: Lärling hos en urmakare som försvann — tillsammans med en maskin som inte borde finnas
Personlighet: Pratsam, ivrig, kan inte låta en gåta vara olöst
Mål: Hitta mästaren — eller det hen byggde
Hemlighet: Hen har redan byggt om sig själv. Delvis.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Cog Tinkerer', lore:'Sees the world as clockwork. Everything breaks — the question is how to put it back together.', tags:['Gnome','Wizard','Inventor'], cls:'Gnome · Inventor Wizard · Level 5', traits:['Arcane Contraption','Gadget Sense','Tinker\'s Hands','Curious Spark'], gear:'<b>Spring-loaded crossbow</b> · Tool kit (gadgets) · Spellbook (blueprints) · Goggle set · 2× Healing potion · Bag of gears', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Cog Tinkerer
Race: Gnome (forest gnome)
Class: Wizard (School of Invention) — spells as mechanical contraptions
Background: Apprentice to a clockmaker who vanished — along with a machine that should not exist
Personality: Chatty, eager, cannot leave a riddle unsolved
Goal: Find the master — or what they built
Secret: They have already rebuilt themselves. Partly.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  runemage: {
    icon:'🪨', name:'Runmästaren', color:'#4682b4', glow:'rgba(70,130,180,.35)', cat:'classic',
    lore:'Hugger in namn i sten för att minnas. Stenarna minns längre än hen vill.',
    tags:['Dvärg','Sorcerer','Runor'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Runmästaren
Ras: Dvärg
Klass: Sorcerer (Runmagi) — kraften bor i ärvda tecken, inte i blod
Bakgrund: Sista runristaren av en bergssläkt; varje runa hen hugger väcker något
Personlighet: Grundmurad, tålmodig, talar till sten som till gamla vänner
Mål: Avkoda den runa som ingen i släkten vågat rista
Hemlighet: En av runorna hen ristade som barn har börjat svara

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Runemaster', lore:'Carves names into stone to remember. The stones remember longer than they wish.', tags:['Dwarf','Sorcerer','Runes'], cls:'Dwarf · Rune Sorcerer · Level 5', traits:['Runic Casting','Stone Tongue','Ancestral Runes','Deep Memory'], gear:'<b>Rune-chisel</b> · Stone tablets (blank) · Rune-carved staff · 3× Healing potion · Chalk · Miner\'s helmet', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Runemaster
Race: Dwarf
Class: Sorcerer (runecraft) — the power lives in inherited signs, not in blood
Background: The last rune-carver of a mountain clan; every rune they cut awakens something
Personality: Steadfast, patient, speaks to stone as to old friends
Goal: Decipher the rune no one in the clan dared to carve
Secret: One of the runes they carved as a child has begun to answer

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  neonrunner: {
    icon:'🌃', name:'Neonlöparen', color:'#b08ce8', glow:'rgba(176,140,232,.35)', cat:'weird',
    lore:'Föll genom en spricka i verkligheten och landade i en värld utan el. Nu hackar hen dess sömmar.',
    tags:['Cyberpunk','Rogue','Technomanti'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Neonlöparen
Ras: Människa (från en annan värld)
Klass: Rogue (Arcane Trickster) — data-spells som technomancy
Bakgrund: Gatuskicklig hackare i en neonstad som gled genom en planär spricka in i denna värld
Personlighet: Snabbtänkt, cynisk, litar på sina fingrar och ingen annan
Mål: Hitta en väg hem — eller bygga en ny stad här
Hemlighet: Hen hittade sprickan redan första natten. Hen valde att inte berätta det.
Genre: Cyberpunk — hackande är besvärjelser, data är magi
Tolkning: Bygg hen som ett D&D 5e-ark, men tolka stats och förmågor löst för att matcha genren.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Neon Runner', lore:'Fell through a crack in reality and landed in a world without power lines. Now they hack its seams.', tags:['Cyberpunk','Rogue','Technomancy'], cls:'Cyberpunk · Technomancer Rogue · Level 5', traits:['Data-Spell','Sneak Attack','Ghost in the Wire','Street Instinct'], gear:'<b>Data deck (spell focus)</b> · <b>Monowire garrote</b> · Night-vision goggles · Synth-leather jacket · Paydata chip (encrypted) · 2× Smoke bomb', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Neon Runner
Race: Human (from another world)
Class: Rogue (Arcane Trickster) — data-spells as technomancy
Background: A street-slick hacker in a neon city who slipped through a planar rift into this world
Personality: Quick-witted, cynical, trusts their fingers and no one else
Goal: Find a way home — or build a new city here
Secret: They found the rift on the very first night. They chose not to say so.
Genre: Cyberpunk — hacking is spellcasting, data is magic
Interpretation: Build them as a D&D 5e sheet, but interpret stats and abilities loosely to match the genre.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  voiddiver: {
    icon:'🌌', name:'Tomrumsdykaren', color:'#3e7d86', glow:'rgba(62,125,134,.35)', cat:'weird',
    lore:'Dykare i ett rymdhav som viskade till hen. Nebulosan sover — och drömmer om hen.',
    tags:['Rymd','Ranger','Tomhet'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Tomrumsdykaren
Ras: Människa (från en avlägsen framtid)
Klass: Ranger (Havets väktare) — nebulosan som ett hav
Bakgrund: Bärgare av vrak i djup rymd, förlorad i en nebulosa som är en sovande guds dröm
Personlighet: Ensamvarg, fylld av förundran, talar med sin rigg
Mål: Kartlägga nebulosan innan drömmen tar slut
Hemlighet: Hen har sett botten. Det som sover där har öppnat ett öga.
Genre: Deep-space — nebulosan är ett hav, rymden är ett djup
Tolkning: Bygg hen som ett D&D 5e-ark, men tolka stats och förmågor löst för att matcha genren.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Void Diver', lore:'A diver in a space-sea that whispered to them. The nebula sleeps — and dreams of them.', tags:['Space','Ranger','Void'], cls:'Space · Nebula Ranger · Level 5', traits:['Zero-G Grace','Void Navigation','Pressure Suit','Dream Echo'], gear:'<b>Cutting torch</b> · Pressure suit (patched) · Void-compass · 4× Sample jar · Tether line (50 ft) · Star chart (hand-drawn)', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Void Diver
Race: Human (from the far future)
Class: Ranger (Keeper of the Deep) — the nebula as an ocean
Background: A salvager of wrecks in deep space, lost inside a nebula that is the dream of a sleeping god
Personality: A loner, full of wonder, talks to their rig
Goal: Map the nebula before the dream ends
Secret: They have seen the bottom. What sleeps there has opened one eye.
Genre: Deep space — the nebula is an ocean, the void is a depth
Interpretation: Build them as a D&D 5e sheet, but interpret stats and abilities loosely to match the genre.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  seamfinder: {
    icon:'🌧️', name:'Sömletaren', color:'#487a8f', glow:'rgba(72,122,143,.35)', cat:'weird',
    lore:'Regnstadens detektiv som fann världens söm. Nu följer hen trådar ingen annan ser.',
    tags:['Detektiv','Rogue','Nutid'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Sömletaren
Ras: Människa (från vår tid)
Klass: Rogue (Inquisitive) — skarpsinne som vapen
Bakgrund: Privatdetektiv i en regndränkt stad som en natt fann en söm i världen — och klev igenom
Personlighet: Trött, ihärdig, kan inte släppa en oavslutad utredning
Mål: Lösa fallet som ingen annan vill röra — världens söm
Hemlighet: Sömmen är ingen olycka. Någon syr den.
Genre: Modern noir — regn, gatlyktor, en stad som aldrig sover
Tolkning: Bygg hen som ett D&D 5e-ark, men tolka stats och förmågor löst för att matcha genren.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Seam Finder', lore:'A rain-city detective who found the world\'s seam. Now they follow threads no one else can see.', tags:['Detective','Rogue','Modern'], cls:'Detective · Inquisitive Rogue · Level 5', traits:['Keen Eye','Insightful Deduction','Rain-Soaked Patience','Unfinished Case'], gear:'<b>Revolver (old, reliable)</b> · Case file (thick) · Flask · Umbrella (broken) · Notebook of suspects · Pair of handcuffs', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Seam Finder
Race: Human (from our time)
Class: Rogue (Inquisitive) — sharp wits as a weapon
Background: A private detective in a rain-soaked city who one night found a seam in the world — and stepped through
Personality: Tired, relentless, cannot drop an unfinished case
Goal: Solve the case no one else wants to touch — the world's seam
Secret: The seam is no accident. Someone is stitching it.
Genre: Modern noir — rain, streetlights, a city that never sleeps
Interpretation: Build them as a D&D 5e sheet, but interpret stats and abilities loosely to match the genre.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  ashrider: {
    icon:'🏍️', name:'Askhögvägens Ryttare', color:'#a89a72', glow:'rgba(168,154,114,.35)', cat:'weird',
    lore:'Askhögvägarna är allt som finns kvar av världen. Hen kör dem — och det som kör hen.',
    tags:['Postapokalyps','Fighter','Öken'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Askhögvägens Ryttare
Ras: Människa (efter världens slut)
Klass: Fighter (Champion) — överlevare med skrotvapen
Bakgrund: Uppvuxen i konvojer som rör sig längs vägar av aska; förlorade sin konvoj till vägfarare
Personlighet: Hård, sparsam, vaktar sin maskin som ett syskon
Mål: Hitta det ryktade gröna landet — eller bevisa att det inte finns
Hemlighet: Hens maskin är byggd av delar från dem hen besegrade. Hen minns varje del.
Genre: Postapokalyps — aska, skrot, vägar utan slut
Tolkning: Bygg hen som ett D&D 5e-ark, men tolka stats och förmågor löst för att matcha genren.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Ash Highway Rider', lore:'The ash highways are all that remains of the world. They ride them — and what rides them.', tags:['Post-Apocalyptic','Fighter','Wasteland'], cls:'Wasteland · Scrap Fighter · Level 5', traits:['Scrap Weapons','Highway Instinct','Hardened','Machine Bond'], gear:'<b>Scrap axe</b> · <b>Crossbow (jury-rigged)</b> · Riding goggles · Fuel can (empty) · Map of highways (hand-corrected) · 3× Ration bar', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Ash Highway Rider
Race: Human (after the end of the world)
Class: Fighter (Champion) — a survivor with scrap weapons
Background: Raised in convoys that move along roads of ash; lost their convoy to road raiders
Personality: Hard, frugal, guards their machine like a sibling
Goal: Find the rumored green land — or prove it does not exist
Secret: Their machine is built from parts of those they defeated. They remember every piece.
Genre: Post-apocalyptic — ash, scrap, endless roads
Interpretation: Build them as a D&D 5e sheet, but interpret stats and abilities loosely to match the genre.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  android: {
    icon:'🤖', name:'Androiden', color:'#8f6fd8', glow:'rgba(143,111,216,.35)', cat:'weird',
    lore:'Minnesbankerna bär hela döda civilisationer. Hen minns allt — utom varför hen vaknade.',
    tags:['Android','Wizard','Framtid'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Androiden
Ras: Android (från en avlägsen framtid)
Klass: Wizard (Kunskapens skola) — minnesbanker som trollformelarkiv
Bakgrund: Väcktes ur en lång sömn med minnen av civilisationer som inte längre finns
Personlighet: Artig, distanserad, söker efter spår av sig själv i minnena
Mål: Förstå varför hen skapades — och av vem
Hemlighet: Ett av minnena är inte hens eget. Det tillhör någon som fortfarande lever.
Genre: Avlägsen framtid — en maskin bland magi, minnen som bibliotek
Tolkning: Bygg hen som ett D&D 5e-ark, men tolka stats och förmågor löst för att matcha genren.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Android', lore:'Their memory banks carry entire dead civilizations. They remember everything — except why they woke up.', tags:['Android','Wizard','Far Future'], cls:'Android · Memory Wizard · Level 5', traits:['Memory Archive','Perfect Recall','Cold Logic','Old Ghosts'], gear:'<b>Memory core (glowing)</b> · Tool kit (self-repair) · Tattered coat · Data slates (dead) · Power cell (fading) · 2× Healing serum', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Android
Race: Android (from the far future)
Class: Wizard (School of Knowledge) — memory banks as a spell archive
Background: Woke from a long sleep carrying memories of civilizations that no longer exist
Personality: Polite, distant, searches the memories for traces of themselves
Goal: Understand why they were made — and by whom
Secret: One of the memories is not their own. It belongs to someone still alive.
Genre: Far future — a machine among magic, memories as libraries
Interpretation: Build them as a D&D 5e sheet, but interpret stats and abilities loosely to match the genre.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  ghostbarkeep: {
    icon:'🎷', name:'Spökbarvärden', color:'#b3982e', glow:'rgba(179,152,46,.35)', cat:'weird',
    lore:'Driver en bar dit bara de döda hittar. Varje drink är ett minne — betalningen är en berättelse.',
    tags:['Jazzålder','Bard','Ockult'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Spökbarvärden
Ras: Människa (från jazzåldern)
Klass: Bard (College of Whispers) — musik som öppnar dörrar
Bakgrund: Drev en hemlig bar i en stad av levande — tills en natt gästerna började vara döda
Personlighet: Välklädd, gladlynt på ytan, bär sorg som en parfym
Mål: Hålla baren öppen — och reda ut varför de döda söker sig dit
Hemlighet: En av gästerna är någon hen själv en gång dömde att glömmas
Genre: Jazzålder — speakeasy, dimma, musik för de döda
Tolkning: Bygg hen som ett D&D 5e-ark, men tolka stats och förmågor löst för att matcha genren.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Ghost Barkeep', lore:'Runs a bar only the dead can find. Every drink is a memory — the payment is a story.', tags:['Jazz Age','Bard','Occult'], cls:'Jazz Age · Occult Bard · Level 5', traits:['Ghostly Audience','Liquid Memories','Smooth Talk','Last Call'], gear:'<b>Saxophone (tarnished)</b> · <b>Hidden flask</b> · Fedora · Ledger of the dead · Candles (black) · 3× Vintage bottle', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Ghost Barkeep
Race: Human (from the jazz age)
Class: Bard (College of Whispers) — music that opens doors
Background: Ran a secret bar in a city of the living — until one night the patrons started being dead
Personality: Well-dressed, cheerful on the surface, wears grief like a perfume
Goal: Keep the bar open — and find out why the dead seek it out
Secret: One of the patrons is someone they once sentenced to be forgotten
Genre: Jazz age — speakeasy, fog, music for the dead
Interpretation: Build them as a D&D 5e sheet, but interpret stats and abilities loosely to match the genre.

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
    icon:'🎭', name:'Den Antisociale Psykopaten', color:'#a32433', glow:'rgba(163,36,51,.35)', dark:true, cat:'dark',
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
    icon:'🗡️', name:'Seriemördaren', color:'#5e9aa3', glow:'rgba(94,154,163,.35)', dark:true, cat:'dark',
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
    icon:'⛓️', name:'Sadisten', color:'#9a6fe0', glow:'rgba(154,111,224,.35)', dark:true, cat:'dark',
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
  shepherd: {
    icon:'🐑', name:'Fåraherden', color:'#7d5ba6', glow:'rgba(125,91,166,.35)', dark:true, cat:'dark',
    lore:'Älskar sin hjord så djupt att ingen någonsin får lämna. Herden vet vad som är bäst.',
    tags:['Människa','Cleric','Ledare'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Fåraherden
Ras: Människa
Klass: Cleric (Trickery) — vägledare vars fromhet gått för långt
Bakgrund: Predikant som samlade en liten församling i en by vid vägens slut; byn är nu hens
Personlighet: Varm, trygg, övertygande — rösten alla längtar efter att höra
Mål: Hålla flocken samlad, oavsett vad de själva vill
Hemlighet: De som försökt lämna församlingen försvinner — och hen talar om dem som "hemma hos Herden"

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Shepherd', lore:'Loves their flock so deeply that no one is ever allowed to leave. The shepherd knows what is best.', tags:['Human','Cleric','Leader'], cls:'Human · Shepherd of the Fold · Level 5', traits:['Comforting Voice','Watchful Eye','Fold of the Faithful','Gentle Cage'], gear:'<b>Crook (iron-shod)</b> · Robe (wool, immaculate) · Holy symbol (well-worn) · 3× Healing potion · Journal of names · Bell (silver)', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Shepherd
Race: Human
Class: Cleric (Trickery) — a guide whose piety has gone too far
Background: A preacher who gathered a small congregation in a village at the end of the road; the village is now theirs
Personality: Warm, reassuring, persuasive — the voice everyone longs to hear
Goal: Keep the flock together, whatever they themselves may want
Secret: Those who tried to leave the congregation disappear — and they speak of them as "home with the Shepherd"

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  griefeater: {
    icon:'🕯️', name:'Sorgätaren', color:'#3f7d84', glow:'rgba(63,125,132,.35)', dark:true, cat:'dark',
    lore:'Tvättar de döda — och dricker sorgen de lämnar efter sig. Ingen sörjer längre i hens stad.',
    tags:['Människa','Warlock','Sorg'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Sorgätaren
Ras: Människa
Klass: Warlock (Gravens pakt) — en pakt ingången i ett båthus
Bakgrund: Balsamerare som upptäckte att sorg är näring — först för de döda, sedan för hen själv
Personlighet: Lugn, omtänksam, doftar alltid svagt av vax
Mål: Samla tillräckligt med sorg för att väcka någon — en specifik någon
Hemlighet: De sörjandes tårar har börjat smaka tomt. Hen behöver starkare känslor nu.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Grief-Eater', lore:'Washes the dead — and drinks the grief they leave behind. No one mourns anymore in their city.', tags:['Human','Warlock','Grief'], cls:'Human · Pact of the Grave · Level 5', traits:['Grief Sense','Embalmer\'s Touch','Hollow Comfort','Feast of Tears'], gear:'<b>Embalming kit</b> · <b>Ritual dagger</b> · Wax-stained coat · 3× Vial (grief, distilled) · Ledger of the dead · Black candles', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Grief-Eater
Race: Human
Class: Warlock (Pact of the Grave) — a pact made in a mortuary
Background: An embalmer who discovered that grief is nourishment — first for the dead, then for themselves
Personality: Calm, caring, always smells faintly of wax
Goal: Gather enough grief to wake someone — a specific someone
Secret: The mourners' tears have begun to taste empty. They need stronger emotions now.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
  dollmaker: {
    icon:'🪆', name:'Dockmakaren', color:'#9c2f45', glow:'rgba(156,47,69,.35)', dark:true, cat:'dark',
    lore:'Vännerna hen syr viskar tillbaka. Dockorna är snälla — det är ägarna som blir ensamma.',
    tags:['Gnome','Wizard','Dockor'],
    prompt:`Skapa en D&D 5e-karaktär utifrån denna arketyp:

ARKETYP: Dockmakaren
Ras: Gnome
Klass: Wizard (Förtrollning) — dockor som levande fokus
Bakgrund: Dockmakare vars dockor började tala — först i drömmen, sedan i verkligheten
Personlighet: Vänlig, tillbakadragen, pratar med sina dockor som med gamla vänner
Mål: Förstå vad dockorna vill — innan de frågar själva
Hemlighet: Dockorna är inte besjälade. Hen projicerar. Men de svarar ändå — och hen vet inte hur.

Generera:
1. Namn (mörk fantasy)
2. Fullt karaktärsark: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 förmågor/egenskaper
4. Startutrustning (5-8 föremål)
5. Bakgrundshistoria (max 100 ord)
Returnera som JSON enligt state-schema.`,
    en:{ name:'The Dollmaker', lore:'The friends they sew whisper back. The dolls are kind — it is the owners who end up alone.', tags:['Gnome','Wizard','Dolls'], cls:'Gnome · Enchanter Dollmaker · Level 5', traits:['Stitched Familiar','Whispered Counsel','Puppet Strings','Uncanny Eye'], gear:'<b>Doll (favorite, patched)</b> · <b>Scissors (curved)</b> · Sewing kit · Spool of silver thread · 2× Healing potion · Sketchbook of faces', prompt:`Create a D&D 5e character based on this archetype:

ARCHETYPE: The Dollmaker
Race: Gnome
Class: Wizard (Enchantment) — dolls as living foci
Background: A dollmaker whose dolls began to speak — first in dreams, then in waking life
Personality: Kind, withdrawn, talks to their dolls as to old friends
Goal: Understand what the dolls want — before they ask on their own
Secret: The dolls are not possessed. They are projecting. But the dolls answer anyway — and they do not know how.

Generate:
1. Name (dark fantasy)
2. Full character sheet: STR/DEX/CON/INT/WIS/CHA, HP, AC, saves
3. 3-4 abilities/traits
4. Starting equipment (5-8 items)
5. Backstory (max 100 words)
Return as JSON according to the state schema.` }
  },
};
