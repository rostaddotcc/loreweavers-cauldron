/**
 * 🌍 i18n.js — Språkväxlare för Mörkrets Rike
 * 
 * DOM-baserad översättning: hittar svenska textnoder och ersätter med engelska.
 * Kräver inga data-i18n-attribut i HTML-filerna.
 * 
 * Användning: Laddas på alla sidor. Toggle via Ctrl+Shift+L eller knappen uppe till höger.
 */
const I18N = (() => {
  let _lang = localStorage.getItem('dnd_lang') || 'sv';

  // ═══════════════════════════════════════
  // ÖVERSÄTTNINGAR: svenska → engelska
  // ═══════════════════════════════════════
  const T = {
    // ── Globalt / Alla sidor ──
    'Ett svenskt D&D-äventyr': 'A Swedish D&D Adventure',
    'Stig in i mörkret': 'Enter the Darkness',
    'Till vägskälet': 'Back to the Crossroads',
    'Till bordet': 'To the Table',
    'Lämna': 'Leave',
    'Läser in': 'Loading',

    // ── login.html ──
    'Vem vågar stiga in i mörkret?': 'Who dares enter the darkness?',
    'Äventyrare': 'Adventurer',
    'Lösenord': 'Password',
    '⚔ Stig in i mörkret': '⚔ Enter the Darkness',
    'Glömt lösenordet?': 'Forgot your password?',

    // ── adventure.html ──
    'Vägskälet': 'The Crossroads',
    'Steg ett av fyra': 'Step one of four',
    'Varje äventyr börjar med ett val. Vilken väg tar du?': 'Every adventure begins with a choice. Which path will you take?',
    'Ditt pågående äventyr': 'Your Ongoing Adventure',
    'Fortsätt äventyret': 'Continue Adventure',
    'Avsluta äventyret': 'End Adventure',
    'ett': 'one',
    'äventyr kan pågå åt gången — nya vägar låses tills detta är avslutat.': 'adventure can run at a time — new paths are locked until this one ends.',
    'Förbered äventyr': 'Prepare Adventure',
    'Prompt + Import': 'Prompt + Import',
    'Importera äventyr': 'Import Adventure',
    'Nytt äventyr': 'New Adventure',
    'Freestyle · Direkt': 'Freestyle · Instant',
    'Förbered din värld': 'Prepare Your World',
    'Dra in filer eller': 'Drag files here or',
    'klicka för att bläddra': 'click to browse',
    'Qwen extraherar worldbuilding, karaktärer, platser': 'Qwen extracts worldbuilding, characters, locations',
    'Qwen läser in din värld…': 'Qwen is reading your world…',
    'Platser': 'Locations',
    'Uppdrag': 'Quests',
    'Skapa karaktär & börja': 'Create Character & Begin',
    'Världen sparas och': 'The world is saved and',
    'använder den som grund för äventyret': 'uses it as the foundation for the adventure',
    'Bygg världen': 'Build the World',
    'Prompt + filer skickas till': 'Prompt + files are sent to',
    'som strukturerar allt': 'which structures everything',
    'Importera befintlig kampanj': 'Import Existing Campaign',
    'Dra in dina kampanjfiler eller': 'Drag your campaign files or',
    'Qwen extraherar karaktärer, NPCs, platser och lore…': 'Qwen extracts characters, NPCs, locations and lore…',
    'Karaktärer': 'Characters',

    // ── newgame.html ──
    'Välj ditt öde': 'Choose Your Fate',
    'Steg ett av tre': 'Step one of three',
    'Valvet — återkalla en sparad hjälte': 'The Vault — recall a saved hero',
    'Arketyper': 'Archetypes',
    'Ödesväven': 'The Fateweave',
    'Tom pergament': 'Blank Parchment',
    '— skriv fritt': '— write freely',
    '✦ Tom pergament': '✦ Blank Parchment',
    'Frammana karaktär': 'Summon Character',
    'Dungeon Master väver din ödesväv…': 'The Dungeon Master weaves your fate…',
    'Din hjälte': 'Your Hero',
    '⚔️ Till bordet': '⚔️ To the Table',
    'Slå om ödet': 'Reroll Fate',
    'Spara i valvet': 'Save to Vault',
    'snabb': 'fast',

    // ── chat.html ──
    'Karaktär': 'Character',
    'Världen': 'The World',
    'Verktyg': 'Tools',
    'Kartan': 'The Map',
    'platser & resvägar': 'locations & travel routes',
    'Loggbok': 'Logbook',
    'dina anteckningar': 'your notes',
    'Gestalter': 'Personages',
    'kända NPCs': 'known NPCs',
    'Arkivet': 'The Archive',
    'minnen & fakta': 'memories & facts',
    'Valvet': 'The Vault',
    'inventarium & skatter': 'inventory & treasures',
    'Regel-oraklet': 'Rule Oracle',
    'fråga om 5e-regler': 'ask about 5e rules',
    'Maskinrummet': 'The Engine Room',
    'live debug-loggar': 'live debug logs',
    'Hur spelar man?': 'How to Play?',
    'kommandon & tips': 'commands & tips',
    'Exportera': 'Export',
    'kampanj som zip': 'campaign as zip',
    'Sällskapet': 'The Party',
    'Skriv ditt drag…': 'Write your move…',
    'Berättaren (mörk)': 'The Narrator (dark)',
    'Sagorösten (ljus)': 'The Storyteller (light)',
    'Krigaren (kraftfull)': 'The Warrior (powerful)',
    'Häxan (mystisk)': 'The Witch (mysterious)',

    // ── character.html ──
    'Karaktärsark': 'Character Sheet',
    'Utrustning': 'Equipment',
    'Skattkammare': 'Treasury',
    'Anteckningar': 'Notes',
    'För in bild': 'Add image',
    'Hälsopoäng': 'Hit Points',
    'Skada': 'Damage',
    'Hela': 'Heal',
    'Styrka': 'Strength',
    'Smidighet': 'Dexterity',
    'Fysik': 'Constitution',
    'Intelligens': 'Intelligence',
    'Vishet': 'Wisdom',
    'Karisma': 'Charisma',
    'Rustning': 'Armor',
    'Vapen': 'Weapon',
    'Dryck': 'Potion',
    'Magisk': 'Magical',
    'Verktyg': 'Tool',
    'Annat': 'Other',
    'Lägg till': 'Add',
    'Namn': 'Name',
    'Antal': 'Qty',
    'Vikt': 'Weight',
    'Sällsynthet': 'Rarity',
    'Initiativ': 'Initiative',
    'Perception': 'Perception',
    'Fart': 'Speed',
    'Proficiency': 'Proficiency',
    'Nivå': 'Level',
    'Erfarenhet': 'Experience',

    // ── help.html ──
    'Hur spelar man': 'How to Play',
    'Kommandon': 'Commands',
    'Tips': 'Tips',

    // ── loggbok.html ──
    'Kampanjloggbok': 'Campaign Logbook',
    'Dag': 'Day',

    // ── Toasts / Systemmeddelanden ──
    'Kunde inte generera ljud': 'Could not generate audio',
    'Kunde inte spela upp ljud': 'Could not play audio',
    'Lore tillagd': 'Lore added',
    'Bygger kampanj-export…': 'Building campaign export…',
    'Bild uppdaterad': 'Image updated',
    'Export ej tillgänglig i mock-läge': 'Export not available in mock mode',
    'Session utgången': 'Session expired',
    'Ingen aktiv kampanj': 'No active campaign',
    'Karaktären kunde inte vävas': 'The character could not be woven',
  };

  // ═══════════════════════════════════════
  // PLATSHÅLLARE (input/textarea)
  // ═══════════════════════════════════════
  const PLACEHOLDERS = {
    'Skriv ditt drag…': 'Write your move…',
    'Äventyrare': 'Adventurer',
    'Lösenord': 'Password',
    'Sök bland gestalter…': 'Search personages…',
    'Fråga regel-oraklet…': 'Ask the Rule Oracle…',
  };

  // ═══════════════════════════════════════
  // KÄRNA
  // ═══════════════════════════════════════

  function getLang() { return _lang; }

  function setLang(lang) {
    _lang = lang;
    localStorage.setItem('dnd_lang', lang);
    applyI18n();
    _updateToggle();
  }

  function applyI18n() {
    if (_lang === 'sv') return; // Svenska är original — inget att översätta

    // 1) Ersätt textnoder
    const walker = document.createTreeWalker(
      document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const p = node.parentElement;
          if (!p) return NodeFilter.FILTER_REJECT;
          const tag = p.tagName;
          if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'CODE' || tag === 'PRE') return NodeFilter.FILTER_REJECT;
          if (p.closest('#debug-panel')) return NodeFilter.FILTER_REJECT;
          const t = node.textContent.trim();
          return t.length > 1 && T[t] ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
      }
    );
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const n of nodes) {
      const key = n.textContent.trim();
      if (T[key]) n.textContent = n.textContent.replace(key, T[key]);
    }

    // 2) Ersätt placeholders
    for (const el of document.querySelectorAll('[placeholder]')) {
      const ph = el.getAttribute('placeholder');
      if (PLACEHOLDERS[ph]) el.setAttribute('placeholder', PLACEHOLDERS[ph]);
    }

    // 3) Ersätt title-attribut
    for (const el of document.querySelectorAll('[title]')) {
      const t = el.getAttribute('title');
      if (T[t]) el.setAttribute('title', T[t]);
    }

    // 4) Uppdatera document.title
    if (T[document.title]) document.title = T[document.title];
    // Hantera "— suffix" i titles
    for (const [sv, en] of Object.entries(T)) {
      if (document.title.includes(sv)) {
        document.title = document.title.replace(sv, en);
        break;
      }
    }
  }

  // ═══════════════════════════════════════
  // TOGGLE-KNAPP
  // ═══════════════════════════════════════
  let _toggle = null;

  function _updateToggle() {
    if (!_toggle) return;
    const btn = _toggle.querySelector('.i18n-active');
    if (btn) btn.classList.remove('i18n-active');
    const active = _toggle.querySelector(`[data-lang="${_lang}"]`);
    if (active) active.classList.add('i18n-active');
  }

  function createLangToggle() {
    if (_toggle) return;
    _toggle = document.createElement('div');
    _toggle.id = 'i18n-toggle';
    _toggle.innerHTML = `
      <button data-lang="sv" class="${_lang === 'sv' ? 'i18n-active' : ''}">SV</button>
      <button data-lang="en" class="${_lang === 'en' ? 'i18n-active' : ''}">EN</button>`;
    _toggle.querySelectorAll('button').forEach(b => {
      b.addEventListener('click', () => setLang(b.dataset.lang));
    });
    document.body.appendChild(_toggle);

    const style = document.createElement('style');
    style.textContent = `
      #i18n-toggle{position:fixed;top:10px;right:10px;z-index:9998;display:flex;gap:0;
        border:2px solid #c9a227;border-radius:3px;overflow:hidden;
        box-shadow:0 2px 12px rgba(0,0,0,.5),0 0 8px rgba(201,162,39,.2)}
      #i18n-toggle button{background:#1a1a2e;color:#8a8a9a;border:none;
        font-family:'Press Start 2P',monospace;font-size:9px;padding:6px 10px;
        cursor:pointer;transition:all .2s;letter-spacing:.05em}
      #i18n-toggle button:hover{color:#e8c65a;background:#222244}
      #i18n-toggle button.i18n-active{background:#c9a227;color:#0a0a12;font-weight:bold}`;
    document.head.appendChild(style);
  }

  // ═══════════════════════════════════════
  // TTS (Browser SpeechSynthesis)
  // ═══════════════════════════════════════
  let _ttsAudio = null;

  function speak(text, lang) {
    if (!window.speechSynthesis) return false;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = lang === 'en' ? 'en-US' : 'sv-SE';
    utter.rate = 0.92;
    utter.pitch = 0.9;
    // Föredra en mörkare röst om tillgänglig
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
  // INIT
  // ═══════════════════════════════════════
  document.addEventListener('DOMContentLoaded', () => {
    createLangToggle();
    if (_lang !== 'sv') {
      // Vänta lite så att dynamiskt innehåll hunnit renderas
      setTimeout(applyI18n, 100);
    }
  });

  // Ctrl+Shift+L för att växla språk
  document.addEventListener('keydown', e => {
    if (e.ctrlKey && e.shiftKey && e.key === 'L') {
      e.preventDefault();
      setLang(_lang === 'sv' ? 'en' : 'sv');
    }
  });

  return { T, PLACEHOLDERS, getLang, setLang, applyI18n, createLangToggle, speak, stopSpeaking };
})();
