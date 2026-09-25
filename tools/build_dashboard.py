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

    # ---- per-brand detail: the research, hooks and drafts that make a row worth opening ----
    hooks_by_brand = {}
    hp = D / "hooks.jsonl"
    if hp.exists():
        for line in hp.read_text().splitlines():
            if not line.strip():
                continue
            try:
                h = json.loads(line)
            except Exception:
                continue
            hooks_by_brand.setdefault(h.get("brand", ""), []).append({
                "text": h.get("hook_text") or h.get("angle_evidence_text") or "",
                "angle": h.get("angle"), "days": h.get("days_running"),
                "source": h.get("hook_source"),
            })

    # angles.json groups by verdict: saturated / contested / single_brand
    angles_meta, self_assessment = {}, None
    ap = D / "angles.json"
    if ap.exists():
        try:
            raw = json.loads(ap.read_text())
            self_assessment = raw.get("self_assessment")
            for bucket in ("saturated_angles", "contested_angles", "single_brand_angles"):
                rows = raw.get(bucket) or []
                it = rows.items() if isinstance(rows, dict) else (
                    (a.get("angle_id") or a.get("angle"), a) for a in rows)
                for aid, a in it:
                    if not aid:
                        continue
                    a = a if isinstance(a, dict) else {}
                    angles_meta[aid] = {
                        "bucket": bucket.replace("_angles", ""),
                        "brands": a.get("brand_count") or len(a.get("brands", []) or []) or None,
                        "ads": a.get("ad_count") or a.get("ads"),
                        "max_days": a.get("max_days_running") or a.get("max_days"),
                        "note": a.get("note") or a.get("summary"),
                    }
        except Exception as e:
            angles_meta = {"_error": str(e)}

    detail = {}
    for b in brands:
        slug = b["slug"]
        md = D / "brands" / slug / "brand.md"
        note = None
        if md.exists():
            txt = md.read_text()
            secs = {}
            cur, buf = None, []
            for ln in txt.splitlines():
                if ln.startswith("## "):
                    if cur:
                        secs[cur] = "\n".join(buf).strip()
                    cur, buf = ln[3:].strip(), []
                elif cur:
                    buf.append(ln)
            if cur:
                secs[cur] = "\n".join(buf).strip()
            note = {k: v[:1200] for k, v in secs.items() if v}
        draft = D / "outreach" / f"{slug}.md"
        detail[slug] = {
            "research": note,
            "has_research": md.exists(),
            "hooks": hooks_by_brand.get(b["brand"], [])[:25],
            "scripts": [s for s in script_rows if s["brand"] == slug],
            "outreach_draft": draft.read_text()[:4000] if draft.exists() else None,
        }

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
        "detail": detail,
        "angles": angles_meta,
        "self_assessment": self_assessment,
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
