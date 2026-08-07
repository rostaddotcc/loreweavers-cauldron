# TTS Realtime Research — `qwen-audio-3.0-realtime-plus` on the Alibaba Token Plan

**Date:** 2026-08-06 · **Author:** research subagent · **Status:** verified by live API tests
**Scope:** What the model is, Token Plan availability, latency/quality comparison vs. current game TTS (Qwen REST + StepFun), and a concrete streaming-integration recommendation for The Lore Weaver's Cauldron (~/dnd-llm).

---

## TL;DR

- `qwen-audio-3.0-realtime-plus` is **NOT a TTS model**. It is an **end-to-end real-time voice *dialogue* model** (full-duplex WebSocket speech-to-speech), per official Alibaba docs ("a real-time voice dialogue model (not a speech synthesis model)"). It **can** synthesize speech — including from plain text input — which is what matters for the game.
- It is **listed on the Token Plan** (`/v1/models`, verified 2026-08-06) and — unlike every other audio path tried so far — the **WebSocket realtime route on the Token Plan host WORKS**: `wss://token-plan.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen-audio-3.0-realtime-plus`.
- **Measured time-to-first-audio: ~1.3–1.7 s** (warm connection), regardless of text length (tested 100 → 1,548 chars). The current REST whole-file path takes **~2.9 s for 100 chars and roughly a minute for long DM replies** (sequential segment synthesis).
- Output is **PCM 24 kHz 16-bit mono only** (no MP3/Opus on this route) — the backend must transcode or the frontend must use WebAudio.
- The two narrator voices the game already uses (`longanlingxin` female, `longanlufeng` male) **exist on the realtime model** — voice parity.
- **Recommendation: yes, integrate** — it would cut perceived TTS latency from up to ~1 min to ~1.5–2 s first audio. Moderate effort (~2–4 dev-days), medium risk (Token Plan WS stability, PCM-only output, unverified Swedish quality, unknown credit burn).

---

## 1. What is this model, actually?

**Official answer (Alibaba Cloud Model Studio docs, help.aliyun.com / alibabacloud.com):**

- Model Studio doc "Qwen-Audio real-time voice model": *"Qwen-Audio is an end-to-end real-time voice interaction model that uses the WebSocket streaming protocol for low-latency voice conversations. Use cases include voice assistants, intelligent customer service, and AI companions."* It is a **full-duplex speech-to-speech / voice-dialogue model** (audio in → speech + text out), event-driven, OpenAI-Realtime-style API (`session.update`, `input_audio_buffer.append`, `response.create`, `response.audio.delta`, `response.done`).
- Voice cloning doc is explicit: *"Qwen-Audio-Realtime is a real-time voice dialogue model (**not a speech synthesis model**). Voice cloning is used to customize the TTS voice of the dialogue model's responses."*
- The Model Studio model index categorizes it under **Speech-to-speech** ("End-to-end voice conversation without separate ASR and TTS calls").
- So: **neither a pure TTS model nor a pure ASR model — it is the full realtime voice pipeline.** The dedicated TTS models are the separate `qwen-audio-3.0-tts-flash/plus` (what the game uses today, REST) and `qwen3-tts-*-realtime` (WebSocket TTS, not on Token Plan).
- It does accept **text-only input → spoken audio output** (documented `conversation.item.create` with `input_text` content), which is the mode relevant to the game.

**Key official specs (qwen-audio-realtime-user-guides):**

| Property | Value |
|---|---|
| Protocol | WebSocket full-duplex (`/api-ws/v1/realtime`) |
| Input audio | PCM 16 kHz, 16-bit, mono |
| Output audio | **PCM 24 kHz, 16-bit, mono only** (`output_audio_format: "pcm"`) |
| Context | 50 turns / 300 s cumulative audio max |
| Interaction modes | server_vad, smart_turn, manual (push-to-talk) |
| Function calling | Yes |
| System voices | `longanqian`, `longanlingxin`, `longanlingxi`, `longanxiaoxin`, `longanlufeng` |
| Voice cloning | Yes (Beijing region only per docs) |
| Documented regions | China (Beijing) only for this model ID (Singapore WS URL exists for `qwen3.5-omni-plus-realtime`, not for this ID) |

**Voices / languages:** the realtime system voices overlap the TTS voice list; `longanlingxin` and `longanlufeng` are documented as **Chinese (Mandarin) + English**. **Swedish is not in any official voice list.** (See §4 — it still synthesizes Swedish text without erroring, but pronunciation quality is unverified.)

---

## 2. Availability on the Token Plan — live test results (2026-08-06)

Key used: `DASHSCOPE_API_KEY` from `~/dnd-llm/backend/.env` (sk-sp-…, Token Plan).

### 2.1 Model listing
`GET https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/models` → 11 models, including **`qwen-audio-3.0-realtime-plus`** and `qwen-audio-3.0-tts-plus`. (Listed ≠ callable — see below.)

### 2.2 REST path — NOT callable (expected failure mode confirmed)
`POST /api/v1/services/audio/tts/SpeechSynthesizer` with `{"model":"qwen-audio-3.0-realtime-plus", "input":{text, voice:"longanqian", format:"mp3", sample_rate:24000}}` →
```
400 InvalidParameter: "url error, please check url! ...error-code#error-url"
```
Same signature as the known Token Plan proxy failure for audio models (multimodal-generation, chat-with-audio). The Token Plan proxy does **not** route this model over REST.

### 2.3 WebSocket path — WORKS (verified end-to-end)
```
wss://token-plan.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen-audio-3.0-realtime-plus
Authorization: Bearer <sk-sp-…>
```
- Connect → `session.created` received **~4 ms** after handshake.
- `session.update` (modalities `["text","audio"]`, voice) → OK. ⚠️ `["audio"]` alone is rejected: `invalid_value "modalities must include 'text'"`.
- Text→speech (documented `conversation.item.create` with `input_text`, then `response.create`) → **`response.audio.delta` streams base64 PCM**, ends with `response.done`. Verified in one live session.

### 2.4 Measured latency benchmark (Token Plan, 2026-08-06, warm connection)

| Test | First audio delta | Audio received | Result |
|---|---|---|---|
| EN ~100 chars (`longanlingxi`) | **1,264 ms** | 318,720 B PCM ≈ 6.6 s | done, no error |
| SV ~100 chars | **1,277 ms** | 326,400 B ≈ 6.8 s | done, no error |
| **SV 1,548 chars (long DM-style)** | **1,743 ms** | 528,100 B ≈ 11.0 s | done, no error; full stream delivered in ~4 s wall time |

First-chunk latency is essentially **independent of text length** — the streaming win scales with reply size.
Baseline for comparison — current REST path (`qwen-audio-3.0-tts-plus`, voice `longanlingxin`, ~100 chars): **2.9 s total** (synth+OSS URL 2.1 s + MP3 download 0.8 s), 106,651 B MP3. Long replies (1,500+ chars) are split into segments synthesized **sequentially** → 30–60 s before any audio plays (matches the reported UX problem).

### 2.5 Quirks found
- REST `qwen-audio-3.0-tts-plus` **rejects flash-tier voices** (`longanlingxi` → `400 [cosyvoice:] Engine error [411]: TTS speak operation failed`). The game already uses the correct plus voices (`longanlingxin`, `longanlufeng`).
- On the realtime WS, modalities must include `"text"` even for audio-only output; in tests the model emitted **no `response.text.delta`** events (audio only) — harmless for TTS use.
- The old dashscope-SDK WS TTS route (`/api-ws/v1/inference`) is still presumed dead (23 s hang, as documented in main.py). The `/api-ws/v1/realtime` path is a different proxy route and is the one that works.

---

## 3. Pricing

**Token Plan:** credits are consumed dynamically per request; **no per-model table is published**, and there is no official published price for `qwen-audio-3.0-realtime-plus` in the docs I could access. The only way to know the burn rate is to measure credits before/after a few calls. Flag this as the main financial unknown.

**PAYG list prices (for context, secondary sources — not confirmed in official docs):**
- `qwen-audio-3.0-tts-plus` (TTS): ~$27.59 / 1M chars (digitalapplied citing Alibaba's listed price; OpenRouter mirrors $20/1M). Current game cost for a ~10 s narrator line is therefore sub-cent.
- Realtime dialogue models are billed per token (~427 tokens ≈ 1 min of audio; e.g. `qwen3-omni-flash-realtime` ≈ $0.52 in / $1.99 out per M tokens → ~$0.0009 per 10 s of output audio on PAYG — negligible). These numbers are for the omni-realtime family, **not** this exact model ID; expect similar order of magnitude but verify.

Bottom line: cost is unlikely to be a blocker, but the Token Plan credit burn for the realtime model is **unmeasured**.

---

## 4. Comparison vs. what the game uses today

| | **Qwen TTS today** (Patron) | **StepFun TTS** (Support) | **qwen-audio-3.0-realtime-plus** (candidate) |
|---|---|---|---|
| Model / route | `qwen-audio-3.0-tts-plus` REST `/SpeechSynthesizer` → signed OSS URL → MP3 download | `stepaudio-2.5-tts` REST `/step_plan/v1/audio/speech` | WS `/api-ws/v1/realtime` on Token Plan host |
| First audio | whole file only; ~2.9 s @100 chars, **~30–60 s long replies** | whole file only | **~1.3–1.7 s regardless of length** |
| Output format | MP3 24 kHz | MP3 | PCM 24 kHz (must transcode/WAV-wrap or WebAudio) |
| Narrator voices | `longanlingxin` (F), `longanlufeng` (M) — zh+en | StepFun official voices | **same two voices available** (longanlingxin/longanlufeng) |
| Swedish | not official; works de facto | not official | not official; synthesized SV text without error in test |
| Instruction/style control | yes (`instruction` param) | yes | yes (system prompt + instruction-style session config; untested for style) |
| Cost | credits (dynamic) | credits (dynamic) | credits (dynamic, unmeasured) |
| Status | **works in production** | works in production | **works via WS (verified today)**, REST dead |

**Quality note:** the realtime model is a dialogue model — its voice quality is designed for conversation, not audiobook narration. Whether `longanlingxin` on the realtime model sounds as good as on the TTS-plus model is **unverified** (I could not listen to output; only byte counts and error-free completion were confirmed). The dedicated TTS models (flash/plus) remain the quality-first choice; the realtime model's selling point is latency, not audio quality.

---

## 5. Recommendation: integrate streaming TTS — YES, with caveats

### 5.1 Verdict
Integrating the **realtime WebSocket route as a streaming TTS path for Patron tier** would cut perceived TTS latency from up to ~1 min to **~1.5–2 s first audio**, with the rest of the reply streaming in. This is the single biggest UX win available in the current TTS stack, and it is the **only working streaming route on the Token Plan** (the dashscope SDK `/inference` WS is dead; REST is whole-file).

**Caveats (be honest about these):**
1. It is a dialogue model, not a TTS model — billing semantics, context limits (300 s audio / 50 turns per session) and quality are not 1:1 with TTS-plus. Recommended pattern: **one-shot sessions per request** (connect → speak → close), not long-lived conversations, to sidestep context/credits drift.
2. **PCM-only output** — needs a transcode or WebAudio playback path (below).
3. **Swedish pronunciation unverified** — must A/B test against current Qwen/StepFun output before rollout (game content is Swedish).
4. Token Plan WS stability is a known historical risk (the `/inference` path died once). Add reconnect/fallback-to-REST logic.
5. Real-time voice quality of a dialogue model may differ from TTS-plus — test before committing Patron narrators to it.

### 5.2 Integration sketch (backend → frontend)

**Backend** (`~/dnd-llm/backend/main.py`, new module e.g. `tts_stream.py`):
1. New endpoint `POST /api/tts/stream` (same tier/voice/style gating as `/api/tts`).
2. Maintain a small pool (1–2) of **persistent WS connections** to `wss://token-plan.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen-audio-3.0-realtime-plus` (reconnect on drop, reuse the existing `DASHSCOPE_API_KEY`).
3. Per request: `session.update` (voice, modalities `["text","audio"]`) → `conversation.item.create` (input_text) → `response.create` → read `response.audio.delta` (base64 PCM) → **transcode PCM→MP3 in small chunks** (lameenc / ffmpeg subprocess; ~5–10% of one core) → push to an **SSE stream** (`text/event-stream`, `data: {"b64": …}` per chunk; `event: done` at `response.done`). Also emit `event: meta` with total PCM duration for progress UI.
4. On cancel (client disconnect / new TTS request): send `response.cancel` / close WS gracefully.
5. Keep the existing whole-file path as **fallback** (any WS error → old REST flow) and keep the 10-min cache by caching the concatenated stream after completion. Usage accounting unchanged (duration from PCM length).

**Frontend** (`~/dnd-llm/frontend/chat.html` + `api.js`):
- Option A (least code, reuses existing player): backend streams **MP3**; frontend uses **MediaSource** (`audio/mpeg`, `appendBuffer` per SSE chunk, `endOfStream` on done) feeding the existing `Audio` element — keeps `playbackRate` speed control and pause/play for free. Progress bar must be reworked to estimate position from `meta` duration (no file `duration` until buffered).
- Option B (no transcoding): WebAudio — append WAV-wrapped PCM chunks (44-byte header per chunk batch) to a queue, schedule `AudioBufferSourceNode`s with lookahead; speed via `playbackRate`. More code, but zero server transcode and sample-accurate.
- Recommendation: **Option A** (MediaSource + MP3) — minimal change to the existing `_wireTtsPlayer`/`playTTS` flow; only the blob-fetch (`API.tts`) is swapped for a stream reader.

**Effort / risk:**
- Backend WS client + SSE relay + fallback: ~0.5–1 dev-day.
- Frontend MediaSource player + progress/stop semantics: ~1–2 dev-days.
- Testing (Swedish A/B, tier gating, credit-burn measurement, reconnect): ~0.5–1 dev-day.
- Risk: **medium** — Token Plan WS longevity, dialogue-model quality delta, unverified Swedish, PCM-only pipeline. All have mitigations (fallback to current REST path is the big one).

### 5.3 Cheaper interim alternative (no new model)
Keep the current REST providers but **parallelize segment synthesis** and **stream each completed segment immediately** (chunked HTTP, MP3 frames in order — the game already proves `b"".join` of same-format segments is playable). First audio after the first segment (~3 s) instead of ~1 min; no new endpoints beyond making the response progressive, no PCM, no new model risk. **This is the recommended first step** (low risk, ~0.5 day); the realtime WS integration is the follow-up that gets first audio to ~1.5 s.

---

## 6. Open questions / next steps

1. **Listen-test** `longanlingxin`/`longanlufeng` on the realtime model vs. TTS-plus (Swedish + English) — quality gate.
2. **Measure credit burn** on Token Plan for a few realtime calls vs. the same text via REST TTS.
3. Verify the realtime WS stays healthy over a longer soak (the `/inference` path died before — monitor).
4. Check whether `instruction`/style control works on the realtime model (untested; session/system-prompt based).
5. If streaming ships: decide cache strategy for streamed audio (whole-PCM cache keyed like today, TTL 10 min).

---

## Appendix: sources & test evidence

**Official docs (primary):**
- Model Studio — Qwen-Audio realtime voice model: alibabacloud.com/help/en/model-studio/qwen-audio-realtime-user-guides (updated 2026-07-14)
- Model Studio — Real-time speech synthesis (TTS models): alibabacloud.com/help/en/model-studio/realtime-tts-user-guide
- Model Studio — Speech synthesis model selection: help.aliyun.com/en/model-studio/tts-model/
- Model Studio — Voice cloning (states realtime is "not a speech synthesis model"): alibabacloud.com/help/en/model-studio/voice-cloning-user-guide
- Model Studio — Qwen-Audio-TTS voice list (languages per voice): help.aliyun.com/en/model-studio/qwen-audio-tts-voice-list
- Model Studio — model index / regions / request URLs: help.aliyun.com/en/model-studio/models

**Secondary (flagged, unverified):** digitalapplied.com & OpenRouter (tts-plus ~$20–27.6/1M chars), aireiter.com (omni-realtime per-token pricing, ~427 tokens/min audio, ~97 ms first-packet for dedicated Qwen-TTS-Realtime), github.com/icnhzq/qianwen-speech-pricing (CN billing overview).

**Live tests run 2026-08-06 (Token Plan key from backend/.env):**
- `GET /compatible-mode/v1/models` → 11 models; `qwen-audio-3.0-realtime-plus` + `qwen-audio-3.0-tts-plus` listed.
- REST SpeechSynthesizer + realtime model → `400 InvalidParameter "url error"` (not callable over REST).
- WS `/api-ws/v1/realtime` + realtime model → connected, `session.created` in ~4 ms; EN/SV short + SV 1,548-char text→speech all succeeded; first audio 1,264 / 1,277 / 1,743 ms; output PCM 24 kHz.
- REST SpeechSynthesizer + tts-plus baseline (~100 chars): 2.9 s total (2.1 s synth+OSS, 0.8 s download).
- REST tts-plus + flash voice (`longanlingxi`) → 400 Engine error 411 (voice/model mismatch — game already uses correct plus voices).
