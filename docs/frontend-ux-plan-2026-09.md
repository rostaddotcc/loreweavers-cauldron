# Frontend UX/UI-åtgärdsplan — 2026-09-17

Källa: rostads 8-punkterslista. Alla findings verifierade mot koden (file:line nedan).
Design-lins: Anthropic `frontend-design`-skill (medveten typografi, struktur=information,
copy som designmaterial, motion med disciplin) + projektets egen estetik
(Castlevania×DOS×terminal, guld+bone+arcane, UI på engelska).

---

## 1. Sidinventering (punkt 1)

20 publika sidor: login, adventure, newgame, chat, character, characters (The Forge),
npcs, platser, loggbok, facts, help, mechanics, models, pricing, releases, reset,
screenshots, admin, index, book-souls.

Audit-våg går igenom alla med frontend-design-principerna → issue-lista (file:line,
severity) innan fixes. Kända axplock redan nu:
- newgame.html:191 "Step one of three" — stale label, sidan är ett långt scroll, inte 3 steg.
- newgame.html:200 tom `<option selected>` för språk — tvingar val utan default.
- adventure.html step-model: 4 modellval (DM, Lorekeeper, Extraction, TTS) + 3 not-rader
  + upgrade-note — överväldigande för en ny spelare.
- login.html auth-btn "What will the Cauldron Foretell?" — charmig men otydlig som CTA.
- Stora releases/mechanics/help-sidor: innehålls- och typografi-genomgång.

## 2. Toast/banner på login (punkt 2)

Verifierat: backend `FREE_PLAYER_MODELS = ("qwen3.8-flash", "step-3.7-flash", "step-3.5-flash-2603")`
(main.py:1833) — **qwen3.8-flash ÄR i free tier** ✓.

Tre ytor att synka:
- **login.html:410** `#update-banner` = "The Honest Dice v1.2" release-notis
  (localStorage `rn_12_seen`) → ersätt med: "✦ Qwen 3.8 Flash — now in the free tier.
  A fast DM mind that thinks, free for every account." + länk till releases + ny
  dismiss-nyckel (`qwen_flash_seen`).
- **adventure.html:835-841** `news-qwen38` banner säger fortfarande "Qwen 3.8 Max
  (full release)" med Patron-lås-text för free/tier1 → stale. Uppdatera till
  flash/free-tier-budskapet (ingen lås-text — den ÄR gratis).
- **chat.html:8247-8248** release-toast v1.3 nämner redan flash men som "new" →
  bumpa `RELEASE_TOAST_VERSION`, korta texten till free-tier-budskapet.

## 3. Kompakt login + mjukare onboarding (punkt 3)

**login.html gate:**
- gate-card idag: 2 fält + keep-logged-in + CTA + 3 toggle-rader + foot-text —
  gör kompakt: tightare padding, toggle-rader som en enda text-rad,
  gate-foot kortare. Behåll pitch-listan (den säljer) men trimma radhöjder.
- CTA-copy: behåll rösten, tydligare verb ("Enter the realm" som primär,
  "Foretell"-leken kan leva i gate-sub).

**adventure.html stepper (huvudgreppet):**
- step-model (adventure.html:1047-1091): visa ENDAST "Dungeon Master" som aktivt val.
  Guardian/Extraction/TTS → kollapsad "Advanced"-sektion med smarta defaults
  (Guardian+Extraction = qwen3.8-flash, TTS = Qwen). En rad: "You can change all of
  this later in Settings."
- Rekommendera qwen3.8-flash visuellt i DM-selecten (⭐ free tier-tagg).
- Progress-indikator: 4 prickar/steg (Language → Name → Adventurer → DM) så spelaren
  ser var i flödet den är — struktur som information.
- Kom ihåg val (lang, modeller) i localStorage → återvändare slipper välja om.

**Karaktärsarken (reveal-momentet):**
- Efter summon: renare karaktärskort — porträtt stort, namn/klass/HP tydlig hierarki,
  "Look them in the eye" → Continue/Reroll som enda val (ingen modellrad mitt i
  revelen; adventure.html:1042-1046 har `adv-char-model` inline i gen-row → flytta
  till Advanced).
- newgame.html samma treatment + fixa "Step one of three"-label och språk-default.

## 4. Turns-hover-popup (punkt 4)

Tooltip-texten är dessutom FAKTISKT FEL ("background calls count too" — guardian/
extraction/summaries är gratis interna anrop).

- **chat.html:1353** statisk `title` på `#rr-tally` → "Number of turns".
- **chat.html:2117-2123** `renderTurnTally()` bygger lång title varje tick →
  ersätt med kort: `Turns: X/Y left` (eller bara "Number of turns").
- **adventure.html:518** `.quota-tip` span: "Each DM, TTS, Image-gen and background
  llm-calls counts..." → "Number of turns".

## 5. Sidebar-avataren i chat (punkt 5)

chat.html `.pc-wrap` (CSS :203, HTML :1507-1509, render :2970-2988):
IDAG = två bilder samtidigt — `pc-avatar-bg` (helt kort som bakgrund, 256px, opacity .62,
gradient över) + `pc-avatar` miniatyr (128px) ovanpå → "miniatyr på renderad bild",
grötigt.

FIX: ett rent porträtt-behandling —
- Ta bort `pc-avatar-bg`-lagret (alt: behåll bg men ta bort miniatyren; audit-vågen
  väljer med screenshot-jämförelse, lutning: stor rundad porträtt som EGET element
  till vänster i kortet, stats till höger, ingen dubbelexponering).
- Behåll: klick→pickAvatar, hover-ring, "click to change"-affordance, has-bg-grensling städas.

## 6. Förstora avatarbilder (punkt 6)

Lightbox finns redan: chat.html `.av-lightbox` (:151-157, openAvatarLightbox :2923) +
character.html (:437-441). Saknas på:
- chat.html sidebar `pc-avatar` (klick = pickAvatar; lägg till: shift/ikon eller
  separat "🔍" → lightbox; alt. långtryck/hover-lupp — välj i implementation).
- chat.html `.msg-avatar` (player/dm/npc i chatten) → klick öppnar lightbox
  (pickAvatar flyttas till högerklick/liten ✎-knapp så klick inte krockar).
- characters.html (The Forge): `.pv-portrait` (:171, :461) och `.vcard-avatar` (:417)
  → klick = lightbox (saknas helt på sidan).
- adventure.html continue-panel/porträtt i onboarding-revelen → samma mönster.
Mål: EN delad lightbox-mönster (Esc stänger, pil-navigation där galleri finns,
samma guld-ram) på alla sidor.

## 7. frontend-design-skill-översyn (punkt 7)

Skill laddad (Anthropic). Tillämpas i audit + implementation:
- Typografi: Cinzel (display) / Spectral (body) / mono (data) — behåll, men se över
  skala/kontrast per sida (releases/mechanics är väggar av text).
- Struktur som information: stegnumrering i onboarding (verklig sekvens ✓),
  section-labels med I/II/✦ i newgame — konsekvent system.
- Copy-pass: knappar säger vad de gör (active voice), tomma states = inbjudan,
  felmeddelanden vägleder utan att be om ursäkt.
- Motion: befintliga rise/glow/ember-animationer — håll, respektera
  prefers-reduced-motion (finns redan på login, verifiera övriga sidor).
- Ett estetiskt risktag per yta max (Chanel-regeln) — onboarding-revelen är den givna.

## 8. Menystruktur (punkt 8)

**chat.html settings ⚙️ (:1371-1394)** — platt blandning idag. Gruppera:
- 🎮 Your game: How to Play · Feedback
- ⚙️ Settings: Models (DM/Lorekeeper/Extraction-kort) · Chat UI (CLI/bubbles) · About the Models
- 📊 Account: Usage · Export
- 🚪 Leave (röd, sist, separator)
**chat.html mobil-drawer (:1566-1571)**: spegla samma gruppering (Character · Engine
Room · Admin · Leave → grupperat).
**adventure.html gear-menu (:528-537)**: Release Notes/Profile/Upgrade/The Forge/Admin/
Log Out → gruppera: Account (Profile, Upgrade) · Realm (Release Notes, The Forge) ·
Admin · Log Out, med separators + konsekventa ikoner.
Topbar-ikonraden (📖 👑 🎵 🛠️ ⚙️) behålls — men 🔍-audit om 🛠️ Engine Room ska in i menyn.

---

## Utförande (subagent-vågor, max 3 parallellt)

**Våg 1 — Audit (2 subagenter, read-only):**
- A1: login/adventure/newgame/characters + onboarding-flödet → issue-lista mot punkterna 1,3,7.
- A2: chat/character/npcs/platser/loggbok/facts/help/mechanics/releases/pricing/models/
  reset/screenshots/book-souls → issue-lista mot 1,4,5,6,8.
- Output: markdown per sida, file:line, severity, fix-förslag. Screenshots där möjligt.

**Våg 2 — Implementation (3 subagenter, filkluster så inga två rör samma fil):**
- S1: login.html + adventure.html (banner, kompakt gate, stepper/advanced-kollaps,
  progress, quota-tip, gear-menu, localStorage-minne).
- S2: chat.html (rr-tally tooltip, pc-wrap avatar-redesign, msg-avatar lightbox,
  settings-menu gruppering, release-toast bump, mobil-drawer).
- S3: newgame.html + characters.html + character.html + övriga Codex-sidor
  (step-label, språk-default, lightbox i Forge, menykonsistens, copy-pass från audit).

**Våg 3 — Verify + deploy:**
- E2E i browser (ENDAST mainchat/test-konto — aldrig riktiga spelare), desktop 1440px
  + mobil 390px, alla ändrade sidor + hela onboarding-flödet registrera→starta kampanj.
- node --check på alla extraherade script-block; brace-balans på minifierad CSS;
  python HTML-validering; bump_versions.py / cache-bust (även CODEX_PAGES i chat.html).
- `docker compose build && docker compose up -d` (container = bake, inte volume!),
  verifiera live på dnd.rostad.cc med curl + browser.
- Uppdatera dnd-llm-skillen med nya patterns/pitfalls.

## Pitfalls som bakas in i varje subagent-kontext
- snes.css §1/§5 !important → nya regler EFTER snes.css-link; body-style-block vinner
  över head-block (cascade-ordning = filens ordning).
- TDZ: toppnivå-anrop som rör sena const/let → lägg i INITIERING-blocket sist.
- API.me() är LÅNGSAM — aldrig polla; utöka det enda load-anropet.
- Mobil topbar `overflow:hidden` klipper dropdowns → position:fixed-override ≤900px.
- Codex-iframe: embed.js döljer topbar; bumpa CODEX_PAGES `?v=`.
- Oavslutad `{` i minifierat style-block sväljer ALL CSS efter.
- Readability: title-attribut byts ut, inte bara CSS — kontrollera både statisk HTML
  och JS-satta titles.
- Konton: mainchat + nyskapat testkonto. ALDRIG robert/daddy/nomis/boblin/legendaryg.
