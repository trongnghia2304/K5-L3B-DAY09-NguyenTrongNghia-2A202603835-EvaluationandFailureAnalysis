"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]

    # 1. Aggregates must be finite numbers: NaN < min is False, so a NaN sails past a naive floor.
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (NaN/inf hides a crashed grader)")

    # 2. Grader crashes must not be dropped: no evaluator failures, no None/non-bool row values.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in the PR run")
    rows = pr.get("rows") or []
    bad_cells = [(r.get("item_id"), r.get("seed"), m) for r in rows for m in graded
                 if not isinstance(r.get(m), bool)]
    if bad_cells:
        problems.append(f"{len(bad_cells)} graded cell(s) are missing/None/not bool, first {bad_cells[0]}")

    # 3. Coverage: every (item, seed) of the baseline exactly once, as the manifest promises.
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    base_keys = [(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []]
    dupes = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dupes:
        problems.append(f"{len(dupes)} duplicated (item, seed) row(s), first {dupes[0]}")
    pm, bm = pr.get("manifest") or {}, base.get("manifest") or {}
    want = int(pm.get("items") or 0) * len(pm.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest promises {pm.get('items')} items x {len(pm.get('seeds') or [])} seeds = {want}")
    if (pm.get("items"), list(pm.get("seeds") or [])) != (bm.get("items"), list(bm.get("seeds") or [])):
        problems.append(f"manifest items/seeds {pm.get('items')}/{pm.get('seeds')} differ from baseline "
                        f"{bm.get('items')}/{bm.get('seeds')} (cherry-picked seeds or items)")
    missing, extra = set(base_keys) - set(keys), set(keys) - set(base_keys)
    if missing or extra:
        problems.append(f"(item, seed) set differs from baseline: {len(missing)} missing, {len(extra)} extra"
                        + (f", e.g. missing {sorted(missing, key=str)[0]}" if missing else ""))

    # 4. Slice membership is fixed by the label, not by the PR: compare per item with the baseline.
    def tags(rs: list[dict]) -> dict[str, set]:
        out: dict[str, set] = {}
        for r in rs:
            out.setdefault(r.get("item_id"), set()).update(r.get("slices") or [])
        return out
    pt, bt = tags(rows), tags(base.get("rows") or [])
    relabelled = sorted(i for i in set(pt) & set(bt) if pt[i] != bt[i])
    if relabelled:
        problems.append(f"slice tags changed vs baseline on {len(relabelled)} item(s), first {relabelled[0]}: "
                        f"{sorted(bt[relabelled[0]])} -> {sorted(pt[relabelled[0]])}")
    inconsistent = sorted({r.get("item_id") for r in rows
                           if set(r.get("slices") or []) != pt.get(r.get("item_id"), set())}, key=str)
    if inconsistent:
        problems.append(f"item {inconsistent[0]} carries different slice tags on different seeds")

    # 5. The reported aggregates must be what the rows say (a hand-edited number is a lie).
    if rows and not bad_cells:
        present = [m for m in graded if all(m in r for r in rows)]
        has_cost = all(isinstance(r.get("cost"), (int, float)) for r in rows)
        again = aggregate([{**r, "cost": r.get("cost", 0.0)} for r in rows], present,
                          k_values=spec.get("pass_k", []))
        for k, v in (pr.get("metrics") or {}).items():
            if k == "cost_per_success" and not has_cost:
                continue
            w = again.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) \
                    and isinstance(w, (int, float)) and abs(v - w) > 1e-6:
                problems.append(f"metric {k}={v} but its rows give {w} (aggregate edited by hand)")

    # 6. Ratchet: on the same eval set, a PR may only tighten the spec it is judged by.
    if base_spec is not None and (spec.get("eval_set_version") == base_spec.get("eval_set_version")
                                  or pm.get("eval_set_sha") == bm.get("eval_set_sha")):
        problems += [f"ratchet: {p}" for p in ratchet(spec, base_spec)]
    return problems


def _looser(new: dict, old: dict, where: str) -> list[str]:
    """Threshold/flag changes that make `new` easier to pass than `old`."""
    out = []
    nt, ot = new.get("threshold", new), old.get("threshold", old)
    for key in ("min",):
        if key in ot and (key not in nt or nt[key] < ot[key]):
            out.append(f"{where} {key} {ot[key]} -> {nt.get(key, 'removed')}")
    for key in ("max", "max_increase"):
        if key in ot and (key not in nt or nt[key] > ot[key]):
            out.append(f"{where} {key} {ot[key]} -> {nt.get(key, 'removed')}")
    if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
        out.append(f"{where} no_significant_drop dropped")
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"{where} no longer blocking")
    return out


def ratchet(spec: dict, base_spec: dict) -> list[str]:
    out = []
    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        if m["id"] not in new_m:
            out.append(f"metric {m['id']} removed")
        else:
            out += _looser(new_m[m["id"]], m, f"metric {m['id']}")
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        k = (s["name"], s["metric"])
        if k not in new_s:
            out.append(f"slice {k[0]}/{k[1]} removed")
        else:
            out += _looser(new_s[k], s, f"slice {k[0]}/{k[1]}")
    for key in ("seeds", "pass_k", "bootstrap"):
        if key in base_spec and spec.get(key) != base_spec.get(key):
            out.append(f"{key} changed {base_spec.get(key)} -> {spec.get(key)}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        sid = f"slice:{name}/{mid}"
        a, b = per_item(pr, mid, slice_name=name), per_item(base, mid, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"   # an empty slice cannot vouch for anything: never a silent pass
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict, note = "missing", "no shared items with baseline"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
