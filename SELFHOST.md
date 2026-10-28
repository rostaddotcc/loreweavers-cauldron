# Self-hosting The Lore Weaver's Cauldron

This is the stripped, self-contained build of the Cauldron: the same Docker
image as the hosted service, started with `SELFHOST=1`. It runs on your own
machine, keeps all data in a local folder, and plays only against an Ollama
model you host yourself. There is no billing, no account tiers, no turn cap and
no cloud API key — which also means no cloud model quality, no text-to-speech
and no image generation. You trade polish for a private campaign that costs
nothing per turn.

| | Hosted (`dnd.rostad.cc`) | Self-host |
|---|---|---|
| Unlocking supporter features | Stripe checkout | not present — undo and campaign export are on for every account |
| Turn limit | daily cap on free accounts | unlimited turns, no daily cap |
| DM model | cloud models (Qwen, DeepSeek, StepFun, OpenRouter free tier) | local Ollama only |
| TTS narration | yes | absent |
| Image generation | yes | absent |
| Billing routes | `/api/billing/*`, `/api/stripe/webhook` | not registered (404) |

## Requirements

- Docker with the Compose plugin (`docker compose version`).
- Ollama running and reachable from inside the container. The compose file maps
  `host.docker.internal` to the host gateway, so Ollama on the same machine
  works out of the box; if Ollama lives on another box, change `OLLAMA_URL` to
  its address.
- **~4 GB RAM free** for the app plus an 8B model at 4-bit quantization. More
  for bigger models; a 14B model needs roughly 10–12 GB.
- About 6 GB of disk for the image and the model weights.

### Pick a model that can hold the job

The DM quality depends entirely on the local model — there is no fallback. Use
an instruction-following model that is good at tool calls and JSON output.
`qwen3:8b` is the smallest model worth playing on; larger (14B/32B) is
noticeably better at keeping the world consistent. Small 3–4B models tend to
break the structured output the engine relies on. The model picker in the UI
shows these as `ollama:<name>` ids (`ollama:qwen3:8b`); `SELFHOST_MODEL` itself
takes the bare Ollama name.

### Raise Ollama's context window

Ollama's default context is 4k tokens, which is far too small for a campaign —
the system prompt, state and recent turns alone exceed it, and the model
silently starts forgetting. Raise it to at least 16k before playing.

With the systemd service:

```bash
sudo systemctl edit ollama
```

add

```ini
[Service]
Environment="OLLAMA_CONTEXT_LENGTH=16384"
```

then

```bash
sudo systemctl restart ollama
```

If you run Ollama another way, set `OLLAMA_CONTEXT_LENGTH=16384` in its
environment (or `num_ctx` in the request) the same way.

## Quick start

```bash
git clone https://github.com/rostaddotcc/loreweavers-cauldron
cd loreweavers-cauldron

ollama pull qwen3:8b

cp backend/.env.selfhost.example backend/.env.selfhost
# edit backend/.env.selfhost → ADMIN_PASSWORD, JWT_SECRET, SELFHOST_MODEL

docker compose -f docker-compose.selfhost.yml up -d --build
```

Generate a JWT secret with:

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

Then open **http://localhost:8092/login.html** (host port 8092 → container port
8090) and sign in with `ADMIN_USER` / `ADMIN_PASSWORD`. The admin account is
created at first start. Create a campaign from the campaign screen and send a
message to get your first narration.

The container will refuse to start if `backend/.env.selfhost` is missing —
Compose mounts it as the only env file.

## Verify it works

```bash
curl -s localhost:8092/api/health
# {"status":"ok","game":"The Lore Weaver's Cauldron","selfhost":true}

curl -s localhost:8092/api/config
# {"selfhost": true, ...}
```

`"selfhost": true` in `/api/config` confirms the stripped mode is active. Then
start a campaign and send one message: you should get streamed narration back.
The first turn is slow — Ollama has to load the model into RAM.

Logs:

```bash
docker compose -f docker-compose.selfhost.yml logs -f
docker compose -f docker-compose.selfhost.yml ps
```

If narration fails, check the logs for the Ollama connection first: from inside
the container, `host.docker.internal:11434` must answer, and the model named in
`SELFHOST_MODEL` must be one Ollama has:

```bash
docker compose -f docker-compose.selfhost.yml exec cauldron-selfhost \
  python -c "import httpx; print(httpx.get('http://host.docker.internal:11434/api/tags').text)"
```

## What is stripped

- **No Stripe.** `/api/billing/*` and `/api/stripe/webhook` are not registered
  and return 404. `backend/.env.stripe` is not mounted.
- **No turn caps and no tier/patron logic.** Turns are unlimited, and supporter
  features — undo and campaign export — are unlocked for every account.
- **No TTS.** Voice narration endpoints and voices are gone.
- **No image generation.** Character/NPC/scene art generation is gone.
- **No OpenRouter free models.** The `orfree:` model path does not exist here.
- **No cloud providers.** No DashScope, DeepSeek, StepFun or MiMo keys are read;
  the only model backend is Ollama.

The frontend is the same bundle as the hosted build, but it adapts: every page
loads `frontend/selfhost.js`, which asks `/api/config` what this build can do
and hides the billing links, the turn counters, the update banner and the
narration/voice controls. The endpoints behind them are not there either, so a
stale cached page cannot spend anything — it just gets a `404` or a `501`.

## Data and backups

Everything lives in `backend/data/` on the host:

```
backend/data/
├── users.json      # accounts (bcrypt hashes)
├── campaigns/      # per-user campaign state, transcripts, attachments
└── vaults/         # saved characters
```

Back it up by archiving that folder (stop the container first so nothing is
mid-write):

```bash
docker compose -f docker-compose.selfhost.yml stop
tar czf cauldron-backup-$(date +%F).tar.gz -C backend data
docker compose -f docker-compose.selfhost.yml start
```

Restore is the reverse: stop, extract the archive into `backend/`, start.

### Security

- **Do not expose it to the internet as-is.** There is no TLS in the container.
  Put it behind nginx/Caddy/Traefik with a certificate, and set
  `COOKIE_SECURE=1` in the `environment:` block of
  `docker-compose.selfhost.yml` (that block overrides the env file, so editing
  `.env.selfhost` alone is not enough).
- Set a real `ADMIN_PASSWORD` and `JWT_SECRET` before the first start; the admin
  account is bootstrapped from the environment and the password is stored as a
  bcrypt hash in `data/users.json`.
- `backend/.env.selfhost` holds secrets and is already listed in `.gitignore` —
  keep it that way in your clone.

## Known limitations

- Image generation and voice narration are simply absent — there is no
  local substitute wired in.
- The DM runs at your model's speed. Expect seconds to tens of seconds per turn
  on CPU, much faster on a decent GPU.
- Model quality sets the ceiling: confused continuity, ignored mechanics or
  malformed structured output at small sizes is the model's limit, not a bug to
  file.
- RAG memory needs a Qdrant instance plus `QDRANT_URL` (and an embedding model
  in Ollama). Leave `QDRANT_URL` unset and the game runs without vector memory.
- Single image, single instance: this compose file is meant for one machine, not
  a horizontally scaled deployment.