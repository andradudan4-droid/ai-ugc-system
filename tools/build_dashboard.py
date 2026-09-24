#!/usr/bin/env python3
"""Export every shared artifact into one dashboard.json for the CRM front end.

    python3 tools/build_dashboard.py            # -> shared/data/dashboard.json

Read-only. Touches nothing it does not own. The front end consumes ONLY this file,
so the UI never has to understand the repo's layout, and changing the layout does not
break the UI.
"""

import csv, json, pathlib, re, datetime as dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
SH = ROOT / "shared"
D = SH / "data"

ROLES = [
    ("Strategy", "—",              "Decides scope, reviews findings, resolves blocks"),
    ("Writer",   "Agent 0, 3",     "Brand intake and scriptwriting"),
    ("Miner",    "Agent 1, 2",     "Ad mining and angle taxonomy"),
    ("Producer", "Agent 4, 5",     "Render queue and quality gate"),
    ("Outreach", "Agent 7",        "Drafts outreach. Never sends."),
]

# Pipeline stages, in order. A brand's stage is the furthest one it has reached.
STAGES = ["prospect", "researched", "scripted", "drafted", "pitched", "client"]


def read_status():
    """Parse the append-only status log into structured events."""
    p = SH / "STATUS.md"
    if not p.exists():
        return []
    out = []
    pat = re.compile(r"^(\S+)\s+(\w+)\s+(DONE|BLOCKED|NOOP|INFO|NOTE|FLAG|RESULT|CORRECTION)\s+(.*)$")
    for line in p.read_text().splitlines():
        m = pat.match(line.strip())
        if m:
            ts, role, state, detail = m.groups()
            out.append({"ts": ts, "role": role, "state": state, "detail": detail.strip()})
    return out


def read_targets():
    p = D / "targets.csv"
    if not p.exists():
        return []
    with p.open() as fh:
        return [r for r in csv.DictReader(fh) if r.get("brand")]


def stage_for(slug: str, has_scripts: set, has_outreach: set, pitched: set) -> str:
    if slug in pitched:      return "pitched"
    if slug in has_outreach: return "drafted"
    if slug in has_scripts:  return "scripted"
    if (D / "brands" / slug).exists(): return "researched"
    return "prospect"


def main() -> int:
    targets = read_targets()
    events = read_status()

    scripts_by_brand, script_rows = set(), []
    sp = D / "scripts.json"
    if sp.exists():
        raw = json.loads(sp.read_text())
        rows = raw.get("scripts", raw) if isinstance(raw, dict) else raw
        for s in rows:
            scripts_by_brand.add(s.get("brand_slug", ""))
            script_rows.append({
                "script_id": s.get("script_id"), "brand": s.get("brand_slug"),
                "angle": s.get("angle_id"), "hook": s.get("hook"),
                "product": s.get("product"), "ready": bool(s.get("client_ready")),
            })

    outreach = {p.stem for p in (D / "outreach").glob("*.md") if p.stem != "INDEX"} \
        if (D / "outreach").exists() else set()
    pitched = set()   # nothing sent yet — this is the honest state

    brands = []
    for r in targets:
        slug = (r.get("website", "") or "").replace("https://", "").replace("http://", "") \
                                           .strip("/").replace(".", "-")
        brands.append({
            "brand": r.get("brand"), "website": r.get("website"),
            "segment": r.get("segment"), "category": r.get("category_by_ads") or r.get("category"),
            "ad_count": int(r.get("ad_count") or 0),
            "ugc_est": int(r.get("ugc_ad_count_est") or r.get("ugc_ad_count") or 0),
            "newest_ad_days": r.get("newest_ad_days"),
            "score": float(r.get("fatigue_score") or 0),
            "stage": stage_for(slug, scripts_by_brand, outreach, pitched),
            "slug": slug,
        })
    brands.sort(key=lambda b: -b["score"])

    by_role = {}
    for e in events:
        by_role.setdefault(e["role"], []).append(e)
    agents = [{
        "role": name, "owns": owns, "does": does,
        "events": len(by_role.get(name, [])),
        "last": (by_role.get(name) or [{}])[-1].get("ts"),
        "blocked": sum(1 for e in by_role.get(name, []) if e["state"] == "BLOCKED"),
    } for name, owns, does in ROLES]

    prod = {}
    rq = D / "render_queue.json"
    if rq.exists():
        q = json.loads(rq.read_text())
        prod = {k: q.get(k) for k in
                ("dry_run", "spent_usd", "renders_produced", "attempt_cap_per_script", "warning")}

    funnel = {s: sum(1 for b in brands if b["stage"] == s) for s in STAGES}

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "stats": {
            "brands": len(brands),
            "researched": sum(1 for b in brands if b["stage"] != "prospect"),
            "scripts": len(script_rows),
            "scripts_ready": sum(1 for s in script_rows if s["ready"]),
            "hooks": sum(1 for _ in (D / "hooks.jsonl").open()) if (D / "hooks.jsonl").exists() else 0,
            "spent_usd": prod.get("spent_usd", 0),
        },
        "funnel": funnel,
        "agents": agents,
        "brands": brands,
        "scripts": script_rows,
        "activity": events[-60:],
        "production": prod,
    }
    (D / "dashboard.json").write_text(json.dumps(out, indent=2))
    print(f"wrote shared/data/dashboard.json")
    print(f"  {out['stats']['brands']} brands · {out['stats']['scripts']} scripts "
          f"({out['stats']['scripts_ready']} ready) · {out['stats']['hooks']} hooks")
    print(f"  funnel: " + " · ".join(f"{k}={v}" for k, v in funnel.items() if v))
    print(f"  agents: " + ", ".join(f"{a['role']}({a['events']}ev"
          + (f",{a['blocked']}blk" if a['blocked'] else "") + ")" for a in agents))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
