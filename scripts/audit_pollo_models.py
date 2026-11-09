#!/usr/bin/env python3
"""Audit our Pollo model catalogue against the docs and against a live key.

Two independent signals decide what to list and how to configure each model —
neither is enough alone, as our Seedance models prove (they work but aren't in
the public spec):

  1. DOCUMENTED?  Pollo's OpenAPI spec (docs.pollo.ai/openapi.json) is the
     source of truth for a model's FEATURES — whether it has a reference-to-
     video branch, the refs cap, allowed ref types, durations, resolutions,
     ratios. This script extracts those and diffs them against our registry
     (web/providers/pollo_engine/v1_video.py V1_VIDEO + pollo_models.MODEL_INFO)
     so you never hand-find a model's feature set again.

  2. ENABLED ON YOUR KEY?  (--key / POLLO_API_KEY) The free estimate probe
     (scripts/probe_pollo_models.py) says which models actually answer for your
     key. This is the real show/hide signal: show = enabled, hide = 403/404,
     regardless of whether the model is documented.

Usage:
    # Feature diff only (fetches the ~10 MB spec, or pass a saved copy):
    python scripts/audit_pollo_models.py
    python scripts/audit_pollo_models.py --spec /path/to/openapi.json

    # Add the live availability column:
    python scripts/audit_pollo_models.py --key sk-...

Output per model: docs? | enabled? | refs(cap/types) | mismatches vs our config.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))  # repo root, for `web.*`
sys.path.insert(0, _HERE)  # this scripts/ dir, for the probe import

from web.providers.pollo_engine.v1_video import V1_VIDEO  # noqa: E402
from web.providers.pollo_models import MODEL_INFO  # noqa: E402

SPEC_URL = "https://docs.pollo.ai/openapi.json"
# Per-type ref caps live in the free-text "constraints" of the refs description;
# pull the common phrasings so the audit can compare them to our ref_mode limits.
_LIMIT_PATTERNS = {
    "image": re.compile(r"(?:up to|most)\s+(\d+)\s+image", re.I),
    "video": re.compile(r"(?:up to|most)\s+(\d+)\s+(?:reference\s+)?video", re.I),
    "audio": re.compile(r"(?:up to|most)\s+(\d+)\s+(?:audio|voice)", re.I),
}


def _load_spec(path_or_none: str | None) -> dict:
    if path_or_none:
        with open(path_or_none, encoding="utf-8") as f:
            return json.load(f)
    print(f"Fetching {SPEC_URL} (~10 MB)…", file=sys.stderr)
    with urllib.request.urlopen(SPEC_URL, timeout=60) as resp:  # noqa: S310 — fixed, trusted docs URL
        return json.loads(resp.read().decode("utf-8"))


def _resolve(spec: dict, node: dict) -> dict:
    """Follow a single $ref (one level is enough for these schemas)."""
    ref = node.get("$ref")
    if not ref:
        return node
    cur: dict = spec
    for part in ref.lstrip("#/").split("/"):
        cur = cur.get(part, {})
    return cur


def _ref_branch(spec: dict, input_schema: dict) -> dict | None:
    """The Reference-To-Video branch of an `input` oneOf — the one with refs."""
    for branch in input_schema.get("oneOf", []):
        b = _resolve(spec, branch)
        if "refs" in (b.get("properties") or {}):
            return b
    return None


def _enum(schema: dict, prop: str) -> list | None:
    p = (schema.get("properties") or {}).get(prop) or {}
    return p.get("enum")


def _docs_feature(spec: dict, op: dict) -> dict:
    """Extract one model's refs/durations/resolutions feature set from its POST op."""
    body = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
    body = _resolve(spec, body)
    input_schema = _resolve(spec, (body.get("properties") or {}).get("input") or {})
    feat: dict = {"refs": None}
    branch = _ref_branch(spec, input_schema)
    if branch:
        refs_prop = branch["properties"]["refs"]
        items = _resolve(spec, refs_prop.get("items") or {})
        desc = str(refs_prop.get("description") or "") + " " + str(branch.get("description") or "")
        limits = {k: int(m.group(1)) for k, pat in _LIMIT_PATTERNS.items() if (m := pat.search(desc))}
        feat["refs"] = {
            "max": refs_prop.get("maxItems"),
            "types": _enum(items, "type") or [t for t in ("image", "video", "audio") if t in desc],
            "limits": limits,
        }
    feat["resolutions"] = _enum(input_schema, "resolution")
    feat["ratios"] = _enum(input_schema, "aspectRatio")
    return feat


def parse_docs(spec: dict) -> dict[str, dict]:
    """{last path segment's model slug -> feature dict} for every POST generation path."""
    out: dict[str, dict] = {}
    for path, methods in (spec.get("paths") or {}).items():
        if "/generation/" not in path or "post" not in methods:
            continue
        # .../<provider>/<model-slug>/video  (slug is the identifying segment)
        parts = [p for p in path.split("/") if p]
        slug = parts[-2] if parts[-1] in ("video", "image", "audio") else parts[-1]
        out[slug] = {"path": path, **_docs_feature(spec, methods["post"])}
    return out


def _our_models() -> dict[str, dict]:
    """Our v1 video registry keyed by Pollo model slug (V1_MODEL)."""
    out = {}
    for key, cfg in V1_VIDEO.items():
        slug = cfg.get("V1_MODEL")
        if slug:
            out[slug] = {"key": key, "info": MODEL_INFO.get(key, {}), "cfg": cfg}
    return out


def _mismatches(ours: dict, docs: dict | None) -> list[str]:
    """Where our ref_mode config disagrees with the docs (empty = consistent)."""
    if not docs:
        return []
    msgs = []
    rm = ours["info"].get("ref_mode")
    doc_refs = docs.get("refs")
    if doc_refs and not rm:
        msgs.append(f"docs has refs (max {doc_refs['max']}) but we declare no ref_mode")
    elif rm and not doc_refs:
        msgs.append("we declare ref_mode but docs show no refs branch")
    elif rm and doc_refs:
        if doc_refs.get("max") and rm.get("max") != doc_refs["max"]:
            msgs.append(f"refs max ours={rm.get('max')} docs={doc_refs['max']}")
        for t, n in (doc_refs.get("limits") or {}).items():
            if (rm.get("limits") or {}).get(t) != n:
                msgs.append(f"{t} cap ours={(rm.get('limits') or {}).get(t)} docs={n}")
    return msgs


def _enablement(keys: list[str], api_key: str) -> dict[str, str]:
    """Live estimate probe (reuses probe_pollo_models) -> {our_key: verdict}."""
    from probe_pollo_models import _probe_estimate  # local script

    return {k: _probe_estimate(k, api_key)[0] for k in keys}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", help="path to a saved openapi.json (else fetched from docs.pollo.ai)")
    ap.add_argument("--key", default=os.getenv("POLLO_API_KEY"), help="probe live availability (or POLLO_API_KEY)")
    args = ap.parse_args()

    docs = parse_docs(_load_spec(args.spec))
    ours = _our_models()
    enabled = _enablement([v["key"] for v in ours.values()], args.key) if args.key else {}

    print(f"\n{'model (our key)':26} {'slug':22} docs enabled refs            notes")
    print("-" * 110)
    for slug, o in sorted(ours.items(), key=lambda kv: kv[1]["key"]):
        d = docs.get(slug)
        refs = d and d.get("refs")
        refs_s = f"{refs['max']}:{','.join(refs['types'] or [])}"[:15] if refs else "-"
        notes = "; ".join(_mismatches(o, d))
        if o["info"].get("hidden"):
            notes = (notes + "; " if notes else "") + "hidden in UI"
        print(f"{o['key']:26} {slug:22} {'Y' if d else '-':4} {enabled.get(o['key'], '?'):7} {refs_s:15} {notes}")

    # Models documented but absent from our registry — candidates to add.
    missing = sorted(set(docs) - set(ours))
    if missing:
        print("\nIn docs, not in our registry (candidates to add):")
        for slug in missing:
            r = docs[slug].get("refs")
            print(f"  {slug:28} {docs[slug]['path']}" + (f"  refs max {r['max']}" if r else ""))
    print(f"\n{len(ours)} models in registry, {len(docs)} documented, {len(missing)} documented-but-missing.")
    if enabled:
        print(f"{sum(1 for v in enabled.values() if v == 'ENABLED')}/{len(enabled)} enabled on this key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
