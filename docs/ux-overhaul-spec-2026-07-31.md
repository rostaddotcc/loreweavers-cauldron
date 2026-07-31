# 🎨 UX Overhaul Spec — Drawers + Kodex + Console + Free-text (2026-07-31)

Projekt: `~/dnd-llm`. Design: "Terminal Gothic v3" (Castlevania × DOS × terminal). snes.css = temat (vinner via !important). Tokens: --ink #08080d, --stone*, --edge*, --gold #c9a227, --blood #8b1a2a/#d43a4d, --bone*, --term-green #33cc33, --term-amber, --arcane #7b4fd4. Fonts: Cinzel (rubriker, uppercase, letter-spacing), Press Start 2P (retro-titlar), Spectral (body), VT323/monospace (terminal). Skarpa hörn (radius 0), scanlines, ingen glans.

Kontrakt mellan tre design-spår. UI-text är ENGLISH (språk-overhaulen pågår parallellt — skriv nya strängar på engelska; använd I18N.t('Svensk text') där det redan finns, annars direkt engelska).

## SPÅR D1 — chat.html + snes.css (ENDA chat.html + snes.css)

Filwhitelist: `frontend/chat.html`, `frontend/snes.css`. RÖR INTE backend, övriga sidor, api.js, i18n.js, sfx.js, sprites.js.

### D1.1 Karaktärsdrawer (Förslag A)
- Ny `#char-drawer` (fixed right drawer desktop / bottom-sheet ≤900px):
  - Desktop: höger drawer ~320px, glider in med transition, overlay-dimmer bakom (klick stänger)
  - Mobile: bottom-sheet, max-height 80vh, dra upp
- Trigger: klick på spelar-avatar/namn i chat-headern + en "Character"-knapp i topbar
- Innehåll (data via `API.getCampaign()` → `campaign._raw`):
  - Header: namn, klass/ras, nivå
  - HP-trough (befintlig `.hp-trough`-stil: blod-gradient, sheen, alarm <25%), temp-HP
  - XP-bar (befintlig), AC, Initiative, Perception
  - Ability-grid (STR/DEX/CON/INT/WIS/CHA med score+mod)
  - Aktiva resurser: `_raw.resources` (roll_grants: Bardic Inspiration etc.) — visa notation+label, tärningsknapp som anropar `rollDice`+ceremoni om möjligt
  - Spell slots (current/max)
  - Dödsräddningspips om HP 0 (💀 ●●○)
  - Inventory: klickbara item-kort (ÅTERANVÄND mönstret från character.html — kort med D&D-stats, klick → modal med detaljer; kopiera CSS/JS-mönstret, anpassa till drawer)
- Klasser: `.cd-*` (char-drawer) — unika namn, snes.css-safe

### D1.2 NPC-drawer
- Klick på NPC-namn/token i chatten eller sidebar-NPC → samma drawer visar NPC-kort
  - Namn, roll, relation (färg), ikon, levande/död, anteckningar
  - "@-nämn"-knapp: infogar `@Namn ` i inputen
- Lägg `data-npc` på NPC-meddelanden om det inte finns; klick-handler

### D1.3 Kodexen (Förslag B) — nav-förenkling
- Ny `#codex-modal` (fullscreen overlay, dark):
  - Tabs: 🧙 Character · 🧝 NPCs · 🗺 Map · 📖 Journal · 📌 Facts
  - Implementation: **iframe per tab** — `<iframe src="character.html">` osv (samma origin, sessionStorage-auth funkar). Border 0, background --ink, höjd fyller modalen, inre scroll. Aktiv tab = bara den iframen synlig (display toggle).
  - Lazy-load: skapa iframe först när tab aktiveras första gången
  - "Open full page ↗"-länk per tab (öppnar sidan standalone i ny flik)
  - Header: "📖 KODEX" (Cinzel, guld) + stäng ✕ + tabbar
- Sidebar/topbar-förenkling:
  - Desktop sidebar: ersätt de 5 sidlänkarna (Karaktär/NPCs/Karta/Loggbok/Fakta) med EN "📖 Kodex"-knapp som öppnar modalen
  - Behåll: Ljud (♫), Modell, Maskinrummet (🛠), Lämna
  - Mobile-drawer: samma förenkling
- Om en sidebarlänk till en sida behöver finnas kvar (t.ex. i mobile), lägg den i Kodexen

### D1.4 Maskinrummet-restyle (matcha api.js debug-panelen)
- Befintlig `.console` (full-höjd slide-in med gradient+scanlines+glow) → **ren, platt, minimal**:
  - Bottom-right panel (som api.js `#debug-panel`): width ~420px, max-height 45vh, fast position, border 1px, **flat background #0a0a12**, INGEN gradient, INGA scanlines, INGEN glow/text-shadow
  - Header: enkel rad — titel "🛠️ Debug" + count + knappar (Rensa, ✕) — platta, små, diskreta
  - Logg-rader: enkel monospace (VT323 eller monospace), tid + nivå + meddelande, färgkodade nivåer (INFO=grön, WARNING=amber, ERROR=blod, DEBUG=dim) — men INGA animationer (clog-in bort), ingen border-bottom? Håll det nära api.js-stilen
  - Behåll level-filtren (Alla/Debug/Info/Warn+) men styla dem platt som api.js-knapparna
  - Ta bort `.console::after` scanlines, `.console-title .pulse` glow (eller gör diskret)
  - Beteende: öppnas som overlay-panel (inte width-transition) — enkel show/hide
- ALLA klasser under `.console*` uppdateras i chat.html + snes.css

### D1.5 Övrig chat-polish
- Tomma states med vägledning (t.ex. ingen inventory ännu: "No belongings yet — the world will provide…")
- Se till att drawers/kodex är touch-vänliga (44px targets, :active)
- Inga placeholder-funktioner — allt ska fungera

### Verifiering D1
```bash
cd ~/dnd-llm/frontend && python3 -c "
import re
html = open('chat.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/chat_inline.js','w').write('\n;\n'.join(scripts))
" && node --check /tmp/chat_inline.js && echo "JS OK"
grep -c "char-drawer" chat.html        # >= 3
grep -c "codex-modal" chat.html        # >= 2
grep -c "iframe" chat.html             # >= 1
grep -c "console" snes.css             # uppdaterad
```

## SPÅR D2 — newgame.html fritext-mallen

Filwhitelist: `frontend/newgame.html` (ENDAST). RÖR INTE övriga filer.

### D2.1 Fritext-mall (markdown-liknande)
- Befintlig `<textarea id="prompt">` (den "fria legenden") → ersätt med en **mall-styrd fritext**:
  - Textarea förfylld med en strukturerad mall (MD-inspirerad, SV/EN beroende på vald lang-pill):
    ```
    ## Legend

    **Name:**
    **Race:**
    **Class:**
    **Backstory:**
    **Personality:**
    **A memory that haunts you:**
    **What do you seek?**
    ```
    (SV-varianten: **Namn:**, **Folk:**, **Klass:**, **Bakgrund:**, **Personlighet:**, **Ett minne som jagar dig:**, **Vad söker du?**)
  - "Clear"-knapp (🗑) som tömmer till tom textarea
  - Mallen följer `onLangChange` — byt mall när pill växlas (bevara det spelaren redan skrivit om möjligt, annars byt helt)
- **Live MD-förhandsvisning** under textarean: rendera det spelaren skriver som markdown (headings, **bold**, *italic*, - listor) i en `.legend-preview`-ruta (stone-bg, edge-border, samma font som chatten). Om tom: visa mall-förhandsvisningen.
  - Skriv en MINIMAL markdown-renderare (escape HTML → headings → bold → italic → lists → newlines). Återanvänd gärna mönstret från chat.html `mdToHtml` om det är enkelt att kopiera.
- Layout: textarea + preview sida vid sida desktop (grid 1fr 1fr), staplade mobile
- Stil: `.lp-*`-klasser (legend-preview), snes.css-safe, border-radius 0

### Verifiering D2
```bash
cd ~/dnd-llm/frontend && python3 -c "
import re
html = open('newgame.html').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/newgame_inline.js','w').write('\n;\n'.join(scripts))
" && node --check /tmp/newgame_inline.js && echo "JS OK"
grep -c "legend-preview" newgame.html   # >= 2
```

## SPÅR D3 — sekundära sidor polish + konsistens

Filwhitelist: `frontend/adventure.html`, `frontend/character.html`, `frontend/npcs.html`, `frontend/platser.html`, `frontend/loggbok.html`, `frontend/facts.html`, `frontend/admin.html`. RÖR INTE chat.html, newgame.html, api.js, i18n.js.

### D3.1 Konsistens & polish
- Varje sekundär sida: kontrollera att header/nav är konsekvent (samma knappar/stil); om en sida har egen nav med sidlänkar → behåll men lägg till "← Back to game" (till chat.html)
- Tomma states: `character.html` (ingen inventory: "Your pack is empty…"), `npcs.html` ("No souls met yet — the world awaits…"), `loggbok.html` ("No journal entries yet…"), `facts.html` ("No truths recorded yet…"), `platser.html` (kart-teckenförklaring)
- `adventure.html` (Vägskälet): se över "Så spelar du"-onepagern — säkerställ att den är hopfällbar och snygg; om den innehåller svenska som inte översatts av L-spåren, rapportera
- Knappar/CTA: konsekventa, touch-vänliga, inga placeholder-funktioner
- Alla nya klasser: unika, snes.css-safe

### Verifiering D3
```bash
cd ~/dnd-llm/frontend && for f in adventure character npcs platser loggbok facts admin; do python3 -c "import re; s=re.findall(r'<script>(.*?)</script>', open('$f.html').read(), re.DOTALL); open('/tmp/js_$f.js','w').write('\n;\n'.join(s))"; node --check /tmp/js_$f.js || echo "JS FAIL $f"; done
```

## ALLMÄNNA REGLER
1. Bryt inte fungerande funktioner. `node --check` måste klara. Backend rörs INTE.
2. Design-tokens: inga nya färger; Cinzel bara för rubriker; radius 0; platt.
3. Spara med write_file/patch — inte heredoc.
4. Verifiera med kommandona ovan innan du rapporterar klart.
5. Rapportera: exakt vad du ändrade + kvar för människan.
