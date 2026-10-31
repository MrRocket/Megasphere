#!/usr/bin/env python3
"""
Fetches the Zandronum and Q-Zandronum server lists from doomlist.net and writes a slimmed-down
servers.json. A GitHub Action runs this every few minutes and publishes the result to the
"data" branch, where the Megasphere page can read it as a backup when the live request fails.

Only the standard library is used, so there is nothing to install.
"""
import datetime
import json
import re
import sys
import urllib.request

SOURCES = [
    ("zandronum", "https://doomlist.net/api"),
    ("qzandronum", "https://q.doomlist.net/api"),
]

COLOR_CODES = re.compile(r"\x1c(\[[^\]]*\]|.)", re.S)
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def clean(value):
    """Strip Zandronum colour codes and control characters. Must match clean() in index.html."""
    if not isinstance(value, str):
        return ""
    value = COLOR_CODES.sub("", value)
    value = CONTROL_CHARS.sub("", value)
    return value.strip()[:200]


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def slim(e, engine):
    """Reduce one raw server entry to just the fields the page shows. Must match slim() in index.html."""
    if not isinstance(e, dict) or not isinstance(e.get("name"), str):
        return None
    addr, port = e.get("addr"), e.get("port")
    if not isinstance(addr, str) or not is_number(port):
        return None

    all_pwads = e.get("pwads") if isinstance(e.get("pwads"), list) else []
    pwads, qcde = [], False
    for w in all_pwads:
        if not isinstance(w, str):
            continue
        if re.search("qcde", w, re.I):
            qcde = True
        if len(pwads) < 12:
            pwads.append(clean(w))

    players = []
    playerdata = e.get("playerdata") if isinstance(e.get("playerdata"), list) else []
    for p in playerdata[:40]:
        if not isinstance(p, dict):
            continue
        n = clean(p.get("plain-name") or p.get("name") or "")
        if n:
            players.append({"n": n, "bot": bool(p.get("bot")), "spec": bool(p.get("spec"))})

    gm = e.get("gamemode")
    gametype = e.get("gametype")
    mode = clean(gm.get("name")) if isinstance(gm, dict) else ""
    mod = clean(e.get("mod"))
    if not mode:
        mode = mod
    if not mode and isinstance(gametype, dict):
        mode = clean(gametype.get("gamemode"))

    bots = e["numbots"] if is_number(e.get("numbots")) else 0
    if is_number(e.get("numhumans")):
        humans = e["numhumans"]
    else:
        humans = max(0, (e["numplayers"] if is_number(e.get("numplayers")) else 0) - bots)
    if is_number(e.get("maxplayers")):
        maxp = e["maxplayers"]
    elif is_number(e.get("maxclients")):
        maxp = e["maxclients"]
    else:
        maxp = 0

    url = e.get("url") if isinstance(e.get("url"), str) and re.match(r"^https?://", e["url"], re.I) else ""
    loc = e.get("location")

    return {
        "engine": engine,
        "name": clean(e["name"]) or "%s:%s" % (addr, int(port)),
        "addr": addr,
        "port": port,
        "mode": mode,
        "mod": mod,
        "map": clean(e.get("mapname")),
        "iwad": clean(e.get("iwad")),
        "humans": humans,
        "bots": bots,
        "specs": e["numspec"] if is_number(e.get("numspec")) else 0,
        "max": maxp,
        "password": bool(e.get("forcepassword") or e.get("forcejoinpassword")),
        "version": clean(e.get("version")),
        "country": clean(loc.get("code")) if isinstance(loc, dict) else "",
        "url": url[:300],
        "pwads": pwads,
        "npwads": len(all_pwads),
        "players": players,
        "qcde": qcde,
    }


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MegasphereServerList/1.0 (+https://mrrocket.github.io/Megasphere/)"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build(fetcher=fetch):
    servers, status, any_ok = [], {}, False
    for engine, url in SOURCES:
        try:
            data = fetcher(url)
            found = [s for s in (slim(v, engine) for v in data.values()) if s]
            servers.extend(found)
            status[engine] = {"ok": True, "count": len(found)}
            any_ok = True
        except Exception as exc:  # network error, bad JSON, site down...
            print("Could not read %s: %s" % (url, exc), file=sys.stderr)
            status[engine] = {"ok": False, "count": 0}
    servers.sort(key=lambda s: (-s["humans"], s["name"].lower()))
    return any_ok, {
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": status,
        "servers": servers,
    }


def main():
    ok, result = build()
    if not ok:
        print("Both lists failed, keeping the previous servers.json.", file=sys.stderr)
        return 1
    with open("servers.json", "w", encoding="utf-8") as f:
        json.dump(result, f, separators=(",", ":"), ensure_ascii=False)
    print("Wrote %d servers." % len(result["servers"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
