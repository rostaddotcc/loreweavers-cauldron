"""
IP-spårning + geo-uppslag för The Lore Weaver's Cauldron.

Middlewares i main.py anropar `record_ip()` för varje autentiserad request.

GEO-STRATEGI (2026-09-20, rostad: "sluta pinga hela dagarna"):
- Uppslag sker ENDAST i bakgrunden (fire-and-forget) när en NY eller ÄNDRAD
  publik IP dyker upp: vid registrering, vid login (IP-byte) och när en
  ny besöks-IP räknas in i record_visit.
- Admin-vyn (`geo_for_users`, `visits_summary`) är REN CACHE-LÄSNING —
  aldrig nätverksanrop i requesten. Okänd IP → "??" tills bakgrunds-
  uppslaget landat; gammal cache visas hellre än inget (land ändras sällan).
- Budget: max LOOKUP_DAILY_BUDGET uppslag/dygn (ipwho.is = 10k req/månad).
  Incident 2026-09-20: en 7-dagars TTL + sekventiella uppslag INNE i
  admin-requesten brände ~1300 anrop på en dag när cachen revertades.
- Misslyckade uppslag negativ-cachas i GEO_FAIL_TTL (24 h) — tidigare
  retriedes de i evighet vid varje dashboard-laddning.

Flagg-emoji genereras från landskod (regional indicators), t.ex. "SE" → 🇸🇪.
Privata/lokala IP:er (LAN, Docker-brygga, localhost) markeras 🏠 Lokal
och skickas ALDRIG till något geo-API.
"""

import asyncio
import json
import re
import time
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent / "data"
IP_GEO_FILE = DATA_DIR / "ip_geo.json"
VISITS_FILE = DATA_DIR / "visits.json"
GEO_REFRESH_AGE = 86400 * 30  # bakgrunds-refresh tidigast efter 30 dygn (display: stale-OK)
GEO_FAIL_TTL = 86400          # negativ cache: 24 h innan misslyckad IP provas igen
LOOKUP_DAILY_BUDGET = 150     # max externa geo-anrop per dygn (10k/mån → gott om marginal)
_GEO_MAX_CONCURRENT = 4       # samtidiga bakgrundsuppslag

# In-memory cache: {"ip": {"country": ..., "countryCode": ..., "ts": ...}}
_geo_cache: dict[str, dict] = {}
# Per-användare senast sedda IP:er (skrivs till disk vid ändring)
_ip_store: dict[str, dict] = {}
# Besöksräkning (2026-08-05, rostad): {total, by_day, by_ip, by_referrer, by_day_unique}.
# by_ip används för att aggregera "unika besökare per land" vid admin-stats
# (varje IP = 1 unik besökare, geokodas via cache). by_referrer = varifrån
# besökaren klickade in (Google, Reddit, Direct …) som {källa: {ip: last_seen}}
# → unika besökare per källa (2026-08-09). by_day_unique = {dag: {ip: last_seen}}
# → unika besökare per dag för dagsgrafen i admin.
_visit_store: dict = {"total": 0, "by_day": {}, "by_ip": {}, "by_referrer": {}, "by_day_unique": {}}
_visits_loaded = False
_loaded = False

# CIDR-nät som aldrig slås upp (privata + loopback + link-local)
_PRIVATE_PREFIXES = (
    "10.", "127.", "169.254.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.", "0.", "255.255.255.255",
)


def _load():
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if IP_GEO_FILE.exists():
            data = json.loads(IP_GEO_FILE.read_text())
            _ip_store.update(data.get("users", {}))
            _geo_cache.update(data.get("geo", {}))
    except (OSError, json.JSONDecodeError):
        pass


def _save():
    try:
        IP_GEO_FILE.parent.mkdir(parents=True, exist_ok=True)
        IP_GEO_FILE.write_text(json.dumps({
            "users": _ip_store,
            "geo": _geo_cache,
        }, ensure_ascii=False, indent=1))
    except OSError:
        pass


def client_ip(request) -> str:
    """Extrahera klient-IP ur request: X-Forwarded-For → direkt anslutning."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return ""


def is_private(ip: str) -> bool:
    if not ip:
        return True
    ip = ip.strip().lower()
    if ip in ("::1", "::ffff:127.0.0.1"):
        return True
    if ip.startswith("::ffff:"):
        ip = ip[7:]
    # Inte en riktig IP (t.ex. hostname "testclient" från TestClient, eller
    # tomt) → behandla som privat. 2026-08-05: annars blockerade register
    # 1-konto-per-IP på icke-IP-värden och alla tester sprack.
    if ":" not in ip and not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
        return True
    return ip.startswith(_PRIVATE_PREFIXES)


def record_ip(username: str, ip: str) -> None:
    """Spara senast sedda IP för en användare. Skriver bara till disk när IP ändrats.

    Ny/ändrad publik IP → köa ETT bakgrunds-geo-uppslag (2026-09-20).
    """
    if not username or not ip:
        return
    _load()
    now = time.time()
    prev = _ip_store.get(username)
    if prev and prev.get("ip") == ip:
        prev["last_seen"] = now
        return
    _ip_store[username] = {
        "ip": ip,
        "first_seen": prev.get("first_seen", now) if prev else now,
        "last_seen": now,
    }
    _save()
    queue_geo_lookup(ip)


# ── Bakgrunds-geo (2026-09-20) ──────────────────────────────────────────
# Admin-ytor läser BARA cachen; uppslag köas hit och körs av en worker med
# daglig budget + negativ cache. Aldrig nätverk i en request-path.
_geo_queue: set[str] = set()
_geo_inflight: set[str] = set()
_geo_worker = None
_budget_day: str = ""
_budget_used: int = 0
_GEO_QUEUE_MAX = 500  # minnestak; överflödet köas om vid nästa besök/login


def _budget_ok() -> bool:
    """Rullande dygnsbudget för externa geo-anrop (reset vid datumbyte)."""
    global _budget_day, _budget_used
    today = time.strftime("%Y-%m-%d")
    if today != _budget_day:
        _budget_day, _budget_used = today, 0
    return _budget_used < LOOKUP_DAILY_BUDGET


def _needs_lookup(ip: str) -> bool:
    """True om IP saknar användbar cache eller cachen är tillräckligt gammal."""
    cached = _geo_cache.get(ip)
    now = time.time()
    if not cached:
        return True
    if cached.get("fail"):
        # misslyckat uppslag — provas igen först efter GEO_FAIL_TTL
        return (now - cached.get("ts", 0)) >= GEO_FAIL_TTL
    if not cached.get("countryCode"):
        return True
    return (now - cached.get("ts", 0)) >= GEO_REFRESH_AGE


def queue_geo_lookup(ip: str) -> None:
    """Köa ett bakgrundsuppslag (dedup, budget-check, privat-skydd).

    Anropas SYNKRONT från record_ip/record_visit/admin-läsningar — själva
    nätverket sker i _geo_worker_loop. Ingen loop (t.ex. tester/sync-kontext)
    → köa bara; nästa async-anrop drar igång workern.
    """
    if not ip or is_private(ip):
        return
    _load()
    if not _needs_lookup(ip):
        return
    if ip in _geo_queue or ip in _geo_inflight:
        return
    if len(_geo_queue) >= _GEO_QUEUE_MAX:
        return
    _geo_queue.add(ip)
    _ensure_geo_worker()


def _ensure_geo_worker() -> None:
    global _geo_worker
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _geo_worker is None or _geo_worker.done():
        _geo_worker = loop.create_task(_geo_worker_loop())


async def _geo_worker_loop() -> None:
    """Dränerar kön: max _GEO_MAX_CONCURRENT samtidiga, 0.5s paus per batch.

    Budgeten bokförs HÄR per dispatch (inte i _geo_fetch) — en dispatch kan
    bli upp till 2 HTTP-anrop (provider-fallback), så räkna worst-case 2×
    mot providerns kvot. Budget slut → resten ligger kvar i kön till nästa dygn.
    """
    global _budget_used
    sem = asyncio.Semaphore(_GEO_MAX_CONCURRENT)
    while _geo_queue:
        if not _budget_ok():
            return
        cap = min(_GEO_MAX_CONCURRENT, LOOKUP_DAILY_BUDGET - _budget_used)
        if cap <= 0:
            return
        batch = set()
        while _geo_queue and len(batch) < cap:
            batch.add(_geo_queue.pop())
        _budget_used += len(batch)
        _geo_inflight.update(batch)
        try:
            await asyncio.gather(*[_geo_fetch(ip, sem) for ip in batch])
        finally:
            _geo_inflight.difference_update(batch)
        await asyncio.sleep(0.5)


def get_user_ip(username: str) -> str:
    _load()
    return (_ip_store.get(username) or {}).get("ip", "")


def _visits_load() -> None:
    global _visits_loaded
    if _visits_loaded:
        return
    _visits_loaded = True
    try:
        if VISITS_FILE.exists():
            data = json.loads(VISITS_FILE.read_text())
            _visit_store["total"] = int(data.get("total", 0) or 0)
            _visit_store["by_day"] = data.get("by_day", {}) or {}
            _visit_store["by_ip"] = data.get("by_ip", {}) or {}
            _visit_store["by_referrer"] = data.get("by_referrer", {}) or {}
            _visit_store["by_day_unique"] = data.get("by_day_unique", {}) or {}
    except (OSError, json.JSONDecodeError):
        pass


def _visits_save() -> None:
    try:
        VISITS_FILE.parent.mkdir(parents=True, exist_ok=True)
        VISITS_FILE.write_text(json.dumps(_visit_store, ensure_ascii=False))
    except OSError:
        pass


# Kända sökmotorer + sajter → läsbara etiketter för referrer-spårning
_SEARCH_ENGINES = {
    "google": "Google", "bing": "Bing", "duckduckgo": "DuckDuckGo",
    "yahoo": "Yahoo", "yandex": "Yandex", "ecosia": "Ecosia",
    "startpage": "Startpage", "qwant": "Qwant", "brave": "Brave",
}
_KNOWN_SITES = {
    "reddit.com": "Reddit", "discord.com": "Discord", "t.me": "Telegram",
    "facebook.com": "Facebook", "x.com": "X", "twitter.com": "X",
    "instagram.com": "Instagram", "youtube.com": "YouTube",
    "tiktok.com": "TikTok", "twitch.tv": "Twitch", "linkedin.com": "LinkedIn",
    "steamcommunity.com": "Steam", "rollspel.nu": "rollspel.nu",
}


def _referrer_source(referrer: str, self_host: str = "") -> str:
    """Klassificera en HTTP Referer → läsbar källa (Google, Reddit, Direct …).

    - Tom/relativ referrer → "Direct" (skrivit URL själv, bokmärke, app).
    - Egen domän (self_host) → "Direct" — intern navigering räknas inte som
      "klick inifrån".
    - Känd sökmotor/sajt → läsbar etikett, annars domänen som den är.
    """
    if not referrer:
        return "Direct"
    try:
        from urllib.parse import urlparse
        host = (urlparse(referrer).netloc or "").lower()
    except Exception:
        return "Direct"
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return "Direct"
    # Strippa port (host:port) — IPv6 (med [ ]) lämnas orörd
    if not host.startswith("["):
        host = host.split(":")[0]
    sh = (self_host or "").lower().split(":")[0]
    if sh and (host == sh or host == "www." + sh):
        return "Direct"
    for key, label in _SEARCH_ENGINES.items():
        if host == key or host.startswith(key + "."):
            return label
    if host in _KNOWN_SITES:
        return _KNOWN_SITES[host]
    return host


def record_visit(ip: str, referrer: str = "", self_host: str = "") -> None:
    """Räkna en sidvisning (anropas från middleware för HTML-sidor).

    by_day sparas i ~32 dagar; by_ip = {count, last_seen} per IP för
    unique-besök (antal distinkta besökare) i admin-stats. Geokodning sker
    lat i visits_summary via _geo_cache — inget nätverksanrop här.
    by_referrer = varifrån besökaren kom (Google/Reddit/Direct …) som
    {källa: {ip: last_seen}} → unika besökare per källa. by_day_unique =
    {dag: {ip: last_seen}} → unika besökare per dag (2026-08-09, rostad).
    """
    _visits_load()
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    _visit_store["total"] += 1
    _visit_store["by_day"][today] = int(_visit_store["by_day"].get(today, 0) or 0) + 1
    key = ip or "__noip__"
    if ip:
        cur = _visit_store["by_ip"].get(ip)
        if isinstance(cur, dict):
            cur["count"] = int(cur.get("count", 0) or 0) + 1
            cur["last_seen"] = now
        else:
            # Migrera legacy-format (int) → {count, last_seen}
            _visit_store["by_ip"][ip] = {"count": int(cur or 0) + 1, "last_seen": now}
    # Referrer-källa (egna sidor → Direct, så vi mäter bara utifrån-in-klick).
    # Format {källa: {ip: last_seen}} → unika besökare per källa. Legacy-int
    # (total) ersätts med en färsk dict vid nästa besök från källan.
    src = _referrer_source(referrer, self_host)
    refs = _visit_store.setdefault("by_referrer", {})
    if not isinstance(refs.get(src), dict):
        refs[src] = {}
    refs[src][key] = now
    # Unika besökare per dag (distinkta IP:er i dagens set)
    du = _visit_store.setdefault("by_day_unique", {})
    today_set = du.setdefault(today, {})
    today_set[key] = now
    # Trimma by_day + by_day_unique till ~32 dagar
    days = sorted(_visit_store["by_day"].keys())
    if len(days) > 32:
        for d in days[: len(days) - 32]:
            _visit_store["by_day"].pop(d, None)
            du.pop(d, None)
    _visits_save()
    # Ny besöks-IP → köa bakgrunds-geo (2026-09-20). Dedup+budget i queue_geo_lookup:
    # återbesök från känd/färsk IP kostar inget (ingen kö, inget anrop).
    if ip and not is_private(ip) and ip not in _geo_cache:
        queue_geo_lookup(ip)


async def visits_summary(country_range: str = "all") -> dict:
    """Admin-sammanfattning: total, idag, 7 dagar, per dag (14) + unika per land.

    Per-land aggregeras från by_ip via geo-cachen (varje IP = 1 unik besökare,
    2026-08-09); okända IP:er slås upp lat (geo_for_ip, cachad). by_referrer
    = unika besökare per källa (Google/Reddit/Direct …). by_day_unique = unika
    besökare per dag (distinkta IP:er). country_range filtrerar land-grafen på
    IP:ernas senaste aktivitet: 1h/12h/24h/7d/30d (default "all")."""
    _visits_load()
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    last_7 = 0
    for i in range(7):
        d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
        last_7 += int(_visit_store["by_day"].get(d, 0) or 0)
    days = sorted(_visit_store["by_day"].keys())[-14:]
    by_day = {d: int(_visit_store["by_day"].get(d, 0) or 0) for d in days}
    # Unika besökare per dag (distinkta IP:er per dag) — dagsgrafen i admin
    du = _visit_store.get("by_day_unique", {}) or {}
    du_days = sorted(du.keys())[-14:]
    by_day_unique = {d: len(du[d]) for d in du_days if isinstance(du.get(d), dict)}
    # Unique-besök (distinkta IP:er): total, idag, senaste 7 dygn
    now = time.time()
    day_start = time.mktime(time.strptime(today, "%Y-%m-%d"))
    unique_total = 0
    unique_today = 0
    unique_7d = 0
    unique_14d = 0
    for rec in _visit_store["by_ip"].values():
        if not isinstance(rec, dict):
            continue
        last = float(rec.get("last_seen", 0) or 0)
        unique_total += 1
        if last >= day_start:
            unique_today += 1
        if last >= now - 7 * 86400:
            unique_7d += 1
        if last >= now - 14 * 86400:
            unique_14d += 1
    # Land-grafens tidsfönster (2026-08-09, rostad): filtrera på IP:ernas
    # senaste aktivitet → "unika besökare de senaste 1h/12h/24h/7d/30d".
    cutoff = 0  # all time
    if country_range == "1h":
        cutoff = now - 3600
    elif country_range == "12h":
        cutoff = now - 12 * 3600
    elif country_range == "24h":
        cutoff = now - 24 * 3600
    elif country_range == "7d":
        cutoff = now - 7 * 86400
    elif country_range == "30d":
        cutoff = now - 30 * 86400
    by_country: dict[str, int] = {}
    for ip, rec in _visit_store["by_ip"].items():
        if cutoff:
            last = rec.get("last_seen", 0) if isinstance(rec, dict) else 0
            if not last or last < cutoff:
                continue
        # Unika besökare per land: varje distinkt IP räknas EN gång,
        # oavsett antal sidvisningar (2026-08-09, rostad: "unique visitors by country").
        # 2026-09-20: REN CACHE-LÄSNING — aldrig nätverk i admin-requesten.
        # Okänd/stale IP köas till bakgrundsworkern (queue_geo_lookup);
        # gammal cache visas hellre än "??" (länder ändras sällan).
        cc = "??"
        if ip and not is_private(ip):
            cached = _geo_cache.get(ip)
            if cached:
                cc = cached.get("countryCode") or "??"
            queue_geo_lookup(ip)  # no-op om cachen är färsk; budget+tak skyddar
        else:
            cc = "LOCAL" if (ip and is_private(ip)) else "??"
        by_country[cc] = by_country.get(cc, 0) + 1
    by_country = dict(sorted(by_country.items(), key=lambda kv: kv[1], reverse=True))
    # Unika besökare per referrer-källa: {källa: {ip: last_seen}} → len(ips).
    # Legacy-int (total) behålls som count tills källan får nya besök.
    by_referrer: dict[str, int] = {}
    for src, v in (_visit_store.get("by_referrer", {}) or {}).items():
        if isinstance(v, dict):
            by_referrer[src] = len(v)
        elif isinstance(v, int):
            by_referrer[src] = v
        else:
            by_referrer[src] = 1
    by_referrer = dict(sorted(by_referrer.items(), key=lambda kv: kv[1], reverse=True))
    return {
        "total": _visit_store["total"],
        "today": int(_visit_store["by_day"].get(today, 0) or 0),
        "last_7": last_7,
        "unique_total": unique_total,
        "unique_today": unique_today,
        "unique_7d": unique_7d,
        "unique_14d": unique_14d,
        "by_day": by_day,
        "by_day_unique": by_day_unique,
        "by_country": by_country,
        "by_referrer": by_referrer,
    }

def country_flag(country_code: str) -> str:
    """Landskod 'SE' → flagg-emoji 🇸🇪. 'LOCAL' → 🏠, tom → ❓."""
    if not country_code:
        return "❓"
    cc = country_code.upper()
    if cc == "LOCAL":
        return "🏠"
    if len(cc) != 2 or not cc.isalpha():
        return "❓"
    return chr(0x1F1E6 + ord(cc[0]) - ord("A")) + chr(0x1F1E6 + ord(cc[1]) - ord("A"))


async def _geo_fetch(ip: str, sem: asyncio.Semaphore) -> dict:
    """BAKGRUNDS-uppslag (körs bara av _geo_worker_loop — budget bokförs där).

    Misslyckade anrop negativ-cachas (fail=True, GEO_FAIL_TTL) så de inte
    retries vid varje dashboard-laddning. Providers i fallback-ordning
    (ip-api.com är blockerad från servern):
      1. ipwho.is  — gratis, ingen nyckel, 10k req/månad
      2. ipinfo.io — gratis, ingen nyckel, 50k req/månad (country bara)
    """
    if not ip or is_private(ip):
        return {"country": "Lokal", "countryCode": "LOCAL"}
    _load()
    async with sem:
        providers = [
            ("https://ipwho.is/{ip}", {"country": "country", "countryCode": "country_code"}),
            ("https://ipinfo.io/{ip}/json", {"country": "country", "countryCode": "country"}),
        ]
        for url_tpl, mapping in providers:
            try:
                async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
                    r = await client.get(url_tpl.format(ip=ip))
                    if r.status_code != 200:
                        continue
                    data = r.json()
                country = data.get(mapping["country"], "") or ""
                code = data.get(mapping["countryCode"], "") or ""
                if code:
                    _geo_cache[ip] = {"country": country, "countryCode": code, "ts": time.time()}
                    _save()
                    return {"country": country, "countryCode": code}
            except Exception:
                continue
        # Båda providrarna misslyckades → negativ cache (24 h)
        _geo_cache[ip] = {"country": "", "countryCode": "", "ts": time.time(), "fail": True}
        _save()
        return {"country": "", "countryCode": ""}


def geo_cached(ip: str) -> dict:
    """Cachen exakt som den är — ingen nätverksanrop, ingen TTL-gate.

    Stale-värde visas hellre än tomt: en IP:s land flyttar i princip aldrig.
    """
    if not ip or is_private(ip):
        return {"country": "Lokal", "countryCode": "LOCAL"}
    cached = _geo_cache.get(ip) or {}
    return {"country": cached.get("country", ""), "countryCode": cached.get("countryCode", "")}


async def geo_for_ip(ip: str) -> dict:
    """Cache-först, bakgrund-refresh. ALDRIG ett blockande nätverksanrop.

    Historik: förr slog denna funktion upp synkront i requesten med 7-dagars
    TTL → admin-dashboarden kunde trigga tusentals sekventiella anrop
    (incident 2026-09-20). Nu: läs cachen, köa bakgrundsuppslag vid behov.
    """
    if not ip or is_private(ip):
        return {"country": "Lokal", "countryCode": "LOCAL"}
    _load()
    if _needs_lookup(ip):
        queue_geo_lookup(ip)
    return geo_cached(ip)


async def geo_for_users(users: dict[str, dict]) -> dict[str, dict]:
    """Batch-läsning för alla användare. Returnerar {username: {country, countryCode, ip}}.

    2026-09-20: REN CACHE — okända/stale IP:er köas till bakgrundsworkern
    (max LOOKUP_DAILY_BUDGET/dygn, _GEO_MAX_CONCURRENT samtidiga) och syns
    som "??" tills uppslaget landat. Privata IP:er = 🏠 Lokal direkt.
    """
    _load()
    result: dict[str, dict] = {}
    for username in users:
        ip = get_user_ip(username)
        if not ip:
            result[username] = {"ip": "", "country": "", "countryCode": ""}
            continue
        if is_private(ip):
            result[username] = {"ip": ip, "country": "Lokal", "countryCode": "LOCAL"}
            continue
        if _needs_lookup(ip):
            queue_geo_lookup(ip)
        result[username] = {"ip": ip, **geo_cached(ip)}
    _ensure_geo_worker()  # starta dränering om kön växte utanför en loop-kontext
    return result
