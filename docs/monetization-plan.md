# Monetiserings- & Android-publiceringsplan — The Lore Weaver's Cauldron (dnd.rostad.cc)

**Datum:** 2026-08-03 · **Status:** Fakta verifierade 2026-08-03 mot officiella källor (Google Play Help, developer.android.com, android-developers.googleblog.com, stripe.com, docs.stripe.com, swish.nu/bankerna, skatteverket.se, verksamt.se, ko-fi.com).  
**Gäller:** Hobbyprojekt i Stockholm, ingen registrerad firma, egen Docker-server bakom Cloudflare, FastAPI + vanilla JS, JWT-cookie-inloggning.

**Nuläge i koden (verifierat):** `backend/main.py` har redan `_turn_cap_for()` som läser `turn_cap` (0 = obegränsat) ur `backend/data/users.json`, samt `total_tokens`-spårning per användare/modell och `PLAYER_MODELS` (vilka LLM:er icke-admin-spelare får välja). Metering-infrastrukturen finns alltså på plats — det som saknas är ett `credits`-fält, daglig reset-logik och betalningsflödet. Live-sajten har i dag **ingen** `manifest.json`, `/.well-known/assetlinks.json` eller service worker (alla ger 404 — verifierat 2026-08-03), vilket krävs för TWA-vägen nedan.

---

## 1) Sammanfattning (rekommendation i 5 rader)

1. **Skippa Google Play Billing i lanseringen.** Gör Android-appen till en *consumption-only*-app: allt köp sker på webben (dnd.rostad.cc), appen innehåller inga länkar till kassan. Det är uttryckligen tillåtet enligt Googles Payments-policy och kostar **0 % till Google**.
2. **Primär prismodell: gratis-spel med daglig turn-cap (t.ex. 5 turer/dygn) + betalda turn-paket** köpta på webben. Intäkten matchar LLM-API-kostnaden 1:1; kräver bara ett `credits`-fält i users.json + en webhook-endpoint.
3. **Android: Trusted Web Activity (TWA) via Bubblewrap** — Googles officiella väg för PWA→Play. Rå WebView-wrapper riskerar avslag under *Minimum Functionality*-policyn.
4. **Starta betalningar utan företag: Ko-fi** (0 % plattformsavgift på tips) eller PayPal. När intäkterna blir verkliga (och omsättningen över ~30 000 kr/år): registrera **enskild firma + F-skatt** (gratis via verksamt.se) — det låser upp Stripe Payment Links och Swish Företag.
5. **Tidslinje till Play-lansering: ~6–8 veckor** — $25-konto + ID-verifiering, sedan **12 testare i 14 dagar** (obligatoriskt för nya personkonton), sedan granskning (räkna med 1–7 dagar).

---

## 2) APK-alternativ — hur webbappen blir en Android-app

### 2.1 De tre vägarna

| Alternativ | Insats | Passform för ditt spel | Play-acceptansrisk |
|---|---|---|---|
| **(a) TWA via Bubblewrap/PWABuilder** | Medel (1–3 dagar): `manifest.json` + ikoner + `assetlinks.json` på servern, sedan `bubblewrap` CLI → AAB. | **Bra.** Hela appen körs i Chrome: JWT-cookies, canvas och ljud fungerar oförändrat. Ingen adressrad, egen ikon/splash. | **Låg.** Detta är Googles dokumenterade, officiella väg (codelab + guide): https://developers.google.com/codelabs/pwa-in-play, https://developer.android.com/develop/ui/views/layout/webapps/guide-trusted-web-activities-version2, https://github.com/GoogleChromeLabs/bubblewrap |
| **(b) Rå WebView-wrapper** | Låg (timmar): minimal Android-app med WebView som laddar URL:en. | Sämre. JWT-cookies fungerar men kräver cookie-hantering (persistens, `setCookie`-tillstånd); canvas/ljud fungerar, men du får adressrad-beteenden och versioner av WebView som skiljer sig mellan enheter. | **Högre.** Google Play tillämpar *Spam and Minimum Functionality*-policyn: rena "webbläsare i en låda" utan app-specifik funktionalitet avvisas/avlistas (officiell kurs: https://playacademy.exceedlms.com/student/path/65190-comply-with-google-play-s-spam-and-minimum-functionality-policies; branschgenomgångar: https://code2native.com/blog/webview-app-google-play-approval-2026, https://nativine.com/blog/are-webview-apps-google-play-store-compliant-policy-guide). |
| **(c) Bara PWA utan store** | Ingen. Användare installerar via Chrome ("Lägg till på startskärmen"). | Fungerar redan i dag (efter att `manifest.json` + service worker lagts till). | Ingen granskning. Ingen Play-synlighet/uppdateringar. Bra fallback och för iOS-användare (som ändå inte kan installera din APK). |

**Rekommendation: (a) TWA via Bubblewrap.** Det är den enda vägen som ger äkta app-känsla *och* låg avslagsrisk. Bubblewrap läser web-manifestet och genererar ett Android-projekt (AAB) automatiskt. PWABuilder (https://www.pwabuilder.com) är ett GUI-alternativ som gör samma sak.

**Konkret att göra på servern (verifierat att det saknas i dag):**
- `manifest.json` (start_url, `display: standalone`, ikoner 192/512 px, theme color).
- `/.well-known/assetlinks.json` — Digital Asset Links som binder dnd.rostad.cc till paketnamnet (krav för TWA-verifiering).
- Enkel service worker (offline-fallback, bättre PWA-status).
- OBS: hela spelet ligger bakom JWT-inloggning — det påverkar inte TWA (full Chrome), men du måste lämna testinloggningsuppgifter till granskarna (App Access, se 3.3).

### 2.2 Insats-uppskattning

| Uppgift | Tid |
|---|---|
| manifest + ikoner + service worker | 2–4 h |
| assetlinks.json + Bubblewrap-bygge | 2–4 h |
| Lokaltest på Android (adb install, inloggning, canvas, ljud) | 2–4 h |
| Play Console-flöde (konto, formulär, tester) | 3–6 h utspritt över 2–3 veckor (14-dagars testkrav) |

---

## 3) Google Play-publicering — kraven 2025/2026

### 3.1 Konto
- **Engångsavgift $25** (ingen årsavgift), betalas med kort — PayPal accepteras inte. Officiellt: https://support.google.com/googleplay/android-developer/answer/6112435
- **Google-konto med 2FA** krävs, plus **identitetsverifiering** (officiell ID-handling m.m.) för alla nya utvecklare.
- **Personkonto räcker för hobby** — organisationskonto kräver företagsdokument + D-U-N-S-nummer och är onödigt i starten. Nackdelen med personkonto: testkravet nedan (organisationskonton är undantagna).
- **Testkrav för nya personkonton (verifierat, gäller fortfarande 2026):** "you must run a closed test for your app with a minimum of **12 testers who have been opted-in for at least the last 14 days continuously**" innan du kan ansöka om produktionsåtkomst. Officiellt: https://support.google.com/googleplay/android-developer/answer/14151465. Praktiskt: be spelare/Discord-vänner att opta in i den slutna testen i Play Console och *faktiskt* installera och använda appen.

### 3.2 Tekniska krav
- **AAB, inte APK** — Google kräver Android App Bundle för nya appar. Bubblewrap genererar AAB automatiskt.
- **Target API-nivå (verifierat på officiell sida 2026-08-03, https://developer.android.com/google/play/requirements/target-sdk):**
  - Från **31 aug 2026: nya appar och uppdateringar måste targeta Android 16 (API level 36)** eller högre (undantag: Wear OS/Automotive = API 35, TV/XR = API 34).
  - Befintliga appar måste targeta **Android 15 (API 35)** för att fortsätta vara tillgängliga för nya användare på nyare enheter; möjligt att ansöka om förlängning till 1 nov 2026.
  - Din tidslinje (~6–8 veckor) landar efter 31 aug → **sikta på targetSdk 36 direkt**. Bubblewrap sätter detta per aktuell nivå, men dubbelkolla.

### 3.3 Obligatoriska formulär & granskning
- **IARC-innehållsklassificering** (obligatorisk, ~5 min i Play Console). Ett textbaserat fantasy-RPG med "fantasy violence" hamnar typiskt runt **PEGI 7–12** (https://support.google.com/googleplay/android-developer/answer/9898843).
- **Data Safety-formuläret** (obligatoriskt): deklarera ärligt att appen samlar in konto-e-post, användarinnehåll (spelmeddelanden) och skickar dessa till en tredjeparts-LLM. Oärlig deklaration = vanligaste orsaken till avslag/borttagning (https://support.google.com/googleplay/android-developer/answer/10787469).
- **App Access:** eftersom hela spelet ligger bakom inloggning **måste** du lämna testinloggningsuppgifter i Play Console, annars stoppas granskningen (https://support.google.com/googleplay/android-developer/answer/10281818 — avsnittet om login credentials).
- **Privacy policy-länk** i store-listan — krav för alla appar som hanterar användardata.
- **AI-innehåll:** Googles policy för AI-genererat innehåll — deklarera där det är relevant (https://support.google.com/googleplay/android-developer/answer/16926792).
- **Granskningstid:** uppdateringar ofta timmar; nya appar typiskt 1–3 dagar, känsliga kategorier upp till 7; första appen från nytt personkonto kan ta längre. Budgetera en vecka (https://be-dev.pl/blog/eng/how-long-does-app-store-google-play-review-take-in-2025).

### 3.4 Vanliga avslagsorsaker för tunna web-wrapper-appar
- **"Webbplats i en låda"** — WebView utan mervärde → Spam/Minimum Functionality (se 2.1).
- **Saknad App Access / trasig inloggning för granskaren.**
- **Oärlig eller ofullständig Data Safety / saknad privacy policy.**
- **Betalkopplingar i appen utan Play Billing** — att länka till webbkassa inuti appen utan att vara med i EEA-external-offers-programmet är policybrott (se avsnitt 5).
- **Repetitivt/innehållsfattigt innehåll**, eller laddad med AI-genererat innehåll utan deklaration.
- **D&D-IP:** håll dig till **SRD 5.1 (CC-BY 4.0)** och eget material. Wizards' *Fan Content Policy* är icke-kommersiell — säljer du spelet får du inte använda varumärken/miljöer utanför SRD (t.ex. Forgotten Realms). "The Lore Weaver's Cauldron" + egen lore är fritt: https://dnd.wizards.com/resources/srd-and-license

---

## 4) Betalningar — Stripe, Swish och alternativen

### 4.1 Stripe (kräver enskild firma)
- **Krav (verifierat):** Stripe måste verifiera **företagsidentitet** (adress, webbplats, bankkonto) samt bedöma verksamhetens risk och tillåtna branscher: https://support.stripe.com/questions/business-information-requirements-to-use-stripe. För en svensk hobbyutvecklare betyder det i praktiken **enskild firma** (gratis att registrera hos Skatteverket via verksamt.se) — en ren privatperson utan företagsform kommer inte igenom verifieringen.
- **Avgifter Sverige, pay-as-you-go, ingen månadsavgift (verifierat, https://stripe.com/en-se/pricing):**
  - Standardkort inom EEA: **1,5 % + 1,80 kr** per transaktion.
  - UK-kort: 2,5 % + 1,80 kr · Internationella kort: 3,15 % + 1,80 kr (+2 % vid valutaomvandling).
- **Swish via Stripe (verifierat, https://docs.stripe.com/payments/swish):** Swish finns som Stripe-betalmetod men är i dag **"Private preview"** — du ansöker om åtkomst via e-post. Egenskaper: **endast SEK**, bara kunder i Sverige, **engångsbetalningar (inga prenumerationer)**, Stripe agerar "merchant of record" (Stripe står som mottagare i Swish-appen), återbetalning upp till 365 dagar. → Möjligt senare, inte en startpunkt.
- **Payment Links:** Stripe har färdiga betalningslänkar utan kod — idealiskt för "köp 100 turer" när enskild firma finns (https://stripe.com/en-se/payments/payment-links).

### 4.2 Swish direkt (Swish Företag / Swish Handel)
- **Swish Företag** (betala till nummer/QR): kräver svenskt bankkonto + **Swish-företagsavtal hos din bank**. **Enskild näringsidkare KAN få det** (verifierat, t.ex. https://www.swedbank.se/foretag/betala-och-ta-betalt/swish/swish-foretag.html: "Som enskild näringsidkare kan du ha både Swish som privatperson och Swish Företag"). En privatperson *utan* firma kan inte teckna det.
- **Swish Handel** (e-handel/betalning i webbshop eller app via Swish API): en separat, tyngre anslutning. Krav (verifierat hos bankerna): **avtal tecknas direkt med banken**, organisationnummer/företagsform, utsedda **certifikatsansvariga (CPOC)**, teknisk integration mot Swish API med ömsesidig autentisering (https://www.nordea.se/foretag/produkter/betala/swish-handel.html, https://danskebank.se/foretag/digitala-tjanster/digitala-tjanster/swish/swish-handel, https://www.swish.nu/foretag). För ett litet spel är detta överdimensionerat i starten.
- **Avgifter (bankberoende):** typiskt fast månadsavgift ~40–60 kr/mån + ~0,5–2 kr per transaktion (t.ex. https://www.handelsbanken.se/sv/foretag/konton-betalningar/ta-betalt/swish-for-foretag, https://www.bokio.se/blogg/swish-foretag-kostnad/).
- **Slutsats:** Swish är *den* svenska betalmetoden (>8 miljoner användare, https://www.swish.nu) och värd att lägga till när firman finns — men börja med Stripe Payment Links (Swish via Stripe när preview öppnas) eller Ko-fi.

### 4.3 Fungerar utan företag (dag ett)
- **Ko-fi (rekommenderad startpunkt):** gratis att skapa, **0 % plattformsavgift på tips**, **5 % på medlemskap/shop**; betalningsleverantörens avgift (~3 %) tillkommer. Utbetalning till PayPal/Stripe-konto, ingen företagsform krävs (https://ko-fi.com/pricing, https://help.ko-fi.com/hc/en-us/articles/360002506494-Does-Ko-fi-take-a-fee).
- **PayPal:** privatpersoner kan ta emot betalningar; svensk avgift cirka **2,9 % + fast del** per transaktion (https://www.paypal.com/se/digital-wallet/paypal-consumer-fees). OBS: PayPal kan frysa konton vid oklar företagsbakgrund/högre volymer.
- **Stripe Payment Links** — smidigast för turn-paket, men kräver enskild firma (4.1).
- **Donationer vs försäljning:** tips utan motprestation är inte momspliktiga; "köp turer" är en digital tjänst → momspliktig (se avsnitt 6).

### 4.4 Hur webhooken krediterar kontot (konkret design mot din kod)
Backend läser redan `users.json` via `_turn_cap_for()` (main.py rad 976–984: `turn_cap` = 0 betyder obegränsat). Så här kopplar du betalning → krediter:

1. **Datamodell:** lägg till `"credits": 0` (och valfritt `"subscription_tier"`) i varje användarobjekt i `users.json`. Krediter = betalda turer; gratis-taket = daglig reset av `turn_cap`-logik.
2. **Konsumtion:** i samma funktion som `_turn_cap_for` (eller där turn-spärren appliceras), dra `credits` först; när `credits` = 0, tillämpa dagliga gratisturer (`turn_cap`); `turn_cap = 0` + krediter kvar = obegränsat (befintlig betydelse).
3. **Webhook-endpoint:** ny route, t.ex. `POST /api/payments/webhook`, som tar emot händelsen från betalleverantören:
   - **Stripe:** verifiera signaturen med `stripe.Webhook.construct_event()` och webhook-secret (HMAC). Produkt-metadata (`turns`) avgör antal krediter.
   - **Ko-fi:** verifiera `X-Verify`-headern (SHA256 av body + din API-nyckel). Ko-fi skickar webhooks för donations/medlemskap.
   - **Idempotens:** spara varje händels-ID (t.ex. i en `processed_events`-lista/fil) så en webhook som levereras två gånger inte krediterar två gånger.
4. **Kreditering:** slå upp användaren via e-postadressen från betalaren (matcha mot `users.json`-användarnamn eller lagra e-post per användare), `user["credits"] += turns`, spara, logga.
5. **Enkel start utan webhook:** låt kunden få en **köpkod** på bekräftelsesidan som de anger i appen ("Lös in kod") — endpoint `POST /api/redeem` med engångskoder. Fungerar med Ko-fi direkt, ingen server-till-server-integration.
6. **Säkerhet:** kreditering får aldrig ske från klienten utan verifiering; håll webhook-secret i miljövariabel; rate-limita `redeem`.

---

## 5) Spelregler för Play Billing — vad är obligatoriskt, vad är tillåtet

### 5.1 Huvudregeln (verifierad ordagrant från Googles Payments-policy, https://support.google.com/googleplay/android-developer/answer/10281818)
Digitala varor/tjänster som säljs **inuti** en Play-distribuerad app **måste** använda Google Play Billing: "Digital items (such as virtual currencies, extra lives, additional playtime, add-on items, characters, or avatars)", "Subscription services", "App features". Fysiska varor/tjänster och 1:1-tjänster (t.ex. privat DM-session) omfattas inte.

### 5.2 Avgiftsstrukturen från 30 juni 2026 (verifierad: https://android-developers.googleblog.com/2026/06/play-expanded-billing.html, https://support.google.com/googleplay/android-developer/answer/16954621)
Sedan 2026-06-30 är avgiften delad i serviceavgift + billingavgift (USA, UK, EEA):

| Transaktion | Serviceavgift (första 1 MUSD/år) | Billingavgift (om Play Billing används, EEA) | Totalt |
|---|---|---|---|
| Engångsköp / prenumeration via Play Billing | 10 % | 5 % | **15 %** |
| Via webb-länk / alternativ billing (EEA external offers-programmet) | 10 % | – | **10 %** |
| **Consumption-only-app (inget säljs i appen)** | – | – | **0 %** |

Den gamla 30 %-siffran är alltså historia för dina volymer; Play Billing kostar 15 % under 1 MUSD/år.

### 5.3 Consumption-only — den lagliga vägen (verifierad)
Googles FAQ (samma officiella sida): *"Google Play allows any app to be consumption-only, even if it is part of a paid service. For example, a user could log in when the app opens and access content paid for somewhere else."* och *"developers may choose to provide additional information about purchasing options **without direct links**, including using language like: 'You can...' "*. Dessutom: *"We do not require parity across platforms"* — du får ha andra priser/funktioner på webben än i appen.

**Praktisk tolkning för dig:**
- ✅ **Tillåtet:** Appen visar texten "Köp fler turer på dnd.rostad.cc" **utan klickbar länk**; all betalning sker på webben; kontot (users.json) får krediter som förbrukas i appen. → 0 % Google-avgift, ingen Play Billing-integration.
- ✅ **Tillåtet från 30 juni 2026 (EEA):** anmäl dig till *billing choice / external offers*-programmet och länka EEA-användare till din egen webbkassa (10 % serviceavgift), under programmets UX-krav (https://support.google.com/googleplay/android-developer/answer/13821247).
- ❌ **Inte tillåtet:** klickbara betallänkar i appen utan att vara med i programmet; att sälja i appen via Play Billing och samtidigt erbjuda lägre pris på webben med länk i appen; "consumption-only" som egentligen är en betalmur för att kringgå avgiften (Google tolkar kringgående som policybrott).
- Tips/donationer där 100 % går till mottagaren och inget digitalt innehåll låses upp (inga badges) = peer-to-peer, kräver **inte** Play Billing.
- Om du senare vill sälja i appen: Play Billing Library v7+ (https://developer.android.com/google/play/billing) eller **Digital Goods API** för PWA/TWA utan native-kod (https://developers.google.com/chromeos/app-development/publish/pwa-play-billing).

---

## 6) Prismodeller — tre alternativ för en LLM-baserad hobbytjänst

Dina kostnader skalar med tokens (du spårar redan `total_tokens`), så priset bör knytas till förbrukning.

### Modell A — Gratis med daglig turn-cap + betalda turn-paket
- Gratis: **5 turer/dygn** (befintligt `turn_cap` + ny daglig reset-logik).
- Paket (webbköp): 100 turer ≈ 99 kr, 500 turer ≈ 349 kr, 1500 turer ≈ 899 kr — prissätt så att 100 turer ≈ LLM-tokenkostnad + 30–50 % marginal.
- **För:** intäkt = förbrukning 1:1; låg tröskel; perfekt med consumption-only-app + webbköp; minimal backendändring (`credits` + webhook).
- **Nackdel:** köpfriktion (köp → vänta på krediter); ingen förutsägbar månadsintäkt.

### Modell B — Månadsabonnemang med modell-gating
- T.ex. 89 kr/mån: obegränsat med grundmodell (turn_cap = 0) + högre cap på premium; 149 kr/mån: premium-LLM:er ("bättre DM") utan begränsning.
- Backend är redan redo: `PLAYER_MODELS` + `_clamp_player_model()` (main.py ~rad 998–1003) styr vilka modeller icke-admin-spelare får — lägg till `subscription_tier`-check där.
- **För:** förutsägbar intäkt; lägst avgiftsstruktur (15 % via Play Billing, 10 % via webb).
- **Nackdel:** kostnadsexplosionsrisk vid "obegränsat" — kräv hårda token-tak; churn; abonnemangshantering (Ko-fi-medlemskap eller Stripe Billing senare).

### Modell C — Engångsköp / "lifetime"
- T.ex. 499 kr en gång = obegränsat. Enklast möjliga UX, hög goodwill.
- **Nackdel:** **dålig passform för AI** — API-kostnaden löper för evigt efter en engångsintäkt. Avråds som huvudmodell.

### Rekommendation: **Modell A som fas 1, Modell B som fas 2**
1. **Fas 1:** gratis 5 turer/dygn + turn-paket via **Ko-fi** (0 % plattformsavgift på tips, ingen firma). Android-appen är consumption-only → 0 % Google-avgift. Webhook eller köpkod krediterar `users.json`.
2. **Fas 2 (när betalande användare finns):** registrera enskild firma + F-skatt → **Stripe Payment Links** (1,5 % + 1,80 kr EEA-kort) för turn-paket; lägg till månadsabonnemang (Modell B) via Stripe Billing; Swish via Stripe när preview öppnas, eller Swish Företag/Handel om efterfrågan finns.
3. **Fas 3 (om Play blir en stor kanal):** anmäl dig till EEA external offers (10 %) eller implementera Play Billing via Digital Goods API (15 %).

Motivering: Modell A täcker API-kostnaden direkt, kräver nästan ingen ny backend och håller dig utanför Play Billing-byrokratin så länge projektet är en hobby. För ett nischspel med få användare är förutsägbar kostnadstäckning viktigare än att maximera ARPU.

---

## 7) Juridik & skatt för en svensk hobbyist

### 7.1 Hobby vs enskild firma (verifierat hos Skatteverket, https://www.skatteverket.se/privat/skatter/arbeteochinkomst/inkomster/hobby.4.58d555751259e4d661680003940.html)
- **Hobby:** verksamhet utan vinstsyfte, inte din huvudsakliga försörjning. Överskott **deklareras och beskattas** (inkomst av tjänst) + **egenavgifter** på överskottet. Underskott får sparas och dras av mot kommande överskott (5 år).
- **Näringsverksamhet (enskild firma):** självständig, yrkesmässig, med vinstsyfte — den avgörande gränsen är **vinstsyfte** (samlad bedömning). När du aktivt säljer turn-paket med prissättning som ska täcka kostnader, närmar du dig snabbt näringsverksamhet.
- **Du kan inte vara godkänd för F-skatt för en hobbyverksamhet** (Skatteverket) — men du **kan behöva momsregistrera** om du bedriver ekonomisk verksamhet.

### 7.2 F-skatt och moms (verifierat, https://www.skatteverket.se/foretag/drivaforetag/startaochregistrera/fordigsomvillstartaforetag.4.6e8a1495181dad540842251.html)
- **Enskild firma:** ansökan om F-skatt, moms- och arbetsgivarregistrering sker kostnadsfritt via verksamt.se (BankID). F-skatt innebär att du själv betalar in preliminärskatt + egenavgifter.
- **Riktvärde för när F-skatt krävs:** nettoomsättning över ~30 000 kr/år (gängse vägledning via verksamt.se; kontrollera alltid aktuella regler — beloppsgränser ändras).
- **Moms:** du är **momsbefriad upp till 120 000 kr/år i omsättning** — tar då inte ut moms och får inte dra av ingående moms. Över 120 000 kr krävs momsregistrering (undantag finns, t.ex. om du köper momspliktiga tjänster utomlands). Digitala tjänster till privatkonsumenter har 25 % moms. För gränsöverskridande digital försäljning inom EU gäller OSS med tröskeln 10 000 €/år.
- **Konsekvens för planen:** under ~30 000 kr/år netto kan du i praktiken köra "hobby" (deklarera överskottet), men så fort betalningar blir systematiska bör du registrera enskild firma — det är gratis och låser upp Stripe/Swish Företag.

### 7.3 DAC7 — plattformsrapportering (verifierat)
- Sedan **1 januari 2023** är digitala plattformsoperatörer skyldiga att årligen rapportera säljare och deras intäkter till Skatteverket (Sveriges genomförande av EU:s DAC7-direktiv, lag 2022:1681, https://www.skatteverket.se/foretag/drivaforetag/startaochregistrera/digitalaplattformarlamnauppgifteromsaljareuthyrareochersattningar.4.7c708f0e16bed42cd0555d5.html).
- Det betyder att **Ko-fi, PayPal m.fl. kommer att rapportera dina intäkter** till Skatteverket och begära ditt personnummer/org.nummer — pengarna "syns" alltså automatiskt; du måste deklarera dem. (Patreon beskriver samma förfarande: https://support.patreon.com/hc/en-us/articles/21712170817293)
- **Stripe:** DAC7-rapportering gäller Stripe för dess *Connect-plattformar* (marketplace-kunder) — https://docs.stripe.com/connect/platform-tax-reporting. Som direkt Stripe-säljare blir du inte DAC7-rapporterad av Stripe, men Stripe genomför KYC-verifiering och lämnar årliga sammanställningar i Dashboard. Skatteverket får ändå uppgifterna via din moms-/inkomstdeklaration.

### 7.4 Praktiska slutsatser
- Börja med Ko-fi/PayPal som privatperson och deklarera överskottet ärligt (blankett T2/SKV 2051 för hobby, eller i näringsbilagan när firman finns).
- Registrera enskild firma + F-skatt (gratis) när försäljningen blir regelbunden eller närmar sig 30 000 kr/år — det låser upp Stripe och Swish Företag.
- Sätt upp en enkel bokföring (Skatteverket kräver underlag i 7 år).
- Håll D&D-innehållet inom SRD 5.1 (CC-BY 4.0) + eget material så snart du säljer (Fan Content Policy är icke-kommersiell).

---

## 8) Rekommendation + steg-för-steg roadmap

**Strategi:** Lanseringsvärdet av Play-butiken för ett nischspel med egen server är *måttlig* — de flesta spelare kommer via webben. Gör webben till primär kanal med Ko-fi-betalning först, och publicera TWA:n på Play som en bekvämlighet. Undvik Play Billing helt i fas 1.

**Checklista (ordnad):**

**Fas 0 — Webb/betalning (vecka 1–2)**
- [ ] Lägg till `credits`-fält per användare i users.json + dra credits i turn-logiken (bredvid `_turn_cap_for`).
- [ ] Daglig reset av gratisturer (ny `daily_turns_used` + datum; återanvänd `turn_cap`).
- [ ] Skapa Ko-fi-sida med fasta belopp för turn-paket; sätt upp webhook (eller köpkod-flöde) → `POST /api/payments/webhook` + idempotens.
- [ ] Räkna LLM-kostnaden per tur (du har `total_tokens` + modellpriser) och prissätt paketen med marginal.
- [ ] Privacy policy + användarvillkor på dnd.rostad.cc (krav även för Play).

**Fas 1 — PWA-grunden (vecka 2)**
- [ ] `manifest.json` + ikoner (192/512 px) + enkel service worker.
- [ ] `/.well-known/assetlinks.json` (Digital Asset Links).

**Fas 2 — Play (vecka 3–6)**
- [ ] Bygg AAB med Bubblewrap CLI (targetSdk **36** — API 36-kravet gäller från 2026-08-31).
- [ ] Lokaltest på fysisk enhet: inloggning, canvas, ljud, laddning.
- [ ] Play Console: 2FA → $25 → ID-verifiering → **personkonto**.
- [ ] Sluten test: rekrytera **12 testare i 14 dagar** → ansök om produktionsåtkomst.
- [ ] IARC-formulär (förväntad PEGI 7–12), Data Safety (deklarera LLM-dataöverföring), privacy policy-länk.
- [ ] App Access: lämna testinloggningsuppgifter.
- [ ] Kontrollera: **inga klickbara betallänkar i appen** (consumption-only: enbart text som "Köp på dnd.rostad.cc").
- [ ] Publicera; budgetera 1–7 dagar granskning.

**Fas 3 — Skala upp (när intäkter finns)**
- [ ] Registrera enskild firma + F-skatt hos Skatteverket (gratis, verksamt.se).
- [ ] Öppna Stripe (enskild firma) → Payment Links för turn-paket; ansök om Swish-access (private preview).
- [ ] Lägg till månadsabonnemang (Modell B) via Stripe Billing; gate:a `PLAYER_MODELS` per tier.
- [ ] Om Play blir stor kanal: EEA external offers-programmet (10 %) eller Play Billing via Digital Goods API (15 %).
- [ ] Dubbelkolla D&D-material: SRD 5.1/eget enbart.

---

## Källförteckning (verifierade 2026-08-03)

- Google Play — kontoregistrering, $25-avgift: https://support.google.com/googleplay/android-developer/answer/6112435
- Google Play — testkrav nya personkonton (12 testare/14 dagar): https://support.google.com/googleplay/android-developer/answer/14151465
- Google Play — Target API-krav (API 36 från 2026-08-31): https://developer.android.com/google/play/requirements/target-sdk
- Google Play — Payments policy (Play Billing, consumption-only, App Access, tips, 1:1): https://support.google.com/googleplay/android-developer/answer/10281818
- Google Play — avgiftsstruktur 2026 (service 10 % + billing 5 % EEA): https://support.google.com/googleplay/android-developer/answer/16954621
- Android Developers Blog — "Expanded billing choice and lower fees" (2026-06-24): https://android-developers.googleblog.com/2026/06/play-expanded-billing.html
- Google Play — IARC-klassificering: https://support.google.com/googleplay/android-developer/answer/9898843 · Data Safety: https://support.google.com/googleplay/android-developer/answer/10787469 · AI-innehåll: https://support.google.com/googleplay/android-developer/answer/16926792
- Spam & Minimum Functionality (officiell Play Academy-kurs): https://playacademy.exceedlms.com/student/path/65190-comply-with-google-play-s-spam-and-minimum-functionality-policies
- TWA/Bubblewrap: https://developer.android.com/develop/ui/views/layout/webapps/guide-trusted-web-activities-version2 · https://developers.google.com/codelabs/pwa-in-play · https://github.com/GoogleChromeLabs/bubblewrap · PWA+Play Billing: https://developers.google.com/chromeos/app-development/publish/pwa-play-billing
- Stripe — priser Sverige (1,5 % + 1,80 kr EEA): https://stripe.com/en-se/pricing
- Stripe — Swish (private preview, SEK, ingen recurring): https://docs.stripe.com/payments/swish
- Stripe — verifieringskrav: https://support.stripe.com/questions/business-information-requirements-to-use-stripe
- Stripe — Payment Links: https://stripe.com/en-se/payments/payment-links · Stripe — DAC7/Connect-rapportering: https://docs.stripe.com/connect/platform-tax-reporting
- Swish — Swish Företag för enskild näringsidkare: https://www.swedbank.se/foretag/betala-och-ta-betalt/swish/swish-foretag.html · Swish Handel: https://www.swish.nu/foretag, https://www.nordea.se/foretag/produkter/betala/swish-handel.html, https://danskebank.se/foretag/digitala-tjanster/digitala-tjanster/swish/swish-handel
- Swish-avgifter: https://www.handelsbanken.se/sv/foretag/konton-betalningar/ta-betalt/swish-for-foretag · https://www.bokio.se/blogg/swish-foretag-kostnad/
- Ko-fi — priser/avgifter: https://ko-fi.com/pricing · PayPal — avgifter: https://www.paypal.com/se/digital-wallet/paypal-consumer-fees
- Skatteverket — hobby: https://www.skatteverket.se/privat/skatter/arbeteochinkomst/inkomster/hobby.4.58d555751259e4d661680003940.html
- Skatteverket — starta företag, F-skatt/moms (momsbefriad ≤120 000 kr, F-skatt ej för hobby): https://www.skatteverket.se/foretag/drivaforetag/startaochregistrera/fordigsomvillstartaforetag.4.6e8a1495181dad540842251.html
- Skatteverket — F-/FA-skatt: https://www.skatteverket.se/foretag/drivaforetag/startaochregistrera/fochfaskatt.4.58d555751259e4d661680006355.html
- Skatteverket — DAC7/plattformsrapportering: https://www.skatteverket.se/foretag/drivaforetag/startaochregistrera/digitalaplattformarlamnauppgifteromsaljareuthyrareochersattningar.4.7c708f0e16bed42cd0555d5.html
- D&D-licenser: https://dnd.wizards.com/resources/srd-and-license
- Granskningstider: https://be-dev.pl/blog/eng/how-long-does-app-store-google-play-review-take-in-2025
