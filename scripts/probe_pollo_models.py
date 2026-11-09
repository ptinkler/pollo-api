#!/usr/bin/env python3
"""Probe which Pollo models are actually enabled for an API key.

Pollo gates models per key: a model shown in the picker can still answer 403
"not enabled for API access" (or 404 "Not found") when you submit. This maps
that out WITHOUT spending credits or uploading anything, by asking each model's
free `.../estimate` twin — the same endpoint the composer uses to price a
request (web/providers/pollo_estimate.py). The estimate takes the real request
body with placeholder media URLs and returns a price without starting a job.

    estimate accepted (a price came back)  -> ENABLED (at least for pricing)
    403 / "not enabled for API access"     -> DISABLED for this key
    404 "Not found"                        -> not available to this key
    anything else                          -> shown verbatim, decide yourself

Usage:
    POLLO_API_KEY=sk-... python scripts/probe_pollo_models.py            # motion/recast family
    python scripts/probe_pollo_models.py --key sk-... --family motion
    python scripts/probe_pollo_models.py --key sk-... --all-video        # every v1 video model
    python scripts/probe_pollo_models.py --key sk-... --live             # GROUND TRUTH: really submits, SPENDS CREDITS

The estimate probe is free but only proves the estimate endpoint is enabled.
A model can in principle gate generation separately; `--live` submits a real
job (one per enabled model, so it costs credits and takes time) to confirm.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

# Run from the repo root so `web` imports resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.providers.pollo_engine import GENERATORS_V1  # noqa: E402
from web.providers.pollo_engine import video_generator as get_video_generator  # noqa: E402
from web.providers.pollo_estimate import PLACEHOLDERS  # noqa: E402
from web.providers.pollo_models import MODEL_INFO  # noqa: E402

TIMEOUT = 20


def _models(family: str | None, all_video: bool) -> list[str]:
    """The v1 video model keys to probe, in catalogue order."""
    keys = []
    for key in GENERATORS_V1:
        info = MODEL_INFO.get(key, {})
        if all_video or (family and info.get("type") == family):
            keys.append(key)
    return keys


def _build(key: str, api_key: str):
    """A video generator for `key` with placeholder media, like the composer's
    estimate path does (web/providers/pollo.py estimate_cost)."""
    info = MODEL_INFO.get(key, {})
    cls = GENERATORS_V1[key]
    kw = {"api_key": api_key, "project": "probe", "prompt": "probe"}
    # A reference/first image when the model takes one; a source video when it
    # reads one. Motion/recast models take both.
    if getattr(cls, "ACCEPTS_IMAGES", True):
        kw["image_url"] = PLACEHOLDERS["image"]
    if info.get("video_input"):
        kw["video_url"] = PLACEHOLDERS["video"]
    if info.get("type") == "lipsync" or info.get("audio_input"):
        kw["audio_url"] = PLACEHOLDERS["audio"]
    return get_video_generator(key, **kw)


def _classify(status: int, text: str) -> tuple[str, str]:
    """(verdict, note) from an estimate response. The question is only whether
    the model is gated for this key — so anything that got PAST auth (a price,
    or a 400 rejecting our placeholder media) counts as ENABLED. Only an
    auth/enablement refusal (401/403/404/"not enabled") is DISABLED."""
    low = text.lower()
    if status == 401:
        return "KEY?", "401 — check the API key itself"
    if status in (403, 404) or "not enabled" in low or "not authorized" in low or "no access" in low:
        return "DISABLED", f"{status} / not enabled for API access on this key"
    if status == 200:
        return "ENABLED", "estimate priced the request"
    # Reached the model (past auth) but it rejected our fake placeholder media —
    # video-input models need a real video URL to price. Still proves the model
    # itself isn't gated for this key.
    return "ENABLED", f"reachable (HTTP {status}); placeholder media rejected: {text[:90]}"


def _probe_estimate(key: str, api_key: str) -> tuple[str, str]:
    try:
        gen = _build(key, api_key)
        payload = gen.get_payload()
    except Exception as e:  # noqa: BLE001 — a model whose probe body we can't build
        return "N/A", f"can't build a probe request: {e}"
    url = getattr(gen, "estimate_url", None)
    if not url:
        return "N/A", "no estimate endpoint for this model"
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        return "ERR", f"not reachable: {e}"
    return _classify(resp.status_code, resp.text)


def _probe_live(key: str, api_key: str) -> tuple[str, str]:
    """Really submit (SPENDS CREDITS on enabled models). Uses real placeholder
    URLs — Pollo will reject the fake media on some models even when enabled,
    which still proves the model itself isn't 403-gated."""
    gen = _build(key, api_key)
    try:
        resp = gen.send_request()
    except Exception as e:  # noqa: BLE001 — report whatever the generator raised
        return "ERR", str(e)[:140]
    try:
        body = resp.json()
    except ValueError:
        return _classify(resp.status_code, resp.text)
    task_id = (body.get("data") or {}).get("taskId") if isinstance(body.get("data"), dict) else None
    if task_id:
        return "ENABLED", f"accepted, taskId={task_id} (a job was created — may cost credits)"
    verdict, note = _classify(resp.status_code, resp.text)
    # A non-403 rejection (bad media, missing field) still means the model is reachable.
    if verdict not in ("DISABLED", "KEY?"):
        return "ENABLED", f"reachable, rejected inputs: {note}"
    return verdict, note


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", default=os.getenv("POLLO_API_KEY"), help="Pollo API key (or set POLLO_API_KEY)")
    ap.add_argument("--family", default="motion", help="model type to probe (default: motion/recast)")
    ap.add_argument("--all-video", action="store_true", help="probe every v1 video model, not just one family")
    ap.add_argument("--live", action="store_true", help="really submit — GROUND TRUTH, SPENDS CREDITS when enabled")
    args = ap.parse_args()

    if not args.key:
        ap.error("no API key — pass --key or set POLLO_API_KEY")

    keys = _models(None if args.all_video else args.family, args.all_video)
    if not keys:
        print(f"No models match family={args.family!r}.")
        return 1

    mode = "LIVE submit (spends credits)" if args.live else "free estimate probe"
    scope = "all v1 video models" if args.all_video else f"family={args.family!r}"
    print(f"Probing {len(keys)} models ({scope}) via {mode}\n")
    probe = _probe_live if args.live else _probe_estimate

    results = []
    for key in keys:
        label = MODEL_INFO.get(key, {}).get("label") or key
        verdict, note = probe(key, args.key)
        results.append((verdict, key, label, note))
        print(f"  {verdict:8}  {key:24}  {label:24}  {note}")

    enabled = sum(1 for r in results if r[0] == "ENABLED")
    print(f"\n{enabled}/{len(results)} enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
