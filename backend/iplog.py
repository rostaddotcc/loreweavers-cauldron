"""
IP-spårning + geo-uppslag för The Lore Weaver's Cauldron.

Middlewares i main.py anropar `record_ip()` för varje autentiserad request.
Admin-vyn hämtar `geo_for_users()` som batch-slår upp okända IP:er via
ip-api.com (gratis, ingen nyckel, 45 req/min) och cachar resultatet i
data/ip_geo.json så vi inte slår API:t i onödan.

Flagg-emoji genereras från landskod (regional indicators), t.ex. "SE" → 🇸🇪.
Privata/lokala IP:er (LAN, Docker-brygga, localhost) markeras 🏠 Lokal
och skickas ALDRIG till ip-api.com.
"""

import json
import re
import time
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent / "data"
IP_GEO_FILE = DATA_DIR / "ip_geo.json"
VISITS_FILE = DATA_DIR / "visits.json"
GEO_CACHE_TTL = 86400 * 7  # 7 dygn innan vi slår upp samma IP igen

# In-memory cache: {"ip": {"country": ..., "countryCode": ..., "ts": ...}}
_geo_cache: dict[str, dict] = {}
# Per-användare senast sedda IP:er (skrivs till disk vid ändring)
_ip_store: dict[str, dict] = {}
# Besöksräkning (2026-08-05, rostad): {total, by_day, by_ip}. by_ip används
# för att aggregera "besök per land" vid admin-stats (geokodas via cache).
_visit_store: dict = {"total": 0, "by_day": {}, "by_ip": {}}
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
    """Spara senast sedda IP för en användare. Skriver bara till disk när IP ändrats."""
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


def get_user_ip(username: str) -> str:
    _load()
    return (_ip_store.get(username) or {}).get("ip", "")


def _visits_load() -> None:
    global _visits_loaded, _visit_store
    if _visits_loaded:
        return
    _visits_loaded = True
    try:
        if VISITS_FILE.exists():
            data = json.loads(VISITS_FILE.read_text())
            _visit_store["total"] = int(data.get("total", 0) or 0)
            _visit_store["by_day"] = data.get("by_day", {}) or {}
            _visit_store["by_ip"] = data.get("by_ip", {}) or {}
    except (OSError, json.JSONDecodeError):
        pass


def _visits_save() -> None:
    try:
        VISITS_FILE.parent.mkdir(parents=True, exist_ok=True)
        VISITS_FILE.write_text(json.dumps(_visit_store, ensure_ascii=False))
    except OSError:
        pass


def record_visit(ip: str) -> None:
    """Räkna en sidvisning (anropas från middleware för HTML-sidor).

    by_day sparas i ~32 dagar; by_ip = {count, last_seen} per IP för
    unique-besök (antal distinkta besökare) i admin-stats. Geokodning sker
    lat i visits_summary via _geo_cache — inget nätverksanrop här."""
    _visits_load()
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    _visit_store["total"] += 1
    _visit_store["by_day"][today] = int(_visit_store["by_day"].get(today, 0) or 0) + 1
    if ip:
        cur = _visit_store["by_ip"].get(ip)
        if isinstance(cur, dict):
            cur["count"] = int(cur.get("count", 0) or 0) + 1
            cur["last_seen"] = now
        else:
            # Migrera legacy-format (int) → {count, last_seen}
            _visit_store["by_ip"][ip] = {"count": int(cur or 0) + 1, "last_seen": now}
    # Trimma by_day till ~32 dagar
    days = sorted(_visit_store["by_day"].keys())
    if len(days) > 32:
        for d in days[: len(days) - 32]:
            _visit_store["by_day"].pop(d, None)
    _visits_save()


async def visits_summary() -> dict:
    """Admin-sammanfattning: total, idag, 7 dagar, per dag (14) + per land.

    Per-land aggregeras från by_ip via geo-cachen; okända IP:er slås upp
    lat (geo_for_ip, cachad) — samma mekanism som admin-landskollen."""
    _visits_load()
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    last_7 = 0
    for i in range(7):
        d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
        last_7 += int(_visit_store["by_day"].get(d, 0) or 0)
    days = sorted(_visit_store["by_day"].keys())[-14:]
    by_day = {d: int(_visit_store["by_day"].get(d, 0) or 0) for d in days}
    # Unique-besök (distinkta IP:er): total, idag, senaste 7 dygn
    now = time.time()
    day_start = time.mktime(time.strptime(today, "%Y-%m-%d"))
    unique_total = 0
    unique_today = 0
    unique_7d = 0
    for rec in _visit_store["by_ip"].values():
        if not isinstance(rec, dict):
            continue
        last = float(rec.get("last_seen", 0) or 0)
        unique_total += 1
        if last >= day_start:
            unique_today += 1
        if last >= now - 7 * 86400:
            unique_7d += 1
    by_country: dict[str, int] = {}
    for ip, n in _visit_store["by_ip"].items():
        cnt = n.get("count", 1) if isinstance(n, dict) else int(n or 1)
        cc = "??"
        if ip and not is_private(ip):
            cached = _geo_cache.get(ip)
            if cached and time.time() - cached.get("ts", 0) < GEO_CACHE_TTL:
                cc = cached.get("countryCode") or "??"
            else:
                info = await geo_for_ip(ip)
                cc = info.get("countryCode") or "??"
        else:
            cc = "LOCAL" if (ip and is_private(ip)) else "??"
        by_country[cc] = by_country.get(cc, 0) + cnt
    by_country = dict(sorted(by_country.items(), key=lambda kv: kv[1], reverse=True))
    return {
        "total": _visit_store["total"],
        "today": int(_visit_store["by_day"].get(today, 0) or 0),
        "last_7": last_7,
        "unique_total": unique_total,
        "unique_today": unique_today,
        "unique_7d": unique_7d,
        "by_day": by_day,
        "by_country": by_country,
    }


def find_username_for_ip(ip: str) -> str | None:
    """Returnera en befintlig användare med samma PUBLIKA IP, annars None.

    Används av register för 1-konto-per-IP (2026-08-05). Privata IP:er
    (LAN/localhost) hoppas över — blockering är meningslös bakom NAT och
    skulle bryta lokal utveckling. _ip_store uppdateras av record_ip() på
    varje autentiserad request, så befintliga användares IP:er finns där."""
    if not ip or is_private(ip):
        return None
    _load()
    for uname, rec in _ip_store.items():
        if rec and rec.get("ip") == ip:
            return uname
    return None


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


async def geo_for_ip(ip: str) -> dict:
    """Slå upp en enskild IP → {country, countryCode}. Cachad + privat-skydd.

    Providers i fallback-ordning (ip-api.com är blockerad från servern):
      1. ipwho.is  — gratis, ingen nyckel, 10k req/månad
      2. ipinfo.io — gratis, ingen nyckel, 50k req/månad (country bara)
    """
    if not ip or is_private(ip):
        return {"country": "Lokal", "countryCode": "LOCAL"}
    _load()
    cached = _geo_cache.get(ip)
    if cached and time.time() - cached.get("ts", 0) < GEO_CACHE_TTL:
        return {"country": cached.get("country", ""), "countryCode": cached.get("countryCode", "")}
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
    return {"country": "", "countryCode": ""}


async def geo_for_users(users: dict[str, dict]) -> dict[str, dict]:
    """Batch-uppslag för alla användare. Returnerar {username: {country, countryCode, ip}}.

    Slår upp varje IP som saknar färsk cache (sekventiellt — få användare,
    ipwho.is har 10k req/månad). Privata IP:er hoppas över direkt."""
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
        cached = _geo_cache.get(ip)
        if cached and time.time() - cached.get("ts", 0) < GEO_CACHE_TTL:
            result[username] = {
                "ip": ip,
                "country": cached.get("country", ""),
                "countryCode": cached.get("countryCode", ""),
            }
        else:
            info = await geo_for_ip(ip)
            result[username] = {"ip": ip, **info}
    return result
