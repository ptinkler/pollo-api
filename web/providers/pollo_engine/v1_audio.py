"""V1 audio API bodies: text-to-speech and text-to-music (Suno)."""

from __future__ import annotations

from typing import Any

from web.core.config import POLLO_API_V1_BASE

_AUDIO_DEFAULTS: dict[str, Any] = {
    "MAX_PROMPT": 3000,
    "NEEDS_VOICE": False,  # voiceId is required (ElevenLabs / MiniMax)
    "HAS_TUNING": False,  # speed / volume / pitch (Seed Audio)
    "HAS_DURATION": False,
}

# model_id -> overrides (plus V1_PROVIDER / V1_MODEL / endpoint / builder)
V1_AUDIO: dict[str, dict[str, Any]] = {
    "seedaudio10v1": {
        "V1_PROVIDER": "bytedance",
        "V1_MODEL": "seed-audio-1-0",
        "endpoint": "text2speech",
        "builder": "speech",
        "HAS_TUNING": True,
    },
    "minimaxspeech28hdv1": {
        "V1_PROVIDER": "minimax",
        "V1_MODEL": "speech-2-8-hd",
        "endpoint": "text2speech",
        "builder": "speech",
        "MAX_PROMPT": 5000,
        "NEEDS_VOICE": True,
    },
    "elevenv3v1": {
        "V1_PROVIDER": "elevenlabs",
        "V1_MODEL": "eleven-v3",
        "endpoint": "text2speech",
        "builder": "speech",
        "MAX_PROMPT": 5000,
        "NEEDS_VOICE": True,
    },
    "sunov45plusv1": {
        "V1_PROVIDER": "suno",
        "V1_MODEL": "suno-v4-5plus",
        "endpoint": "text2music",
        "builder": "music",
        "MAX_PROMPT": 5000,
    },
    "sunov5v1": {
        "V1_PROVIDER": "suno",
        "V1_MODEL": "suno-v5",
        "endpoint": "text2music",
        "builder": "music",
        "MAX_PROMPT": 5000,
    },
    "sunov55v1": {
        "V1_PROVIDER": "suno",
        "V1_MODEL": "suno-v5-5",
        "endpoint": "text2music",
        "builder": "music",
        "MAX_PROMPT": 5000,
        "HAS_DURATION": True,
    },
}


def _cfg(model_id: str) -> dict[str, Any]:
    return {**_AUDIO_DEFAULTS, **V1_AUDIO[model_id]}


def v1_audio_model_url(model_id: str) -> str:
    c = _cfg(model_id)
    return f"{POLLO_API_V1_BASE}/{c['V1_PROVIDER']}/{c['V1_MODEL']}/{c['endpoint']}"


def _clamp(value: Any, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _speech_payload(c: dict[str, Any], prompt: str, **kw) -> dict[str, Any]:
    attrs: dict[str, Any] = {"prompt": prompt}
    if c["NEEDS_VOICE"]:
        if not kw.get("voice"):
            raise ValueError("This speech model needs a voice")
        attrs["voiceId"] = kw["voice"]
    if c["HAS_TUNING"]:
        if kw.get("speed") is not None:
            attrs["speed"] = _clamp(kw["speed"], 0.5, 2)
        if kw.get("volume") is not None:
            attrs["volume"] = _clamp(kw["volume"], 0.5, 2)
        if kw.get("pitch") is not None:
            attrs["pitch"] = int(_clamp(kw["pitch"], -12, 12))
    return {"input": attrs}


def _music_payload(c: dict[str, Any], prompt: str, **kw) -> dict[str, Any]:
    """Suno: a song description, or (with style + title together) lyrics."""
    style, title = (kw.get("style") or "").strip(), (kw.get("title") or "").strip()
    if bool(style) != bool(title):
        raise ValueError("Style and title go together (lyrics mode) — give both or neither")
    attrs: dict[str, Any] = {"prompt": prompt}
    if style:
        attrs.update(style=style, title=title)
    if kw.get("negative_prompt"):
        attrs["negativePrompt"] = kw["negative_prompt"]
    if kw.get("instrumental") is not None:
        attrs["instrumental"] = bool(kw["instrumental"])
    if kw.get("vocal_gender") in ("m", "f") and not kw.get("instrumental"):
        attrs["vocalGender"] = kw["vocal_gender"]
    if c["HAS_DURATION"] and kw.get("duration"):
        attrs["duration"] = int(kw["duration"])
    return {"input": attrs}


def v1_audio_payload(model_id: str, *, prompt: str, **kw) -> dict[str, Any]:
    c = _cfg(model_id)
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Audio needs a prompt")
    if len(prompt) > c["MAX_PROMPT"]:
        raise ValueError(f"The prompt is too long for this model (max {c['MAX_PROMPT']} characters)")
    if c["builder"] == "speech":
        return _speech_payload(c, prompt, **kw)
    return _music_payload(c, prompt, **kw)
