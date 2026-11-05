"""Dependency watch: has Workshop BaseLib or the game's public build moved since last week?

GitHub issue #2: the mod shipped compiled against BaseLib 3.2.1 while every Workshop subscriber had been on
3.4.7 for weeks. BaseLib minor versions are source-compatible, not binary-compatible, so a stale mod DLL
breaks silently when BaseLib updates. Policy (docs/plans/GITHUB_ISSUES_1_2_FIX_PLAN.md, "BaseLib dependency
policy", step 4): check Steam's `time_updated` for the BaseLib Workshop item and the game's public build every
week, in the Monday digest (tools/experiments_mail.py), so a change means "bump, rebuild, smoke, release"
within a day.

Stdlib only. No Steam API key is needed for either call. The last seen values live in a small JSON state file
(BTSWEB_DEP_WATCH_STATE, default <BTSWEB_TRAFFIC_DIR>/dep_watch.json next to experiments_mail.json):

    {"baselib_time_updated": 1789149503, "baselib_first_seen": "2026-11-09",
     "game_buildid": "23811903", "game_first_seen": "2026-11-09", "last_check": "2026-11-09"}

    python web/dep_watch.py            # print the digest section; state untouched
    python web/dep_watch.py --record   # ...and record what was seen (what the Monday digest does)
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASELIB_ITEM_ID = 3737335127
GAME_APP_ID = 2868840
USER_AGENT = "btsweb dep_watch (+https://blankthespire.com)"
WORKSHOP_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
STEAMCMD_URL = "https://api.steamcmd.net/v1/info/{app_id}"
DEFAULT_TRAFFIC_DIR = "/opt/btsweb/traffic"
POLICY_DOC = "docs/plans/GITHUB_ISSUES_1_2_FIX_PLAN.md"


def default_state_path() -> Path:
    env = os.environ.get("BTSWEB_DEP_WATCH_STATE")
    if env:
        return Path(env)
    return Path(os.environ.get("BTSWEB_TRAFFIC_DIR", DEFAULT_TRAFFIC_DIR)) / "dep_watch.json"


def enabled() -> bool:
    """BTSWEB_DEP_WATCH=0 turns the digest section off (the test suite sets it; no network in tests)."""
    return os.environ.get("BTSWEB_DEP_WATCH", "1").strip().lower() not in ("0", "false", "no", "off", "")


# --- fetchers ----------------------------------------------------------------------------------------------

def _get_json(req: urllib.request.Request, timeout: float):
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https URLs
        return json.loads(resp.read().decode("utf-8"))


def fetch_workshop_item(item_id: int, timeout: float = 10) -> dict:
    """{"item_id", "title", "time_updated" (epoch int)} for one public Workshop item. Raises on failure."""
    body = urllib.parse.urlencode({"itemcount": 1, "publishedfileids[0]": int(item_id)}).encode("ascii")
    req = urllib.request.Request(WORKSHOP_URL, data=body, method="POST",
                                 headers={"User-Agent": USER_AGENT,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    data = _get_json(req, timeout)
    files = ((data or {}).get("response") or {}).get("publishedfiledetails") or []
    if not files or int(files[0].get("result") or 0) != 1 or not files[0].get("time_updated"):
        raise ValueError(f"Workshop item {item_id} not returned (result {files[0].get('result') if files else '?'})")
    f = files[0]
    return {"item_id": int(f.get("publishedfileid") or item_id), "title": f.get("title") or "",
            "time_updated": int(f["time_updated"])}


def fetch_game_build(app_id: int = GAME_APP_ID, timeout: float = 10) -> dict | None:
    """{"buildid": str, "timeupdated": int | None} for the public branch, or None on ANY failure."""
    try:
        req = urllib.request.Request(STEAMCMD_URL.format(app_id=int(app_id)), headers={"User-Agent": USER_AGENT})
        data = _get_json(req, timeout)
        public = data["data"][str(app_id)]["depots"]["branches"]["public"]
        buildid = str(public["buildid"])
        tu = public.get("timeupdated")
        return {"buildid": buildid, "timeupdated": int(tu) if tu not in (None, "") else None}
    except Exception:  # noqa: BLE001 — the digest must never break on this
        return None


# --- check -------------------------------------------------------------------------------------------------

def _read_state(path: Path) -> dict:
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
        return st if isinstance(st, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _part(current, previous, first_seen: str | None, error: str | None) -> dict:
    return {"current": current, "previous": previous, "first_seen": first_seen, "error": error,
            "first_run": error is None and previous is None,
            "changed": error is None and previous is not None and current != previous}


def check(now: datetime.date | datetime.datetime | None = None, state_path: Path | str | None = None,
          fetch_item=None, fetch_build=None, write: bool = True) -> dict:
    """Fetch both values, compare them with the state file, and (``write``) record what was seen.

    Returns {"baselib": part, "game": part, "state": new_state, "state_path": str, "today": "YYYY-MM-DD"};
    each part is {"current", "previous", "first_seen", "error", "first_run", "changed"}. A failed fetch
    leaves that item's recorded value alone (``error`` says why). ``write=False`` lets a caller commit
    later with ``commit(result)`` — tools/experiments_mail.py does, only once the digest actually went out,
    so a failed send re-reports the change next run instead of swallowing it."""
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    today = (now.date() if isinstance(now, datetime.datetime) else now).isoformat()
    fetch_item = fetch_item or fetch_workshop_item   # resolved per call so tests can monkeypatch the module
    fetch_build = fetch_build or fetch_game_build
    path = Path(state_path) if state_path is not None else default_state_path()
    old = _read_state(path)
    new = dict(old)

    item, item_err = None, None
    try:
        item = fetch_item(BASELIB_ITEM_ID)
        if not item or item.get("time_updated") is None:
            raise ValueError("no time_updated")
    except Exception as e:  # noqa: BLE001
        item, item_err = None, f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
    build, build_err = None, None
    try:
        build = fetch_build()
    except Exception as e:  # noqa: BLE001 — injected fetchers may raise; the real one returns None
        build_err = f"{type(e).__name__}: {e}"
    if build is None and build_err is None:
        build_err = "steamcmd.net info unavailable"

    prev_tu = old.get("baselib_time_updated")
    if item is not None:
        cur_tu = int(item["time_updated"])
        baselib = _part(cur_tu, prev_tu, old.get("baselib_first_seen"), None)
        if prev_tu != cur_tu:
            new["baselib_time_updated"], new["baselib_first_seen"] = cur_tu, today
            baselib["first_seen"] = today
        new["baselib_title"] = item.get("title") or new.get("baselib_title")
    else:
        baselib = _part(None, prev_tu, old.get("baselib_first_seen"), item_err)

    prev_b = old.get("game_buildid")
    if build is not None:
        cur_b = str(build["buildid"])
        game = _part(cur_b, prev_b, old.get("game_first_seen"), None)
        game["timeupdated"] = build.get("timeupdated")
        if prev_b != cur_b:
            new["game_buildid"], new["game_first_seen"] = cur_b, today
            game["first_seen"] = today
    else:
        game = _part(None, prev_b, old.get("game_first_seen"), build_err)

    new["last_check"] = today
    result = {"baselib": baselib, "game": game, "state": new, "state_path": str(path), "today": today}
    if write:
        commit(result)
    return result


def commit(result: dict) -> bool:
    """Record ``result["state"]``. False (never raises) when the file cannot be written."""
    try:
        _write_state(Path(result["state_path"]), result["state"])
        return True
    except OSError as e:
        print(f"dep watch: could not write {result.get('state_path')}: {e}", file=sys.stderr)
        return False


def any_changed(result: dict | None) -> bool:
    return bool(result) and any((result.get(k) or {}).get("changed") for k in ("baselib", "game"))


# --- digest text -------------------------------------------------------------------------------------------

def _date(epoch) -> str:
    try:
        return datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def digest_section(result: dict | None) -> str:
    """The digest's dependency block: one quiet line when nothing moved, loud ``!!`` lines when it did."""
    if not result:
        return "dep watch: unavailable (no result)"
    b, g = result.get("baselib") or {}, result.get("game") or {}
    if b.get("error") and g.get("error"):
        return f"dep watch: unavailable ({b['error']}; {g['error']})"
    loud: list[str] = []
    quiet: list[str] = []
    label = f"BaseLib (Workshop {BASELIB_ITEM_ID})"
    if b.get("error"):
        quiet.append(f"{label}: unavailable ({b['error']}).")
    elif b.get("changed"):
        loud.append(f"!! BaseLib UPDATED {_date(b['current'])} (was {_date(b['previous'])}) -> bump "
                    f"Alchyr.Sts2.BaseLib in mod/BlankTheSpire.csproj, rebuild, one AutoSlay smoke, release "
                    f"(see {POLICY_DOC} policy).")
    elif b.get("first_run"):
        quiet.append(f"{label}: first run, baseline recorded (last updated {_date(b['current'])}).")
    else:
        quiet.append(f"{label}: unchanged, last updated {_date(b['current'])}.")
    if g.get("error"):
        quiet.append(f"Game build: unavailable ({g['error']}).")
    elif g.get("changed"):
        loud.append(f"!! Game build changed {g['previous']} -> {g['current']}: expect a BaseLib release; "
                    f"re-check the Workshop item")
    elif g.get("first_run"):
        quiet.append(f"Game build: {g['current']}, first run, baseline recorded.")
    else:
        quiet.append(f"Game build: {g['current']}, unchanged.")
    lines = loud + ([" ".join(quiet)] if quiet else [])
    return "\n".join(lines)


def safe_section(state_path: Path | str | None = None, write: bool = False, **kw) -> tuple[str, dict | None]:
    """(section text, result or None) — never raises; anything unexpected becomes the "unavailable" line."""
    try:
        result = check(state_path=state_path, write=write, **kw)
        return digest_section(result), result
    except Exception as e:  # noqa: BLE001
        return f"dep watch: unavailable ({type(e).__name__}: {e})", None


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Print the dependency-watch digest section.")
    ap.add_argument("--state", default=None, help="state file (default $BTSWEB_DEP_WATCH_STATE or "
                                                  "<BTSWEB_TRAFFIC_DIR>/dep_watch.json)")
    ap.add_argument("--record", action="store_true", help="record what was seen in the state file")
    args = ap.parse_args(argv)
    text, result = safe_section(state_path=args.state, write=args.record)
    print(text)
    if result is not None:
        b, g = result["baselib"], result["game"]
        print(f"(BaseLib time_updated={b['current']} previous={b['previous']}; game buildid={g['current']} "
              f"previous={g['previous']}; state {result['state_path']}{'' if args.record else ', not written'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
