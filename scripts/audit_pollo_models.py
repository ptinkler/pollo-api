#!/usr/bin/env python3
"""Audit our Pollo model catalogue against the docs and against a live key.

Two independent signals decide what to list and how to configure each model —
neither is enough alone, as our Seedance models prove (they work but aren't in
the public spec):

  1. DOCUMENTED?  Pollo's OpenAPI spec (docs.pollo.ai/openapi.json) is the
     source of truth for a model's FEATURES — whether it has a reference-to-
     video branch, the refs cap, allowed ref types, durations, resolutions,
     ratios. This script extracts those and diffs them against our registry
     (web/providers/pollo_engine/v1_video.py VIDEO_MODELS + pollo_models.MODEL_INFO)
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
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.probe_pollo_models import _probe_estimate
from web.providers.pollo_engine.video import VIDEO_MODELS
from web.providers.pollo_models import MODEL_INFO

if TYPE_CHECKING:
    from web.types import JsonValue

SPEC_URL = "https://docs.pollo.ai/openapi.json"
# Per-type ref caps live in the free-text "constraints" of the refs description;
# pull the common phrasings so the audit can compare them to our ref_mode limits.
_LIMIT_PATTERNS = {
    "image": re.compile(r"(?:up to|most)\s+(\d+)\s+image", re.IGNORECASE),
    "video": re.compile(r"(?:up to|most)\s+(\d+)\s+(?:reference\s+)?video", re.IGNORECASE),
    "audio": re.compile(r"(?:up to|most)\s+(\d+)\s+(?:audio|voice)", re.IGNORECASE),
}


def _load_spec(path_or_none: str | None) -> dict:
    if path_or_none:
        with Path(path_or_none).open(encoding="utf-8") as f:
            return json.load(f)
    print(f"Fetching {SPEC_URL} (~10 MB)…", file=sys.stderr)
    with urllib.request.urlopen(SPEC_URL, timeout=60) as resp:
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
    """Our video registry keyed by Pollo model slug (MODEL)."""
    out = {}
    for key, cfg in VIDEO_MODELS.items():
        slug = cfg.get("MODEL")
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
    return {k: _probe_estimate(k, api_key)[0] for k in keys}


# ── --write: safe, surgical edits to our source (you review the git diff) ──
# Only the mechanical, derivable fields are touched: `hidden` (enablement) and
# `ref_mode` in pollo_models.py, and `HAS_REFS` in v1_video.py. Curated bits —
# labels, deliberate "Superseded" hides, ref_mode's own quirks like
# `no_audio_with_video` — are merged around, never overwritten.
_REMOVE = object()
_REPO = Path(__file__).resolve().parent.parent  # repo root
_RUFF = shutil.which("ruff")
MODELS_FILE = _REPO / "web" / "providers" / "pollo_models.py"
ENGINE_FILE = _REPO / "web" / "providers" / "pollo_engine" / "v1_video.py"
# A hide we may clear is one justified by enablement; a deliberate hide is kept.
_ENABLEMENT_HIDE = re.compile(r"enabled|403|404|unavailable|access", re.IGNORECASE)


def py_literal(v: JsonValue) -> str:
    """A Python literal using double quotes and True/False (ruff-style)."""
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, dict):
        return "{" + ", ".join(f'"{k}": {py_literal(x)}' for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(py_literal(x) for x in v) + "]"
    if isinstance(v, str):
        return '"' + v.replace('"', '\\"') + '"'
    return str(v)


def _block_range(lines: list[str], key: str) -> tuple[int, int] | None:
    """Find a block's first and last line indices.

    A one-line `    "key": {…},` entry returns (i, i).
    """
    opener = re.compile(r'^    "' + re.escape(key) + r'": \{')
    for i, ln in enumerate(lines):
        if opener.match(ln):
            if sum(ln.count(c) for c in "{[") - sum(ln.count(c) for c in "}]") <= 0:
                return i, i  # balanced on one line
            for j in range(i + 1, len(lines)):
                if re.match(r"^    \},?$", lines[j]):
                    return i, j
            return None
    return None


def _edit_inline(line: str, field: str, val: str) -> str:
    """Add or replace a member inside a one-line dictionary entry.

    Inline values cannot carry comments, so any comment is dropped.
    """
    val = re.sub(r"\s+#.*$", "", val)
    m = re.match(r'^(\s*".*?": \{)(.*?)(\},?\s*)$', line)
    prefix, inner, suffix = m.group(1), m.group(2).rstrip(), m.group(3)
    existing = re.search(r'("' + re.escape(field) + r'": )[^,}]+', inner)
    if existing:
        inner = inner[: existing.start(1)] + existing.group(1) + val + inner[existing.end() :]
    else:
        inner = f'{inner}{", " if inner else ""}"{field}": {val}'
    return f"{prefix}{inner}{suffix}"


def _field_range(lines: list[str], start: int, end: int, field: str) -> tuple[int, int] | None:
    """Find a field's first and last line indices.

    Multi-line dict and list values are followed to their closing line by brace balance.
    """
    pat = re.compile(r'^        "' + re.escape(field) + r'":')
    for i in range(start + 1, end):
        if pat.match(lines[i]):
            depth = 0
            for j in range(i, end):
                depth += sum(lines[j].count(c) for c in "{[") - sum(lines[j].count(c) for c in "}]")
                code = re.sub(r"\s+#.*$", "", lines[j])  # ignore a trailing comment
                if depth <= 0 and code.rstrip().endswith(","):
                    return i, j
            return i, i
    return None


def apply_edits(path: str, edits: dict[str, dict], warnings: list[str]) -> int:
    """Apply model-field edits to a source file and return the edit count.

    Re-scan after each change so line indices stay valid.
    """
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    n = 0
    for key, fields in edits.items():
        for field, val in fields.items():
            blk = _block_range(lines, key)
            if not blk:
                warnings.append(f"{Path(path).name}: {key!r} not found — skipped {field}")
                continue
            s, e = blk
            if s == e:  # one-line inline entry
                if val is not _REMOVE:
                    lines[s] = _edit_inline(lines[s], field, val)
                    n += 1
                continue
            fr = _field_range(lines, s, e, field)
            if val is _REMOVE:
                if fr:
                    del lines[fr[0] : fr[1] + 1]
                    n += 1
                continue
            # The comma terminates the member and must sit before any trailing
            # comment, else it gets commented out and breaks the dict.
            cm = re.match(r"^(.*?)(\s+#.*)$", val)
            newline = f'        "{field}": {cm.group(1)},{cm.group(2)}' if cm else f'        "{field}": {val},'
            if fr:
                lines[fr[0] : fr[1] + 1] = [newline]
            else:
                lines.insert(s + 1, newline)
            n += 1
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return n


def plan_writes(ours: dict, docs: dict[str, dict], enabled: dict[str, str]) -> tuple[dict, dict, list[str]]:
    """Plan source edits and human-only notes from the model audit.

    Add or update ``ref_mode`` from docs but never remove it because the spec is
    incomplete; clear hides only when they were justified by enablement.
    """
    models_edits: dict[str, dict] = {}
    engine_edits: dict[str, dict] = {}
    notes: list[str] = []
    today = datetime.now().astimezone().date().isoformat()
    for slug, o in ours.items():
        key, info, d = o["key"], o["info"], docs.get(slug)
        # Enablement → hidden (needs the probe)
        verdict = enabled.get(key)
        hide = info.get("hidden")
        if verdict == "ENABLED" and hide and _ENABLEMENT_HIDE.search(hide):
            models_edits.setdefault(key, {})["hidden"] = _REMOVE
        elif verdict == "DISABLED" and not hide:
            reason = f'"Not enabled for API access on this key (403)"  # audit {today}'
            models_edits.setdefault(key, {})["hidden"] = reason
        # Features → ref_mode (+ engine HAS_REFS), merged so curated keys survive
        doc_refs = d.get("refs") if d else None
        if doc_refs:
            cur = info.get("ref_mode") or {}
            merged = {**cur, "types": doc_refs["types"], "max": doc_refs["max"]}
            if doc_refs.get("limits"):
                merged["limits"] = doc_refs["limits"]
            if merged != cur:
                models_edits.setdefault(key, {})["ref_mode"] = py_literal(merged)
            if not o["cfg"].get("HAS_REFS"):
                engine_edits.setdefault(key, {})["HAS_REFS"] = "True"
        elif info.get("ref_mode"):
            notes.append(f"{key}: we declare ref_mode but docs show none — review by hand (may be a docs gap)")
    return models_edits, engine_edits, notes


def _write(ours: dict, docs: dict, enabled: dict) -> None:
    """Apply the mechanical fixes to our source, then report; you review the diff."""
    models_edits, engine_edits, notes = plan_writes(ours, docs, enabled)
    warnings: list[str] = []
    n = apply_edits(str(MODELS_FILE), models_edits, warnings) + apply_edits(str(ENGINE_FILE), engine_edits, warnings)
    for w in warnings:
        print(f"  ! {w}")
    if notes:
        print("\nHand-review (not auto-applied):")
        for note in notes:
            print(f"  - {note}")
    # Re-flow to our formatting; harmless if ruff isn't installed.
    with contextlib.suppress(Exception):
        subprocess.run(
            [_RUFF or "ruff", "format", str(MODELS_FILE), str(ENGINE_FILE)], cwd=_REPO, check=False, capture_output=True
        )
    print(f"\nApplied {n} edit(s) to pollo_models.py / v1_video.py. Review with `git diff` before committing.")


def main() -> int:
    """Audit the local model catalogue against Pollo's docs and API key."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", help="path to a saved openapi.json (else fetched from docs.pollo.ai)")
    ap.add_argument("--key", default=os.getenv("POLLO_API_KEY"), help="probe live availability (or POLLO_API_KEY)")
    ap.add_argument(
        "--write",
        action="store_true",
        help="apply the mechanical fixes (hidden/ref_mode/HAS_REFS) to our source — review the git diff after",
    )
    args = ap.parse_args()

    docs = parse_docs(_load_spec(args.spec))
    ours = _our_models()
    enabled = _enablement([v["key"] for v in ours.values()], args.key) if args.key else {}

    if args.write:
        _write(ours, docs, enabled)
        return 0

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
