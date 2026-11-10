"""Building the model request and running generation: the chat-title helper,
conversation/history shaping, reference planning, moderation handling, and the
image/video submit primitives shared by turns and media retries."""

import json
import re
import uuid
from pathlib import Path
from typing import Any

from web.core.metadata import get_db

from .. import characters, providers, request_log
from ..providers import openrouter, pollo, provider_for
from ..uploads import file_to_data_url, is_blank_image
from .catalogue import _auto_ratio, _model_info
from .constants import DEFAULT_IMAGE_LIMIT, IMAGE_EXTS, TITLE_SECONDS
from .helpers import _conv_dir, _effective_ids
from .models import RefChoices
from .tools import AUDIO_TOOL_RESULT, IMAGE_TOOL_RESULT, TITLE_PROMPT, VIDEO_TOOL_RESULT

# Chat APIs don't accept images inside assistant messages, so images the
# model generated ride along with the next user message, after this label
CARRIED_LABEL = {
    "type": "text",
    "text": "[The images you generated in your previous reply, attached so you can see them]",
}


# Reasoning models wrap their thinking in these; it is never part of the answer.
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _ask(model: str, prompt: str, max_seconds: float) -> tuple[str, float]:
    """One short, non-streamed-to-the-UI completion: (the whole reply, its cost
    in USD). For the asides a turn makes on its own — naming a chat, rewriting
    a prompt — not for the chat itself, which streams (see Turn._stream_round)."""
    text, cost = "", 0.0
    for chunk in provider_for(model).stream_chat(model, [{"role": "user", "content": prompt}], max_seconds=max_seconds):
        usage = chunk.get("usage")
        if usage and usage.get("cost"):
            cost += float(usage["cost"])
        for choice in chunk.get("choices") or []:
            text += (choice.get("delta") or {}).get("content") or ""
    return text, cost


def _generate_title(model: str, prompt: str) -> tuple[str | None, float]:
    """(a short title for a chat starting with `prompt`, its cost in USD)."""
    text, cost = _ask(model, TITLE_PROMPT.format(prompt=prompt[:2000]), TITLE_SECONDS)
    return _clean_title(text), cost


ENHANCE_SECONDS = 45
ENHANCE_PROMPT = (
    "Rewrite the user's {kind} prompt into a richer, more specific one for an {kind} generation model: "
    "keep their intent, subjects and any style they named, and add concrete detail about composition, "
    "lighting, setting and mood. Reply with ONLY the improved prompt - no preamble, quotes or notes.\n\n"
    "Prompt: {prompt}"
)


def _enhance_prompt(model: str, prompt: str, kind: str) -> tuple[str, float]:
    """(the prompt rewritten by the chat model, its cost in USD). Raises
    ValueError when the model returns nothing usable."""
    text, cost = _ask(model, ENHANCE_PROMPT.format(kind=kind, prompt=prompt[:4000]), ENHANCE_SECONDS)
    text = _THINK.sub("", text).strip().strip("\"'`").strip()
    if not text:
        raise ValueError("The model returned no prompt")
    return text, cost


def _clean_title(text: str) -> str | None:
    """The model's reply as a title: its first line, without a "Title:" label,
    quotes, markdown or a full stop. None if nothing usable is left."""
    text = _THINK.sub("", text)
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    line = re.sub(r"^(?:\*\*)?title(?:\*\*)?\s*:\s*", "", line, flags=re.IGNORECASE)
    line = line.strip(" \t\"'`*#_“”‘’").rstrip(".").strip()
    if not line or len(line) > 80:
        return None
    return line


def _characters_note(attached: list) -> str:
    """What the chat model is told about the attached characters ('' when there are none)."""
    if not attached:
        return ""
    parts = ["The user has attached these characters to the chat:\n\n" + characters.describe(attached)]
    parts.append(
        "Whenever one of these characters is in an image or video you make, name them in the tool's "
        "`characters` argument: their description and reference images are then sent to the model "
        "for you, so they look the same as before."
    )
    return "\n\n".join(parts)


def _plan_refs(
    chat_refs: list[str],
    chars: list,
    image_limit: int | None,
    after: int | None = None,
    max_refs: int | None = None,
    choices: RefChoices | None = None,
) -> tuple[list[str], list[str]]:
    """The reference images to send, and those left out because the model
    takes fewer (`max_refs`, None = unknown). Chat images are capped at
    `image_limit` (None = all); character images aren't.

    They're sent in priority order, so a model that trims the list itself
    keeps the important ones too: the first `after` chat images (attachments,
    the edit source), the ones the user switched on in the composer, each
    character's main image, the other chat images (pins, recent), then the
    characters' other images. Images the user switched off never go."""
    on, off = (choices.on, set(choices.off)) if choices else ([], set())
    kept = [r for r in _dedupe(chat_refs) if r not in off]
    lead = kept if after is None else [r for r in _dedupe(chat_refs[:after]) if r not in off]
    chat_refs = kept[:image_limit]
    split = min(len(lead), len(chat_refs))
    every = characters.reference_refs(chars, skip=off)
    mains = characters.reference_refs(chars, per_character=1, skip=off)
    candidates = set(kept) | set(every)  # a switched-on chat image goes even over the slider
    ordered = _dedupe(chat_refs[:split] + [r for r in on if r in candidates] + mains + chat_refs[split:] + every)
    if max_refs is None:
        return ordered, []
    return ordered[:max_refs], ordered[max_refs:]


def _param_characters(params: dict) -> list:
    """The characters a media item was made with (deleted ones drop out)."""
    return characters.load(params.get("characters"), get_db())


def _ref_file(conv_id: str, ref: str) -> Path:
    """A reference image's file: a character image ("char:…") or a file in the chat."""
    return characters.ref_path(ref) or _conv_dir(conv_id) / ref


def _history_window(history: list, limit: int | None) -> list:
    """The last `limit` messages (None = all), starting on a user message so
    the model never sees a reply without the prompt that caused it."""
    if not limit or len(history) <= limit:
        return history
    window = history[-limit:]
    while window and window[0].role != "user":
        window = window[1:]
    return window or history[-1:]


def _conversation(
    conv_id: str,
    history: list,
    history_limit: int | None,
    vision: bool,
    as_tool_calls: bool = False,
    image_limit: int | None = DEFAULT_IMAGE_LIMIT,
) -> list[dict]:
    """The chat history as OpenRouter messages (no system prompt): the last
    `history_limit` messages, with the `image_limit` most recent images as
    pixels (None = all).
    Shared by the chat model and conversational image models.

    `as_tool_calls` (only when tools are offered — providers reject tool
    calls otherwise) records generated media as the tool calls and results
    that produced it; without it, media is summarised in bracketed notes."""
    history = _history_window(history, history_limit)
    pixels = _pixels_for(_conv_dir(conv_id), _pixel_files(history, image_limit if vision else 0))
    messages: list[dict] = []
    carried: list[dict] = []
    for msg in history:
        if msg.role == "user":
            parts = ([CARRIED_LABEL, *carried] if carried else []) + _user_parts(msg, pixels)
            carried = []
            if parts:
                messages.append({"role": "user", "content": parts})
        elif msg.role == "assistant":
            carried += [p for p in (pixels(i) for i in msg.media if i["kind"] == "image") if p]
            messages += _assistant_messages(msg, as_tool_calls)
    if carried:  # history ended on an assistant message
        messages.append({"role": "user", "content": [CARRIED_LABEL, *carried]})
    return messages


def _pixel_files(history: list, budget: int | None) -> set[str]:
    """The most recent `budget` images (None = all) — uploaded or generated —
    which go over as pixels so the model can see what's in them; older ones
    are described by a note instead."""
    images = [
        item["file"]
        for msg in reversed(history)
        for item in reversed(msg.media)
        if item["kind"] == "image" and item.get("file") and item.get("status", "done") == "done"
    ]
    return set(images if budget is None else images[:budget])


def _pixels_for(conv_dir: Path, files: set[str]):
    """A function giving an image item's pixels as a message part (None if it doesn't go as pixels)."""

    def pixels(item: dict) -> dict | None:
        f = item.get("file")
        if f in files and (conv_dir / f).is_file():
            return {"type": "image_url", "image_url": {"url": file_to_data_url(conv_dir / f)}}
        return None

    return pixels


def _user_parts(msg, pixels) -> list[dict]:
    parts = [{"type": "text", "text": msg.content}] if msg.content else []
    return parts + [pixels(item) or {"type": "text", "text": "[user attached an image]"} for item in msg.media]


def _assistant_messages(msg, as_tool_calls: bool) -> list[dict]:
    """A reply as messages: with its media as the tool calls that made it, or as notes in the text."""
    generated = [i for i in msg.media if i.get("source") == "generated" and i.get("prompt")]
    if as_tool_calls and generated:
        # Record what actually happened: the model's tool calls and the
        # results it got back — not text it could imitate
        return [
            {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [_history_tool_call(i) for i in generated],
            },
            *(
                {"role": "tool", "tool_call_id": f"call_{i['id']}", "content": json.dumps(_history_tool_result(i))}
                for i in generated
            ),
        ]
    text = "\n\n".join(filter(None, [msg.content or "", "\n".join(_media_note(item) for item in msg.media)]))
    return [{"role": "assistant", "content": text}] if text else []


def _image_context(
    conv_id: str,
    history: list,
    history_limit: int | None,
    reply_text: str,
    prompt: str | None,
    refs: list[str],
    instructions: str | None = None,
    chars: list | None = None,
    image_limit: int | None = DEFAULT_IMAGE_LIMIT,
) -> list[dict]:
    """What a conversational image model is sent: the conversation, then —
    when the chat model called the tool — its reply so far and its prompt,
    verbatim, with any reference images it asked for. In Image mode
    (prompt=None) the user's own message is already the last one."""
    messages = _conversation(conv_id, history, history_limit, vision=True, image_limit=image_limit)
    system = [s for s in (instructions, characters.describe(chars or [])) if s]
    messages[:0] = [{"role": "system", "content": s} for s in system]
    if prompt is not None:
        if reply_text.strip():
            messages.append({"role": "assistant", "content": reply_text.strip()})
        paths = [_ref_file(conv_id, f) for f in refs]
        parts: list[dict] = [{"type": "text", "text": prompt}]
        parts += [{"type": "image_url", "image_url": {"url": file_to_data_url(p)}} for p in paths if p.is_file()]
        messages.append({"role": "user", "content": parts})
    elif chars:
        # Image mode: the user's message is last; their characters' images go with it
        paths = [_ref_file(conv_id, f) for f in refs if f.startswith(characters.REF_PREFIX)]
        if paths and messages and messages[-1]["role"] == "user":
            messages[-1] = {
                **messages[-1],
                "content": messages[-1]["content"]
                + [{"type": "image_url", "image_url": {"url": file_to_data_url(p)}} for p in paths if p.is_file()],
            }
    return messages


def _conversation_instructions(conv_id: str) -> str | None:
    """The instructions a chat uses — its defaults' and its own — flattened for
    the model (user's text, verbatim): every snippet from the groups (in group
    order), then the single snippets — each sent once — joined by blank lines.
    None when nothing with content is attached."""
    db = get_db()
    conv = db.get_conversation(conv_id)
    if not conv:
        return None
    # Paused snippets/groups stay attached but are left out of what's sent
    paused = conv.paused_instructions
    paused_groups, paused_snippets = set(paused["instruction_group"]), set(paused["instruction"])
    snippet_ids: list[int] = []
    for gid in _effective_ids(conv, "instruction_group"):
        if gid in paused_groups:
            continue
        group = db.get_instruction_group(gid)
        if group:
            snippet_ids += group.snippet_ids
    snippet_ids += [sid for sid in _effective_ids(conv, "instruction") if sid not in paused_snippets]
    snippet_ids = list(dict.fromkeys(snippet_ids))  # a snippet in several groups is sent once
    parts = [s.content.strip() for s in db.get_instructions(snippet_ids) if s.content.strip()]
    return "\n\n".join(parts) or None


def _is_conversational(image_model: str | None) -> bool:
    info = _model_info("image", image_model)
    return bool(info and info.get("conversational"))


def _dedupe(files: list[str]) -> list[str]:
    return list(dict.fromkeys(files))


def _history_tool_call(item: dict) -> dict:
    params = item.get("params") or {}
    args: dict[str, Any] = {"prompt": item["prompt"]}
    if params.get("aspect_ratio"):
        args["aspect_ratio"] = params["aspect_ratio"]
    # Replay the reference choices too, so the history doesn't read as a
    # run of reference-free calls that the model then imitates
    if item["kind"] == "image":
        args.update(params.get("ref_args") or {})
    return {
        "id": f"call_{item['id']}",
        "type": "function",
        "function": {
            "name": f"generate_{item['kind']}",
            "arguments": json.dumps(args),
        },
    }


_TOOL_RESULTS = {"image": IMAGE_TOOL_RESULT, "audio": AUDIO_TOOL_RESULT}


def _history_tool_result(item: dict) -> dict:
    if item.get("status") == "error":
        return {"ok": False, "error": item.get("error") or "failed"}
    result: dict[str, Any] = {"ok": True, "result": _TOOL_RESULTS.get(item["kind"], VIDEO_TOOL_RESULT)}
    refs = (item.get("params") or {}).get("refs") or []
    if item["kind"] == "image" and refs:
        result["reference_images"] = len(refs)
    return result


def _media_note(item: dict) -> str:
    kind = item["kind"]
    if item.get("source") == "upload":
        return f"[user attached a {kind}]"
    state = {"done": f"generated {kind}", "pending": f"{kind} rendering", "error": f"{kind} failed"}[item["status"]]
    return f"[{state}: {item.get('prompt') or ''}]"


_MODERATION = re.compile(
    r"moderat|flagged|content[ _-]?polic|safety|nsfw|sexual|prohibited|violat|inappropriate|"
    r"sensitive content|not allowed|blocked",
    re.IGNORECASE,
)


def _is_moderation_error(e: openrouter.OpenRouterError) -> bool:
    """OpenRouter's own moderation returns 403; providers phrase their
    content-policy refusals in many ways, so also match on the message.
    Pollo's 403 means "model not enabled for API access", so for Pollo only
    the message counts."""
    if isinstance(e, pollo.PolloError):
        return bool(_MODERATION.search(str(e)))
    return e.status == 403 or bool(_MODERATION.search(str(e)))


def _failure_fields(e: openrouter.OpenRouterError) -> dict[str, Any]:
    """A failed media item's fields. Called right after the generation call,
    on its thread: what it sent and got back comes from the error, or — when
    the call itself worked but the result didn't (a Pollo task that failed, a
    black image) — from the request log."""
    fields = {"status": "error", "error": str(e), "moderated": _is_moderation_error(e)}
    return {**fields, **_exchange(getattr(e, "log_entry", None) or request_log.take_last())}


def _exchange(entry: dict | None) -> dict[str, Any]:
    """A request-log entry as media item fields: the body sent to the provider
    and what it answered, for the UI's "Request" view."""
    return {"request": entry.get("request"), "response": entry.get("response")} if entry else {}


def _take_log(result: dict) -> tuple[dict, dict[str, Any]]:
    """(a generation's settings/job, minus its request-log entry; that entry as media item fields)."""
    result = dict(result)
    return result, _exchange(result.pop("log", None))


BLACK_IMAGE_ERROR = (
    "Blocked by the model's content filter: it sent back a black image. "
    "Try again, soften the prompt, or pick another model (🔒 private or 🔞 uncensored ones "
    "don't filter like this)"
)


def _run_image_generation(
    conv_id: str, model: str, prompt: str, params: dict[str, Any], context: list[dict] | None = None
) -> tuple[list[str], float | None, int | None, dict[str, Any]]:
    """Generate and save images; returns (filenames, dollar cost, Pollo credits,
    the params actually sent — Pollo and Venice, defaults included — for display).
    With `context` (conversational models) the model gets the conversation;
    otherwise the Images API — or Pollo, or Venice — gets the prompt plus any reference images."""
    conv_dir = _conv_dir(conv_id)
    refs = [p for p in (_ref_file(conv_id, f) for f in params.get("refs") or []) if p.is_file()]
    if context is None:
        prompt = characters.with_characters(prompt, _param_characters(params))
    request_log.forget_last()
    # An unset ratio ("Ratio: auto") becomes the model's own auto value when it
    # has one, so it stays automatic instead of falling back to 16:9.
    aspect_ratio = params.get("aspect_ratio") or _auto_ratio("image", model)
    images, cost, credits, sent = providers.generate_image(
        model,
        prompt,
        aspect_ratio=aspect_ratio,
        resolution=params.get("resolution"),
        ref_paths=refs,
        context=context,
        session_id=conv_id,
    )
    kept = [(data, media_type) for data, media_type in images if not is_blank_image(data)]
    if images and not kept:
        raise openrouter.OpenRouterError(BLACK_IMAGE_ERROR)
    names = []
    for data, media_type in kept:
        name = f"img_{uuid.uuid4().hex[:12]}{IMAGE_EXTS.get(media_type, '.png')}"
        (conv_dir / name).write_bytes(data)
        names.append(name)
    return names, cost, credits, {**sent, "log": request_log.take_last()}


def _submit_video_generation(conv_id: str, model: str, prompt: str, params: dict[str, Any]) -> dict:
    """Start a video job on the model's provider. Returns the job plus
    "log": what was sent and answered (from the request log)."""
    request_log.forget_last()
    return {**_submit_video(conv_id, model, prompt, params), "log": request_log.take_last()}


def _submit_video(conv_id: str, model: str, prompt: str, params: dict[str, Any]) -> dict:
    frame = _ref_file(conv_id, params["first_frame"]) if params.get("first_frame") else None
    prompt = characters.with_characters(prompt, _param_characters(params))
    # An unset ratio uses the model's own auto value when it has one (matching
    # the image path); animating an image still derives the ratio from the frame.
    aspect_ratio = params.get("aspect_ratio") or (None if frame else _auto_ratio("video", model))
    conv_dir = _conv_dir(conv_id)
    return providers.submit_video(
        model,
        prompt,
        duration=params.get("duration"),
        aspect_ratio=aspect_ratio,
        resolution=params.get("resolution"),
        generate_audio=params.get("generate_audio"),
        first_frame=frame,
        last_frame=_ref_file(conv_id, params["last_frame"]) if params.get("last_frame") else None,
        source_video=conv_dir / params["source_video"] if params.get("source_video") else None,
        source_audio=conv_dir / params["source_audio"] if params.get("source_audio") else None,
        mode=params.get("mode"),
        refs=[_ref_file(conv_id, r) for r in params.get("refs") or []],
        # Reference-to-video: named image/video/audio refs the prompt mentions
        # as [@name] (resolve each file to a path; keep its name and type).
        ref_items=[
            {"path": _ref_file(conv_id, r["file"]), "name": r.get("name"), "type": r.get("type")}
            for r in params.get("ref_items") or []
        ],
        session_id=conv_id,
    )
