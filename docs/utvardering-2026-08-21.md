# 🔮 Utvärdering — The Lore Weaver's Cauldron (Mörkrets Rike)
**2026-08-21 · Grundlig analys: mechanics, prompt system, frontend, arkitektur**

---

## Betyg överblick

| Område | Betyg | Kommentar |
|---|---|---|
| Mechanics-motor (Guardian) | **8/10** | Elegant pre/post-separation, server-authoritative dice |
| Prompt system (DM v28) | **8.5/10** | Mogent lagerpå-lager, bra anti-hallucination |
| Minne & kontext | **8.5/10** | Hierarkiskt + RAG + trådkarta — imponerande |
| Frontend design | **6/10** | Två skinn kvar, jank-problem kända men orättade |
| Kodstruktur | **6/10** | main.py 11 230 rader = monolit |
| Tester | **8.5/10** | 405 passerar, bra täckning av mekanik |

**Helhet: 7.5/10 — spelarmekaniken är i toppklass för ett LLM-spel; frontend och kodhälsa är eftersatta.**

---

## 1. MECHANICS — Guardian-systemet

### Styrkor
- **Pre/Post-separation är rätt arkitektur.** Pre-Guardian avgör om kast behövs (med DC, modifierare, FÖRDEL/NACKDEL, proficiency, darkvision-regler). Post-Guardian extraherar ~30 effektfält ur DM-prosan. DM:n skriver berättelse, koden äger siffrorna — det är exakt hur ett LLM-RPG ska byggas.
- **Server-authoritative dice** (Python `secrets`, POST /api/dice, klient fallback) — fusk- och race-säkert. Advantage löses som 2d20 på servern, klienten väljer bästa — bra mönster.
- **KONFLIKTDETEKTERING** i post-prompten (corrections för spelarpåhitt, dubblett-NPC, retractions) — få LLM-spel har detta.
- **Balance guardrails** i combat-prompten (max enemy HP/AC per nivå, max 3 fiender under lvl 3, always an escape route) — skyddar solospelaren.
- **Anti-dubbel-regeln** (rulla inte samma effekt två gånger när DM redan taggat) — visar att ni slagits med verkliga buggar.

### Svagheter
1. **Fiendeanfall: narrativ/kod-motsägelse.** DM-prompten säger *"state the roll in the narration: roll 16 vs AC 12 — hit!"* men post-prompten säger *"KODEN rullar tärningen… ignorera DM:s hit/miss"*. Resultat: DM:n narrerar ett utfall den inte bestämmer — spelaren kan se "roll 16 — hit!" i texten medan koden rullar en miss. Synlig inkonsekvens i stridsloggen. **Rekommendation:** låt koden injicera fienderesultatet som ett separat renderat stridsevent (som ni redan gör med tärningsceremonin) och ta bort "state the roll"-instruktionen ur DM-prompten.
2. **Post-Guardian är överbelastad.** ~30 JSON-fält + långa svenska exempel på en flash-modell (step-3.7-flash). Risk för fältdrift och hallucinerade extraktioner. **Rekommendation:** dela i två anrop (strid/föremål vs. berättelse/NPC/värld) eller använd provider-native structured outputs / function calling med JSON Schema — då kan en mindre modell klara jobbet billigare och stabilare.
3. **Post-prompten är svenska även i engelska kampanjer.** Pre har EN-variant, post har inte (exempel, regler och formatförklaringar på svenska medan narration är engelska). Fungerar, men flash-modeller driftar lättare. Översätt GUARDIAN_POST_SYSTEM som GUARDIAN_PRE_SYSTEM_EN.

---

## 2. PROMPT SYSTEM — DM v28

### Styrkor
- **Språk först + språk sist.** [SPRÅK]-direktivet öppnar och [SPRÅKPÅMINNELSE] avslutar systemprompten — rätt mot drift i långa transkript och reasoning-modeller.
- **TRUTH-block med compact_state** — naturligt-språks-sammanfattning istället för rå JSON sparar tokens och är lättare för modellen att respektera. Inventory, bärvikt, spell slots, darkvision, exhaustion — allt finns med. DM:n kan inte påstå att state saknas.
- **DM-triaden (say yes / say no / roll)** + [KAST:] FÖRE utfall som absolut regel — det är denna disciplin som får spelet att kännas som D&D och inte som en chattbot som låtsas.
- **STORYTELLING CRAFT-sektionen** (show don't tell, två sinnen per scen, implication > description) är ovanligt bra skriven — den ger prosan karaktär utan att blåsa upp längden.
- **Vaknandeprotokollet** (tur 1: frågor, tur 2: öppna scen med spelarens svar) — bästa onboarding jag sett i ett LLM-RPG; spelaren formar världen från första svaret.
- **Villkorad injektion:** combat-prompt endast vid fiender, narrative-prompt annars, dödsräddning endast vid 0 HP, Guardian-råd endast vid rekommenderat kast. Prompten växer bara när den behövs.
- **Aktiva trådar + [SÖK:]-verktyget** — DM:n tappar inte parallella storytrådar och kan själv hämta mer minne. Det är agent-arkitektur, inte bara en chattprompt.

### Svagheter
1. **Long-form-detektering via substring.** `"bok"`, `"läsa"`, `"sign"`, `"map"`, `"minne"` som delsträngar ger falska positives ("jag tittar på bokhyllan" → max_tokens 16000, långsam tur). Låg risk, men en liten whitelist av fraser + ordgränser (regex `\b`) fixar det.
2. **Prompten är stor i totalen.** Core (~200 rader) + combat/narrative + truth + trådar + platser + restidsregler + regelinjektion + Guardian-råd + språkpåminnelse + RAG-minne + 6 000-token transkriptfönster. Det fungerar, men mät faktisk systemprompt-storlek per tur och logga den — ni har ingen koll på om ni närmar sig context-taket på små modeller.
3. **Restidsregeln (avstånd ÷ 10 × terräng) injiceras varje tur** fast den bara behövs vid resor — samma villkorade mönster som combat skulle spara tokens.

---

## 3. MINNE & KONTEXTPERSISTENS

- **Hierarkisk sammanfattning (2 scen + 2 kapitel + 1 kampanjbåge) + token-budgeterat transkriptfönster (6 000 tok, min 8 meddelanden) + fact register + RAG + trådkarta** — detta är en riktigt vuxen minnesarkitektur. Bedömning: **8.5/10**.
- Svaghet: token-estimatet `len(content) // 3` är grovt (svenska ≈ 3.2–3.5 tecken/token, engelska ~4). Engelska kampanjer får ett kortare effektivt fönster än tänkt. Ett snabbt heuristikfix: `len // 3` för svenska, `len // 4` för engelska.

---

## 4. FRONTEND

### Läge
- **Två-skinn-problemet är fortfarande olöst** (audit 2026-08-11): login, mechanics, releases, pricing, models, screenshots, reset laddar inte snes.css — landningssidan ser ut som en annan produkt. index.html är en naken redirect-sida med gammal palett. Detta är det enskilt största varumärkesproblemet: första intrycket matchar inte spelet.
- **Prestanda-auditen är fortfarande aktuell:** embers-canvas 60 fps + shadowBlur på 11 sidor utan `document.hidden`-koll; typewriter med forced sync-layout varje tick; Guardian-poll hämtar hela transkriptet varje sekund; chat.html 479 KB (139 KB inline CSS + 306 KB inline JS) utan gzip/brotli; book-souls-bilder upp till 7.8 MB.
- **Tema-systemet (themes.js v31, server-persistens) och sprite/i18n-lagren är bra byggda** — men ~139 hårdkodade old-gold-värden i chat.html bryter temabyte partiellt på huvudsidan.

### Rekommendationer i ordning
1. Snitt: gzip/brotli + `visibilitychange`-pause för embers (två små fixes, stor effekt).
2. Konvertera de 7 legacy-sidorna till snes.css (ni har redan two-skin-playbooken i refs).
3. Byt ut rgba(232,198,90…)-hardcodes mot `color-mix(var(--gold)…)` i chat.html.
4. Långsiktigt: bryt ut chat.html-inline-JS till moduler + transcript virtualisering.

---

## 5. KODSTRUKTUR & KVALITET

- **main.py = 11 230 rader, 254 funktioner, 70 endpoints i en fil.** Det fungerar men varje ändring riskerar regressionsyta, och diffar blir oläsliga. **Rekommendation:** dela i APIRouters (auth, chat, combat, admin, billing, state) — prompterna kan bo kvar i models.py.
- **guardian.py 3 533 rader** är mest prompt-text — flytta prompterna till separata `.md`-filer som laddas vid start (versionshanterade, diffbara, redigerbara utan Python).
- **405 tester passerar på 68 s** — riktigt starkt för ett hobbyprojekt; täcker combat, tiers, spell slots, IP-block, billing. Detta är er försäkring inför varje refaktor.
- Modellsparken (13 modeller, dashscope/deepseek/mimo/stepfun/ollama) med per-anrops-kostnadsreservering (_reserve_chat_pipeline) är genomtänkt — bakgrundsanrop dör inte mitt i en turn.

---

## 6. SLUTOMDÖME

Detta är ett av de mest genomarbetade LLM-RPG-system jag sett ur **mekanik- och promptsynpunkt**: servern äger sanningen, DM:n äger berättelsen, Guardian översätter mellan dem, minnet är hierarkiskt och spelet lär sig av sina buggar (P2/P3-fixarna i prompterna vittnar om det).

Gapet är inte spelkänslan — det är **skrovet**: monoliten main.py, tvåskinn-frontenden och de kända prestandaproblemen. Inget av det hotar spelet idag, men allt three.js-arbete ni planerar för startsidan blir svårare om två-skinn och 479 KB-chat inte städas först.

**Top 5-prioritering:**
1. Fixa fiende-rull-motsägelsen (narrativ vs kod) — spelarupplevd korrekthet.
2. Gzip + embers visibility-pause — billigast, störst prestandavinst.
3. Konvertera 7 legacy-sidor till snes.css — varumärket.
4. Structured outputs för Guardian post — stabilitet + lägre kostnad.
5. Dela main.py i routers — före nästa stora feature (three.js-startsidan).
