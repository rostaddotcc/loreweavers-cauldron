I have everything needed. Here is the complete feasibility report.

---

# Feasibility Report: AI "Scene Videos" for the dnd-llm Cauldron

**Scope:** Read-only research. No files modified, no API calls made. All findings from `video-gen.py`, the `video-generation` skill, the dnd-llm codebase, and DashScope/Alibaba docs (web).

---

## 1. Video model availability on the Token Plan

**Confirmed working path (already proven on this machine):**
- **HappyHorse 1.1 T2V** — `model: "happyhorse-1.1-t2v"`, endpoint `https://token-plan.ap-southeast-1.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis` (async submit → poll `/api/v1/tasks/{id}` → download `video_url`). Auth: `Bearer ALIBABA_TOKEN_PLAN_API_KEY` (env or `~/.hermes/.env`). Params: `size` 1280*720 (only confirmed tier), `duration` 5 or 10. Latency ≈ **2 min for a 5s clip** (poll every 10s, hard timeout 10 min). Alibaba's AI Token Plan landing page explicitly lists "HappyHorse1.1" as a Token Plan model.
- **Cost (from skill, observed 2026-07-26):** video is the MOST expensive Token Plan operation — **720P ≈ $0.14/sec, 1080P ≈ $0.18/sec**; **5s ≈ ~40% of plan usage, 10s ≈ ~80%**. Billing formula (per DashScope docs): `unit price (resolution) × duration (seconds)`.

**"Wan text2video" question — Wan 2.7 T2V EXISTS:**
- Alibaba Cloud Model Studio (international DashScope) documents a **Wan 2.7 text-to-video API** with models **`wan2.7-t2v`** and **`wan2.7-t2v-2026-06-12`**, plus the family: `wan2.1-t2v-plus`, `wan2.1-t2v-turbo`, `wan2.2-t2v-plus`, `wan2.5-t2v-preview`, `wan2.6-t2v`, `wan2.6-t2v-us`.
- Crucially, its endpoint is **`https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis`** — the *same host pattern and the same async submit→poll API shape* as the Token Plan (which is itself `token-plan.ap-southeast-1.maas.aliyuncs.com`, i.e. just another workspace prefix). Wan 2.7 T2V is a strict superset feature-wise: 720P/1080P, ratios 16:9/9:16/1:1/4:3/3:4, duration 2–15s (default 5), plus `prompt_extend`, `negative_prompt`, `watermark`, and auto-dubbing/`audio_url`.
- **Caveat (unconfirmed):** whether the *Token Plan key* is authorized for `wan2.7-t2v` specifically is not documented anywhere I could verify without calling the API. It very likely is (Token Plan = "all-in-one access to Qwen + leading third-party models"; HappyHorse 1.1 is itself a third-party model on the plan), but the **only confirmed-on-this-plan model is `happyhorse-1.1-t2v`**. Mitigation: build with the model name configurable (`SCENE_VIDEO_MODEL`, default `happyhorse-1.1-t2v`); switching is a one-string config change, verified later with one live test submit.

**Bottom line:** Feasible today with HappyHorse 1.1; a real "Wan 2.7 T2V" brand exists and is the likely eventual target, pending a one-shot Token Plan probe.

---

## 2. Proposed integration architecture (mirrors the avatar pipeline)

The existing avatar flow is the exact template: `frontend/api.js → POST /api/campaign/avatar/generate {provider, prompt, seed} → _require_image_gen_tier → generate → save to backend/data/campaigns/{user}/{cid}/avatars/ → state["avatars"] registry → GET /api/campaign/avatar/{kind} serves it → campaign export zips the folder`.

**Backend (main.py):**
1. `POST /api/scene-video/generate` — body `{message_ts, duration: 5}` (message_ts = transcript entry timestamp; the DM reply text is looked up from the transcript server-side, so the client never passes raw text).
   - `_require_video_tier(username, payload)` — new gate (recommendation below).
   - Hard cap: `video_used_today` counter + `video_reset_date` in users.json, mirroring `_consume_wan_quota` exactly (limit 2/day); consume **1 turn** via `_gate_turn_quota`/`_consume_turn`.
   - Reject 409 if a generation for this user is already running (one at a time).
   - Return `{video_id, status: "pending"}` immediately; spawn `asyncio.create_task(_generate_scene_video(...))` registered in the existing `_RUNNING_BG` set (same pattern as `_guardian_post_dm`, ~line 4697).
2. `_generate_scene_video(...)` background task: build prompt (see §3) → submit to Token Plan → poll every 10s (max ~10 min) → download mp4 → save to `CAMPAIGNS_DIR/{user}/{cid}/videos/{video_id}.mp4` → update `state["videos"][video_id]` `{status: "ready", disk_name, prompt, duration, size, created, message_ts}` → `store.save(state)`. On FAILED/timeout: `status: "failed"` + message (user can retry).
3. `GET /api/scene-video/{video_id}/status` — reads `state["videos"]` (pending/generating/ready/failed + error msg).
4. `GET /api/campaign/video/{video_id}` — `FileResponse(mp4)`, auth-cookie-gated, `?download=1` variant sets `Content-Disposition: attachment`.
5. Ledger: `_add_video_gen(username, model)` mirroring `_add_image_gen` (line 2990) so admin's "Calls by provider" view shows `happyhorse-1.1-t2v`.
6. The key already exists server-side — the Wan image path (line 7715) already reads `DASHSCOPE_API_KEY or ALIBABA_TOKEN_PLAN_API_KEY`.

**Storage layout:**
- `backend/data/campaigns/{username}/{cid}/videos/{video_id}.mp4` (sibling of `avatars/`)
- Registry in `state["videos"]` (parallel to `state["avatars"]`); note `state["images"]` exists but is write-orphaned today — don't reuse it.

**Tier recommendation:** **tier2 (Patron 10€) or lifetime/admin only**, NOT tier1. Rationale: one 5s clip ≈ 40% of the *entire* Token Plan allowance — that's Patron-scale spend (Wan 2.7 image painting, which is ~10× cheaper per unit, is already tier2). Free/tier1 get 403 with the standard upgrade-hint message style. Add a strict **2 videos/day cap** + turn cost on top, and show a cost warning in the UI ("⚠ consumes ~40% of the Token Plan allowance").

**Frontend (chat.html + api.js):**
- `api.js`: `generateSceneVideo(messageTs, duration)` → `req('/api/scene-video/generate', POST)`, `sceneVideoStatus(id)`, `sceneVideoUrl(id)` (mirrors `API.avatarUrl`).
- In `buildMessage()` DM branch (~line 2825): add a small `🎬` button in the `dm-footer` area of each DM bubble. On click → POST → poll status every ~10s (toast "Rendering scene…") → when `ready`, inject `<video controls preload="metadata">` into the bubble below the text, plus a ⬇ download link. 403 → toast with upgrade hint (mirrors avatar gating UX).
- Batch-rendered transcript messages get the button too (they pass through `buildMessage`), so *past* DM replies are instantly video-able — this already satisfies most of the "pick which reply" requirement without a separate selector.

---

## 3. Building the video prompt from a DM reply — no extra LLM call

The DM reply *is* cinematic narration, so v1 uses a **template, zero extra LLM calls** (the DM call already happened; a second call would cost tokens + latency for marginal gain). Extract from state + reply text:

1. **Action** — first 1–2 sentences of the reply, stripped of markdown/quote/roll artifacts (`**bold**`, `[COMBAT:]`, dice `🎲`, NPC-citation markup). This carries the motion.
2. **Location** — `state.world.current_location` + first entry of `state.locations` (fallback: "a fantasy realm").
3. **Characters** — `state.character.name`, a `{race} {class}`; NPCs present in the reply text via the *same keyword match chat.html already implements* (`knownNpcIn()`, line 2698) — reuse that logic server-side.
4. **Mood** — cheap keyword classifier: dark/thunder/blood/storm → "gothic, candlelit, foreboding"; warm/dawn/inn → "golden hour, cozy"; etc. Default "dark cinematic fantasy".
5. **Style suffix** — fixed cinematic boilerplate per the skill: "cinematic, hyper-realistic, shallow depth of field, 4K film quality, slow deliberate camera movement, 16:9".

Template: `"{Location}. {Action}. {Characters}. {Mood}, {style suffix}"` → trim to ~300 chars (HappyHorse has no strict 512 limit like StepFun, but brevity = better video). **Justification for deferring an LLM call:** the DM reply is already model-generated prose; a template preserves the exact scene. *Later*, if quality disappoints, one cheap `step-3.7-flash` call (~200 tokens) to rewrite the template output is a 5-line change behind a flag.

---

## 4. Feasibility of each requested piece

| Piece | Verdict | Notes |
|---|---|---|
| (a) Inline player next to DM reply | ✅ Trivial | Native `<video controls preload="metadata">` inside the existing bubble; 720p 16:9 fits chat width; autoplay needs a user gesture (click-to-play is fine). |
| (b) Download button | ✅ Trivial | `<a href="/api/campaign/video/{id}?download=1">` with attachment `Content-Disposition`; same pattern as `exportCampaign`'s `window.open`. |
| (c) Videos in campaign export zip | ✅ Easy | Add one loop in `export_campaign` (line 7946 avatars block is the template): `bilagor/videos/*.mp4`. Watch total zip size (clips are ~5–20 MB each — see §5). |
| (d) Tier gate + login.html showcase | ✅ Easy / ⚠ one nuance | Gate = new `_require_video_tier`, copy of `_require_image_gen_tier` (line 8443) with tier2. **Nuance:** `login.html` is *unauthenticated*, so showcase clips cannot live behind `/api/campaign/video`. Place 2–3 curated clips in `frontend/assets/videos/` — the backend mounts `FRONTEND_DIR` at `/` via StaticFiles (line 10080), so they're publicly served for free, `<video muted loop autoplay>` in a showcase section (or a "Hall of Adventurers" style card row). Cost to produce: ~2–4 clips ≈ a few dollars of plan usage, one-time. |
| "Pick which reply" selector | ✅ Simple | Per-message 🎬 button (above) covers it without new UI. If a dedicated picker is wanted: the transcript endpoint already returns the last 100 messages with `ts` — a dropdown of recent DM replies → POST with chosen `message_ts`. No new backend needed. |

---

## 5. Cost / latency reality check + recommended MVP

**Reality check:**
- **Cost:** 5s @720p ≈ **$0.70 ≈ 40% of the whole Token Plan allowance** (10s ≈ 80%). This is *the* constraint — it dwarfs every other feature's spend (Wan image ≈ 1/10th). One careless user could drain the plan in 2–3 clips.
- **Latency:** ~2 min per clip (poll every 10s; worst case 10 min timeout). Users must be told it's async ("rendering… check back").
- **Size:** 5s 720p H.264 mp4 ≈ **5–20 MB** (estimate; no sample on disk to measure — verify on first real generation). Disk impact is small per user but grows; add a delete endpoint in a later phase.
- **Concurrency:** one active generation per user (409 otherwise); the plan itself also limits throughput.
- **Vendor risk:** Token Plan is prepaid; if quota depletes, submit returns an error — surface it as `status: "failed"` with a clear message, and consider a server-side plan-balance check (console, not API).

**Recommended MVP (build first):**
1. Backend: `POST /api/scene-video/generate` + status endpoint + video-serving endpoint; background submit→poll→download task; `state["videos"]` registry; storage under `videos/`; tier2+ gate; 2/day cap + 1 turn; `_add_video_gen` ledger; `happyhorse-1.1-t2v` / 720p / **5s only** (hardcode duration=5 — never 10).
2. Frontend: 🎬 button + inline player + download on every DM bubble (past + new); status polling; 403/error toasts.
3. Export: `bilagor/videos/` in campaign zip.
4. Cost warning in the UI before generating.

**Defer:**
- `wan2.7-t2v` switch (after one live probe of the Token Plan key); `prompt_extend`, `negative_prompt`, auto-dubbing.
- Optional LLM prompt-enhancer call (only if template results disappoint).
- login.html showcase (needs curated clips + manual asset copy; cheap one-time cost but not required for the feature to exist).
- Dedicated "pick a reply" dropdown (per-message buttons likely suffice); delete/cleanup endpoint; video-in-vault-export (vault is character portraits, not scenes — campaign export is the right home).

---

## Summary

- **What I did:** Read `~/.hermes/scripts/video-gen.py` + the `video-generation` skill; studied the dnd-llm avatar/image pipeline end-to-end (`main.py` tier gates, Wan image path, export endpoints, transcript/state formats, `chat.html` message builder, `api.js`, `login.html`); verified via web search + official Alibaba Model Studio docs whether a Wan-branded T2V model exists. **No files created or modified; no video API calls made.**
- **Key findings:** HappyHorse 1.1 T2V is confirmed on the Token Plan (~$0.14/s @720p, 5s ≈ 40% of plan, ~2 min latency). **Wan 2.7 T2V (`wan2.7-t2v`) genuinely exists** on Alibaba Model Studio with the same endpoint pattern/API shape — likely reachable via the Token Plan key but unconfirmed without a live probe. The feature is fully feasible by cloning the avatar pipeline: one new gated endpoint + background task + `videos/` storage + per-DM-bubble 🎬 button with inline player, download, and export-zip inclusion. Gate at **tier2+, hard cap 2/day, 5s/720p only**, template-based prompt with zero extra LLM calls.
- **Issues encountered:** `web_extract` backend unavailable (used curl for the Alibaba docs page); a grep pattern with `<` tripped a command blocklist (rewrote it); exact wan2.7-t2v-on-Token-Plan availability and real mp4 byte-size remain unverified (would require a paid API call — intentionally not done per task scope).