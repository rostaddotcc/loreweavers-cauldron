# AI Dungeon (Latitude) — Feature-Gap Research Report
**Prepared for:** Mörkrets Rike / The Lore Weaver's Cauldron (dnd.rostad.cc) — free-to-play AI-DM D&D 5e browser game
**Research date:** 2026-08-11 (live web research, Brave search + Scrapling extraction)
**Confidence tiers:** CONFIRMED = official aidungeon.com / help.aidungeon.com / latitude.io / press release / Wikipedia; REPORTED = Reddit snippets, third-party reviews, blogs (single-source claims flagged).

---

## A. Feature Inventory (AI Dungeon as of 2025–2026)

| # | Feature | Details | Source | Status |
|---|---------|---------|--------|--------|
| A1 | AI story models | Large model roster, deliberately **non-OpenAI** since the Frontier refresh. Current/known: Griffin (free, unlimited at basic speeds), Pegasus (Pathfinder), Mistral Large 2 (Pathfinder), 3 new models (Rise), 4 new text models (Forge), then Frontier (May 21 2026, "biggest model refresh ever") added **6 story models + 6 image models**: Fable (free tier; "Lunaris V1 Turbo" = Sao10k finetune of Llama 3, tuned for atmosphere), DeepSeek V4 Flash (first DeepSeek on free tier), Gemma 4 31B (first Google model), Equinox (Gryphe finetune of Gemma 4 31B, tuned for continuity/rule-following), plus Muse (12B), Wayfarer Small 2, Madness, Atlas, Raven; default free model "Dynamic Small" auto-rotates small models. Model picker UI per tier. | aidungeon.com/unchained, /pathfinder, /rise, /forge, /frontier; solidaitech.com (Frontier lineup); help.aidungeon.com/ai-model-differences; dungeonsdeep.ai | CONFIRMED (models exist) / REPORTED (exact lineup — single blog source, plausible & cross-checked with review) |
| A2 | Image generation | "See" action generates scene images mid-adventure; multiple image models (6 new at Frontier, more at Forge); monthly Credits (760/1650/2750/5200 by tier) spent on Premium/Ultra image quality or temporary extra context; free tier gets 0 credits. | help.aidungeon.com/memberships-benefits; aidungeon.com/frontier, /forge; aigearbase.com | CONFIRMED |
| A3 | Memory System | Two parts: **Auto Summarization** (compresses past story) + **Memory Bank** (condensed info packets; embedding/vector retrieval — tech adapted from Voyage). Free = 25 memory slots; Journey 100 / Legend 200 / Mythic 400 / Ultimate 800. Player complaint: auto-memories eat context tokens and are often poorly worded. | help.aidungeon.com/faq/the-memory-system, /memberships-benefits; reddit r/AIDungeon 1ivhg9n | CONFIRMED |
| A4 | Context construction | Context = story text + AI Instructions + Story Summary + Plot Essentials (formerly "Memory") + Author's Note + triggered Story Cards. Context limits by tier: free 4k, Journey 8k, Legend 16k, Mythic/Ultimate 32k tokens (doubled in Renaissance, doubled again in Aura). 1 credit/action can temporarily extend context on some models. | help.aidungeon.com/memberships-benefits, /faq/the-memory-system; aidungeon.com/renaissance, /aura | CONFIRMED |
| A5 | Story Cards (lore/world-building) | Keyword-triggered info cards auto-inserted into context; card generation improved in Pathfinder; created in World/Scenario editor. | help.aidungeon.com; aidungeon.com/pathfinder; imperialaitools.com | CONFIRMED |
| A6 | Worlds & Scenarios (publishing/sharing) | Scenario = starting template; drafts → Publish (rating + community-guideline review); large public community library (fantasy/sci-fi/romance/horror); Worlds hub for persistent world-building; unpublished content unmoderated, published content moderated. | help.aidungeon.com/faq/what-are-scenarios, /faq/my-stuff; dungeonsdeep.ai; ai-dungeon.fandom.com | CONFIRMED |
| A7 | Multiplayer | Online co-op + local pass-n-play; 8-digit join code; **only host needs premium** (guests inherit member benefits); host can kick/block; no hard player cap (4 suggested); players take alternating turns; third-person recommended to avoid the AI merging players. | help.aidungeon.com/faq/do-you-support-multiplayer; aidungeon.medium.com; reddit r/AIDungeon 1qw2mjc | CONFIRMED |
| A8 | Command modes | Do / Say / Story input modes; Say wraps input in quotes ("You say, …"). | help.aidungeon.com/the-say-mode; dungeonsdeep.ai | CONFIRMED |
| A9 | Voice / TTS | **Built-in TTS was REMOVED** (old thread: ~0.01% usage didn't justify $1,500/mo). No first-party narration voice today. Voyage (sister platform) does ship audio narration. | reddit r/AIDungeon rz1cvx; techcrunch.com (Voyage) | REPORTED (removal, old) / CONFIRMED (Voyage) |
| A10 | Content moderation | Account-level AI Safety Settings: Safe / Moderate / Mature (18+ gate); SCIM filter (sexual content involving minors) hard-block w/ "continue" override; site-wide moderation of published content; community guidelines; historical 2021 moderation crisis (false-positive flagging) still shapes reputation. | help.aidungeon.com/understanding-settings; en.wikipedia.org; toolify.ai; dungeonsdeep.ai | CONFIRMED |
| A11 | Monetization | Free **Wanderer** tier: unlimited actions on free models, 4k context, 25 memories, 0 credits. Paid: Journey $14.99 / Legend $29.99 / Mythic $49.99 / Ultimate $99.99/mo (Credits + memory slots); Shadow Tiers = extra-powerful models/context; 6- & 12-month discounts; Journey+Legend 1-week trial; **energy system retired June 2022 → ads → now ad-free** (Unchained); Rise added "Daily Premium Actions" for free players. | help.aidungeon.com/memberships-benefits; en.wikipedia.org; aidungeon.com/rise, /unchained; dungeonsdeep.ai | CONFIRMED |
| A12 | Platforms | Web (play.aidungeon.io), iOS, Android apps; Steam: paid one-time-purchase version launched Jul 28 2021, retired Mar 12 2024, then a **free Steam version** returned in the Unchained era. | weavai.app; en.wikipedia.org; aidungeon.com/unchained; resetera.com | CONFIRMED |
| A13 | UI / presentation | Phoenix = major interface redesign + beta environment; Saga = richer story presentation for long-running adventures; Context Viewer; model picker; mobile release channels. | aidungeon.com/phoenix, /saga; help.aidungeon.com/understanding-settings | CONFIRMED |
| A14 | Real TTRPG mechanics | **None.** No character sheets, no enforced dice rolls, no rules engine, no battle map — combat is narrated, not adjudicated (multiple third-party reviews flag this as the reason TTRPG players leave). | imperialaitools.com; dungeonsdeep.ai | REPORTED (third-party, consistent across sources) |
| A15 | Original adventures | Ember added first-party adventures (fantasy, post-apocalyptic, urban fantasy, superhero) + quick-start prompts. | aidungeon.com/ember | CONFIRMED |
| A16 | Scale & ownership | 2M+ MAU (2026, third-party); founded 2019 (GPT-2 → GPT-3 "Dragon"); Latitude raised backing incl. Google's AI Futures Fund & Midjourney (per single-source blog); Voyage announced as the "successor" direction. | weavai.app; en.wikipedia.org; solidaitech.com | REPORTED |
| A17 | Voyage (sister platform, Apr 21 2026) | AI-native RPG creation platform: describe world (regions, cities, quests, villains, mechanics) → AI generates the game/code; persistent unscripted worlds; share worlds; audio narration; built on proprietary "World Engine". Shows Latitude's strategic shift beyond AI Dungeon. | techcrunch.com 2026-04-21; businesswire.com; respawn.outlookindia.com | CONFIRMED |

### Sentiment snapshot (r/AIDungeon + reviews, 2025–2026)
**Praised:** unlimited free-tier play ("far more compelling than any of the competition" — reddit 1cb2vcd); total creative freedom ("you can do anything"); scenario building + discovery feed + interface ease vs SillyTavern (reddit 1ck0kfb); model variety and responsiveness to feedback; the new memory system direction (reddit 1cz1sc8).
**Complained about:** the AI forgetting crucial things & **narrating the player's own actions back** ("you do this / you realize that…") — reddit 17k23j6, hx14ab, 1p6nw89; story summary/Plot Essentials hijacking direction ("constantly rewriting it just to keep things on track", summaries taken too seriously — reddit 1kt3fnq, 1o84wpu); memory system eating tokens with malformed memories (1ivhg9n); repetitive loops ("this ai is boring now… loops on itself endlessly" — 1pu6uen); content-filter false positives (historical + current, 1od1lre, toolify.ai); mobile UI update lag (Kimola feedback report); multiplayer AI confusing players as one person (1ejn3as); **zero real D&D mechanics** (dungeonsdeep/imperial reviews).

---

## B. Gap Table vs Mörkrets Rike (dnd.rostad.cc)

Legend: THEY = AI Dungeon has it, we don't. WE = we have it, they don't. Effort = build effort for our small game (S/M/L). Impact = value for a small free chat-first D&D game (low/med/high). Only rows where direction ≠ BOTH/- are real gaps; "BOTH" rows show shared strengths.

| Feature | AI Dungeon | Mörkrets Rike | Gap | Effort | Impact |
|---|---|---|---|---|---|
| LLM DM w/ multiple selectable models (incl. free tiers) | Yes | Yes | BOTH | – | – |
| **Authoritative rules engine** (server dice, HP/gold/XP/items, combat rail, spell slots, rests, levels, death saves) | **No** — narrated combat only, no sheets/dice/map | Yes | **WE** | – | – |
| Parallel "Guardian" state-extraction LLM | No | Yes | **WE** | – | – |
| Persistent world truth (fact register, cross-session) | Partial — AI-assisted Memory Bank/Plot Essentials, lossy | Yes — fact ledger + NPC mini-ledgers | **WE** (we win on reliability) | – | – |
| Auto-summarization / memory compaction | Yes (Auto Summarization + Memory Bank) | No (manual/ledger only) | THEY | M | high |
| Keyword-triggered lore cards (Story Cards) | Yes | No (facts always-on, not trigger-based) | THEY | M | med |
| Scenario/world creation + public library | Yes (huge moat, but moderation burden) | No (fixed campaign) | THEY | L | med |
| Adventure/campaign sharing | Yes (publish scenarios) | No (only Hall of Adventurers gallery) | THEY | M | med |
| **Multiplayer** (co-op, join code, host-benefits) | Yes | No | THEY | L | high |
| In-scene image generation ("See" action) | Yes (credits-gated) | No (portraits/NPC art only) | THEY | M | med |
| **TTS narration** | **No** (removed; only Voyage has it) | **Yes** (free + premium voices) | **WE** | – | – |
| Procedural SFX / mood music | No | Yes (Web Audio, zero files) | **WE** | – | – |
| Chat ceremony / typewriter / colored NPC bubbles / CLI mode | No (plain chat, Do/Say/Story prefixes) | Yes | **WE** | – | – |
| D20 roll ceremony, initiative, combat rail | No | Yes | **WE** | – | – |
| Character art + public player gallery | Portraits? No gallery | Yes (AI-painted portraits, Hall of Adventurers flip-book) | **WE** | – | – |
| AI Safety settings (Safe/Moderate/Mature + filters) | Yes (heavy machinery) | No explicit settings (family-friendly default) | THEY | S | low |
| Native apps (iOS/Android) + Steam | Yes | No (responsive browser only) | THEY | L | med |
| Monetization tiers | Free unlimited + 5 paid tiers + credit economy + Shadow Tiers | Free 50 turns/day + single premium (coming) | THEY | M | high |
| Free-tier generosity | Unlimited free-model actions + Daily Premium Actions | 50 turns/day cap | THEY | S | high |
| Bilingual UI | English only | Swedish + English | **WE** | – | – |
| Model zoo (6+ curated story models) | Yes | Several (free tiers incl.) | THEY | S | med |
| Worlds/campaign persistence across sessions | Partial (memory system) | Yes (fact register, loggbok) | **WE** (on reliability) | – | – |

---

## C. Recommendations (anti-"AI slop" lens: substance over flash)

### Worth closing — build these (in rough priority order)

1. **Free-tier generosity: unlimited or higher free turn cap (S effort, high impact).** AI Dungeon's single most-praised feature in 2025–2026 is *unlimited free actions* (+ "Daily Premium Actions" for free players). Our 50 turns/day is the weakest retention lever vs both AI Dungeon and the rest of the market. Even a "daily premium action" pattern (1–2 premium-model actions/day for free players) would copy the best part of their Rise update without wrecking costs.
2. **Multiplayer / co-op sessions (L effort, high impact).** D&D's DNA is group play; AI Dungeon's multiplayer is crude (turn-based, join code, AI confuses players) and *we* already have the authoritative state layer that makes shared sessions actually work (shared fact register, shared combat rail). A minimal v1: host creates session, 8-char join code, alternating turns, shared ledger. This is the single biggest "grow the game" feature and nobody in the small-AI-DM niche does it well.
3. **Auto-summarization layered on the fact register (M effort, high impact).** Our ledger is *stronger* than their Memory Bank (structured, authoritative vs their lossy auto-summaries), but we lack automatic compaction of long chat history. Add a background summarizer that feeds the DM model without touching authoritative state — we keep the reliability win, they keep the context-loss complaints.
4. **Keyword-triggered lore injection ("Story Cards" light) (M effort, med impact).** Only for *player/world-authored* facts (NPC grudges, quest hooks, place lore from our ledger) — trigger snippets into context when the topic appears. This is substance, not flash: it directly serves the "choices matter / world remembers" promise. Avoid their trap of auto-generated cards that bloat context.
5. **Campaign/adventure sharing (M effort, med impact).** Not a public marketplace (see "not worth copying") but export/share-your-campaign links — "play my campaign" between friends, building on the Hall of Adventurers. Cheap social loop, no moderation burden.
6. **Scene images later, gated to premium (M effort, med impact).** Their "See" action is flash that burns credits. Only worth it as a premium perk once Stripe monetization is live; keep portraits-first (already ours) as the free identity.

### NOT worth copying (and why)

- **Scenario marketplace / public library (L effort).** Their biggest moat *and* biggest moderation/content-policy liability (ratings, guidelines, NSFW gray zones). For a small free game it would drown in curation and attract exactly the generic template content our anti-slop philosophy rejects. Friend-to-friend sharing (rec. 5) captures 80% of the value.
- **Five-tier subscription + credit economy + Shadow Tiers (M effort).** Over-engineered pricing that exists to pay for frontier model costs we don't have. Keep free + one premium tier. Simplicity is a brand asset here.
- **AI Safety settings matrix (Safe/Moderate/Mature, SCIM filters, 18+ gates) (S effort, low-med impact).** Only needed if you host mature content. A small family-friendly game should stay family-friendly and spend the saved effort on quality.
- **Native iOS/Android apps + Steam (L effort, low-med impact).** Huge maintenance surface for a solo dev; mobile-responsive web (already done) plus a PWA covers the real need. Their Steam history (launch → retire → relaunch free) shows even they struggle with storefront economics.
- **Voyage-style world builder / code-gen RPG platform (XL effort).** Entirely different product category; ignore as strategy, but *do* note their Memory System tech came from Voyage — borrowing *ideas* is fine.
- **The model zoo / "Dynamic Small" auto-rotating picker (S effort, med impact).** 6+ curated finetunes is a costly arms race; 2–4 well-chosen models (incl. free tiers) with an explicit picker is plenty and matches our transparency philosophy.
- **Mid-scene image generation as a free feature (M effort, high cost).** Flash over substance; keep gated to premium (rec. 6).

**Bottom line:** AI Dungeon's known weaknesses — no real rules, forgetful/agency-stealing narration, token-hogging auto-memory, filter drama — are exactly the pillars we already win on (authoritative state, fact register, chat ceremony, TTS+audio). The gaps actually worth closing are *social and retention* features (multiplayer, free-tier generosity, campaign sharing) plus *smarter memory* (auto-summarize + triggered lore), not their content marketplace, apps, or pricing machinery.

---

## D. Sources

**Official (CONFIRMED):**
- https://aidungeon.com/ · /updates · /frontier · /gauntlet · /saga · /rise · /aura · /forge · /unchained · /phoenix · /renaissance · /pathfinder · /ember (release-note milestone pages, retrieved 2026-08-11)
- https://help.aidungeon.com/memberships-benefits (tiers, credits, context, memory slots)
- https://help.aidungeon.com/faq/the-memory-system (Auto Summarization + Memory Bank)
- https://help.aidungeon.com/understanding-settings (AI Safety: Safe/Moderate/Mature, SCIM)
- https://help.aidungeon.com/faq/do-you-support-multiplayer (join code, host-benefits, kick/block)
- https://help.aidungeon.com/faq/what-are-scenarios · /faq/my-stuff (publishing flow)
- https://help.aidungeon.com/ai-model-differences (model list)
- https://help.aidungeon.com/the-say-mode (command modes)
- https://aidungeon.medium.com/ai-dungeon-multiplayer-is-out-84177419bf7a (multiplayer launch)
- https://latitude.io/news/forge-a-new-era-of-ai-models-in-ai-dungeon (Forge models)
- https://techcrunch.com/2026/04/21/voyage-is-an-ai-rpg-platform-for-creating-custom-gaming-worlds-with-ai-generated-npc-interactions/ (Voyage launch)
- https://www.businesswire.com/news/home/20260421658665/en/ (Voyage press release)

**Wikipedia / reference (CONFIRMED history):**
- https://en.wikipedia.org/wiki/AI_Dungeon (energy system → ads 2022, Steam launch/retirement, moderation history)

**Third-party reviews & blogs (REPORTED; used for pricing cross-check, model lineup, sentiment):**
- https://dungeonsdeep.ai/blog/ai-dungeon-review-2026 (free-tier limits, models incl. Equinox/Atlas/Raven, "no rules engine" verdict)
- https://www.solidaitech.com/2026/07/ai-dungeon-google-voyage-sequel.html (Frontier model lineup: Fable/Lunaris V1 Turbo, DeepSeek V4 Flash, Gemma 4 31B, Equinox/Gryphe; Google AI Futures Fund + Midjourney backing — single source)
- https://imperialaitools.com/tool/ai-dungeon/ ("no character sheets, enforced dice, or battle map"; community scenarios)
- https://weavai.app/blog/en/2026/04/23/ai-dungeon-review-2026-features-price-alternatives/ (2M+ MAU, web/iOS/Android)
- https://aigearbase.com/tool/ai-dungeon (image credits by tier)
- https://kimola.com/reports/mixed-reviews-latest-update-ai-dungeon-146558 (mobile UI lag complaints)
- https://www.resetera.com/threads/ai-dungeon-is-coming-to-steam-on-july-28th-one-time-purchase-no-ads.605091/ (Steam launch)
- https://steamdb.info/app/1519310/ (Steam app id)

**Reddit sentiment (REPORTED — snippets only, Reddit blocks scraping):**
- r/AIDungeon: 1cb2vcd (free tier praise), 1ck0kfb (interface/scenario praise), 1cz1sc8 (memory system), 17k23j6 + hx14ab + 1p6nw89 (forgetting/agency theft), 1kt3fnq + 1o84wpu (summary/Plot Essentials hijack), 1ivhg9n (memory eats tokens), 1pu6uen (loops/boring), 1ejn3as (multiplayer confusion), rz1cvx (TTS removed), 1qw2mjc (multiplayer tips), 1od1lre (filter relaxation), 1jsm56k + 1878usg (filter/model frustrations)

---
*Method note: Brave search (1 req/sec throttle) + Scrapling extraction via ~/.hermes/skills/research/web-research/scripts/search.py. Official help pages are Super.so/Notion — nav-heavy but body content extracted. ai-dungeon.fandom.com wiki is tiny (14 pages) and dated; Wikipedia + help.aidungeon.com used instead. Reddit extraction blocked → sentiment from search snippets only. Report written incrementally to this file.*
