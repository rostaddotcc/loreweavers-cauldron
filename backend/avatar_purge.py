"""
Avatar purge — diskstädning av gamla porträtt (2026-08-08)
==========================================================

Varje karaktär (äventyraren, DM:n, varje NPC) har ett galleri på upp till
MAX_AVATAR_GALLERY bilder som spelaren bläddrar mellan. Bilder som INTE är
satta som aktiv avatar får ligga kvar i galleriet så spelaren kan gå tillbaka
till ett gammalt porträtt — men de kostar disk (1–1.5 MB styck).

Denna modul raderar:

  1. ORPHANS — filer i avatars/ som inte refereras av NÅGON post i state.json.
     Uppstår när galleriet cappas, när en kampanj-state skrivs över, eller när
     en gammal bugg lämnade filer kvar. Raderas oavsett ålder (de kan aldrig
     visas igen), men bara om filen är äldre än ORPHAN_GRACE_SECONDS så att en
     bild som just skrivits till disk mitt i en pågående generering överlever.

  2. INAKTIVA GALLERIBILDER äldre än PURGE_AFTER_DAYS — bilden ligger kvar i
     galleriet men är inte den aktiva, och ingen har rört den på 30 dagar.
     Posten tas bort ur galleriet OCH filen raderas.

Den AKTIVA bilden raderas ALDRIG, oavsett ålder. Vault-porträtt
(data/vaults/<user>/avatars/) rörs inte alls — de är permanenta karaktärskort.

Åldern läses i första hand från postens "uploaded"-fält, med filens mtime som
fallback (legacy-poster saknar uploaded).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("loreweavers.avatar_purge")

PURGE_AFTER_DAYS = 30
# Föräldralösa filer måste vara minst så här gamla innan de städas.
# Sju dagar, inte en timme: en bild kan se föräldralös ut om state.json
# tillfälligt skrivits över av en samtidig bakgrundsuppgift (samma race som
# _STATE_LOCKS skyddar mot i main.py). Att behålla 20 MB en vecka extra är
# oändligt mycket billigare än att radera en spelares riktiga porträtt.
ORPHAN_GRACE_SECONDS = 7 * 24 * 3600

_AVATAR_ITEM_FIELDS = ("disk_name", "ext", "size", "uploaded", "seed", "ai_generated")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value) -> datetime | None:
    """Tolka en ISO-tidsstämpel; returnera None om den saknas/är trasig."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _item_age_days(item: dict, path: Path, now: datetime) -> float:
    """Ålder i dagar — 'uploaded' först, filens mtime som fallback."""
    ts = _parse_ts(item.get("uploaded"))
    if ts is None and path.exists():
        try:
            ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            ts = None
    if ts is None:
        # Okänd ålder → behandla som färsk, radera aldrig i blindo.
        return 0.0
    return (now - ts).total_seconds() / 86400.0


def _file_size(path: Path, item: dict) -> int:
    """Verklig filstorlek på disk; postens 'size' bara som fallback.

    Metadatan kan vara inaktuell (bild ersatt, post kopierad) — disken är
    sanningen när vi rapporterar hur mycket som faktiskt frigjordes.
    """
    try:
        if path.exists():
            return path.stat().st_size
    except OSError:
        pass
    try:
        return int(item.get("size") or 0)
    except (TypeError, ValueError):
        return 0


def _gallery(entry: dict) -> list:
    """Normalisera en avatar-post till ett galleri (samma regel som main.py)."""
    gal = entry.get("gallery")
    if not isinstance(gal, list):
        item = {k: entry[k] for k in _AVATAR_ITEM_FIELDS if k in entry}
        gal = [item] if item.get("disk_name") else []
        entry["gallery"] = gal
        entry["gallery_index"] = 0
    return gal


def _sync_active(entry: dict) -> None:
    """Spegla den aktiva bildens fält på top-level (bakåtkompatibilitet)."""
    gal = _gallery(entry)
    if not gal:
        entry["gallery_index"] = 0
        for k in _AVATAR_ITEM_FIELDS:
            entry.pop(k, None)
        return
    idx = int(entry.get("gallery_index") or 0) % len(gal)
    entry["gallery_index"] = idx
    active = gal[idx]
    for k in _AVATAR_ITEM_FIELDS:
        if k in active:
            entry[k] = active[k]
        else:
            entry.pop(k, None)


def purge_campaign(
    state_path: Path,
    *,
    older_than_days: int = PURGE_AFTER_DAYS,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict:
    """Städa avatars/ för EN kampanj. Returnerar statistik.

    Skriver bara om state.json när något faktiskt togs bort ur ett galleri.
    """
    now = now or _now()
    av_dir = state_path.parent / "avatars"
    stats = {"removed_files": 0, "removed_entries": 0, "freed_bytes": 0, "orphans": 0}
    if not av_dir.is_dir():
        return stats

    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("🧹 Kunde inte läsa %s: %s", state_path, e)
        return stats

    avatars = state.get("avatars") or {}
    referenced: set[str] = set()
    changed = False

    for key, entry in list(avatars.items()):
        if not isinstance(entry, dict):
            continue
        gal = _gallery(entry)
        active_idx = int(entry.get("gallery_index") or 0) % len(gal) if gal else 0
        keep: list = []
        for i, item in enumerate(gal):
            disk_name = item.get("disk_name")
            if not disk_name:
                continue
            path = av_dir / disk_name
            is_active = i == active_idx
            age = _item_age_days(item, path, now)
            if not is_active and age >= older_than_days:
                # Inaktiv + gammal → bort ur galleriet och från disk.
                size = _file_size(path, item)
                if not dry_run:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError as e:
                        logger.debug("🧹 Kunde inte radera %s: %s", path, e)
                        keep.append(item)
                        referenced.add(disk_name)
                        continue
                else:
                    # dry_run: filen ligger kvar på disk men är redan bokförd
                    # här — markera den som refererad så orphan-svepet nedan
                    # inte räknar samma fil en andra gång.
                    referenced.add(disk_name)
                stats["removed_files"] += 1
                stats["removed_entries"] += 1
                stats["freed_bytes"] += int(size or 0)
                changed = True
            else:
                keep.append(item)
                referenced.add(disk_name)

        if len(keep) != len(gal):
            # Den aktiva bilden ligger kvar i keep — hitta dess nya index.
            new_active = 0
            if gal and active_idx < len(gal):
                active_item = gal[active_idx]
                if active_item in keep:
                    new_active = keep.index(active_item)
            entry["gallery"] = keep
            entry["gallery_index"] = new_active
            _sync_active(entry)
            if not keep:
                avatars.pop(key, None)

    # ── Föräldralösa filer: ligger i avatars/ men refereras inte av staten ──
    for f in av_dir.iterdir():
        if not f.is_file() or f.name in referenced:
            continue
        try:
            age_s = (now - datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)).total_seconds()
            if age_s < ORPHAN_GRACE_SECONDS:
                continue
            size = f.stat().st_size
            if not dry_run:
                f.unlink()
            stats["removed_files"] += 1
            stats["orphans"] += 1
            stats["freed_bytes"] += size
        except OSError as e:
            logger.debug("🧹 Kunde inte radera föräldralös %s: %s", f, e)

    if changed and not dry_run:
        state["avatars"] = avatars
        try:
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        except OSError as e:
            logger.warning("🧹 Kunde inte spara %s: %s", state_path, e)

    return stats


def purge_user_avatars(
    user_avatars_dir: Path,
    *,
    older_than_days: int = PURGE_AFTER_DAYS,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict:
    """Samma städning för kontots profilporträtt (user_avatars/<user>.json)."""
    now = now or _now()
    stats = {"removed_files": 0, "removed_entries": 0, "freed_bytes": 0, "orphans": 0}
    if not user_avatars_dir.is_dir():
        return stats

    referenced: set[str] = set()

    for jf in user_avatars_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        gal = data.get("gallery")
        if not isinstance(gal, list) or not gal:
            continue
        active_idx = int(data.get("gallery_index") or 0) % len(gal)
        keep: list = []
        for i, item in enumerate(gal):
            disk_name = item.get("disk_name")
            if not disk_name:
                continue
            path = user_avatars_dir / disk_name
            age = _item_age_days(item, path, now)
            if i != active_idx and age >= older_than_days:
                size = _file_size(path, item)
                if not dry_run:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        keep.append(item)
                        referenced.add(disk_name)
                        continue
                else:
                    referenced.add(disk_name)
                stats["removed_files"] += 1
                stats["removed_entries"] += 1
                stats["freed_bytes"] += int(size or 0)
            else:
                keep.append(item)
                referenced.add(disk_name)

        if len(keep) != len(gal):
            active_item = gal[active_idx]
            data["gallery"] = keep
            data["gallery_index"] = keep.index(active_item) if active_item in keep else 0
            if not dry_run:
                try:
                    jf.write_text(json.dumps(data, ensure_ascii=False, indent=2))
                except OSError:
                    pass

    # Legacy-filen <user>.png refereras inte av galleriet men används som
    # fallback i _load_user_avatar_gallery() → skydda den alltid.
    for jf in user_avatars_dir.glob("*.json"):
        referenced.add(jf.stem + ".png")

    for f in user_avatars_dir.iterdir():
        if not f.is_file() or f.suffix == ".json" or f.name in referenced:
            continue
        try:
            age_s = (now - datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)).total_seconds()
            if age_s < ORPHAN_GRACE_SECONDS:
                continue
            size = f.stat().st_size
            if not dry_run:
                f.unlink()
            stats["removed_files"] += 1
            stats["orphans"] += 1
            stats["freed_bytes"] += size
        except OSError:
            pass

    return stats


def purge_all(
    campaigns_dir: Path,
    user_avatars_dir: Path | None = None,
    *,
    older_than_days: int = PURGE_AFTER_DAYS,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict:
    """Kör städningen över ALLA kampanjer + kontoporträtt."""
    now = now or _now()
    total: dict = {
        "campaigns": 0, "removed_files": 0, "removed_entries": 0,
        "freed_bytes": 0, "orphans": 0,
    }
    if campaigns_dir.is_dir():
        # Glob:en är medvetet exakt två nivåer djup (user/campaign/state.json).
        # En legacy-katalog som data/campaigns/boblin/boblin/<cid>/ ligger på
        # djup 3 och skannas INTE — den rörs hellre inte alls än städas fel.
        for state_path in campaigns_dir.glob("*/*/state.json"):
            s = purge_campaign(
                state_path, older_than_days=older_than_days, dry_run=dry_run, now=now,
            )
            total["campaigns"] += 1
            for k in ("removed_files", "removed_entries", "freed_bytes", "orphans"):
                total[k] += s[k]

    if user_avatars_dir is not None:
        s = purge_user_avatars(
            user_avatars_dir, older_than_days=older_than_days, dry_run=dry_run, now=now,
        )
        for k in ("removed_files", "removed_entries", "freed_bytes", "orphans"):
            total[k] += s[k]

    total["freed_mb"] = round(total["freed_bytes"] / (1024 * 1024), 2)
    total["dry_run"] = dry_run
    logger.info(
        "🧹 Avatar purge%s: %d filer bort (%d inaktiva + %d föräldralösa) "
        "över %d kampanjer — %.1f MB frigjort",
        " [DRY RUN]" if dry_run else "", total["removed_files"],
        total["removed_entries"], total["orphans"], total["campaigns"],
        total["freed_mb"],
    )
    return total
