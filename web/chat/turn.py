"""The Turn: one chat turn run in a worker thread. Streams the chat model,
runs its generate_image/generate_video/create_* tools via the generation
module, persists everything, and starts video pollers for async jobs."""

import contextlib
import json
import os
import threading
from datetime import datetime
from typing import Any

from web.core.metadata import get_db

from .. import characters
from ..providers import openrouter, venice
from . import generation, polling
from .audio import audio_params, submit_audio_generation
from .catalogue import _auto_ratio, _fit_video_params, _model_info
from .constants import (
    CHAT_ROUND_SECONDS,
    CONSISTENCY_REFS,
    DEFAULT_TITLE,
    MAX_TOOL_ROUNDS,
    TITLE_WAIT_SECONDS,
)
from .generation import (
    _characters_note,
    _conversation,
    _conversation_instructions,
    _dedupe,
    _exchange,
    _failure_fields,
    _image_context,
    _is_conversational,
    _is_moderation_error,
    _plan_refs,
    _run_image_generation,
    _submit_video_generation,
    _take_log,
)
from .helpers import _branch_to, _conv_dir, _effective_ids, _message_out, _new_media, _saved_media
from .models import TurnSettings
from .tools import (
    AUDIO_TOOL_RESULT,
    IMAGE_TOOL_RESULT,
    SYSTEM_PROMPT,
    TOOLS_AUDIO,
    TOOLS_CREATE_CHARACTER,
    TOOLS_CREATE_INSTRUCTION,
    TOOLS_IMAGE,
    TOOLS_VIDEO,
    VIDEO_TOOL_RESULT,
    _with_character_arg,
)
from .workers import _ctx_thread


class Turn:
    """Runs one assistant turn and persists it. `emit` receives UI events."""

    def __init__(self, conv_id: str, settings: TurnSettings, message_id: int, emit, cancel: threading.Event):
        self.conv_id = conv_id
        self.s = settings
        self.message_id = message_id
        self.emit = emit
        self.cancel = cancel
        self.db = get_db()
        # Only this reply's own branch — other versions of earlier turns aren't context
        self.history = _branch_to(self.db.get_chat_messages(conv_id), message_id)[:-1]
        self.instructions = _conversation_instructions(conv_id)
        conv = self.db.get_conversation(conv_id)
        self.characters = []  # attached (to the chat, or by its defaults); the only ones a turn uses
        if self._characters_usable():  # attached ones stay attached, just unused, otherwise
            self.characters = characters.load(_effective_ids(conv, "character"), self.db)
        self.content = ""
        self.cost = 0.0
        self.media: list[dict] = []

    # ― entry point ―
    def run(self) -> None:
        title_job = self._start_title()
        try:
            if self.s.mode == "image":
                self._direct_image()
            elif self.s.mode == "video":
                self._direct_video()
            elif self.s.mode == "audio":
                self._direct_audio()
            else:
                self._chat(tools_enabled=self.s.mode == "auto")
            status, error = ("done", None)
        except openrouter.OpenRouterError as e:
            status, error = "error", str(e)
        except Exception as e:  # noqa: BLE001 — never leave a message stuck in "streaming"
            status, error = "error", f"{type(e).__name__}: {e}"
        if self.cancel.is_set() and status == "done":
            self.content = self.content.rstrip() + ("\n\n" if self.content else "") + "*(stopped)*"
        self._finish_title(title_job)
        msg = self.db.update_chat_message(
            self.message_id,
            content=self.content,
            status=status,
            error=error,
            cost=round(self.cost, 6) if self.cost else None,
        )
        if error:
            self.emit({"type": "error", "message": error})
        self.emit({"type": "done", "message": _message_out(msg) if msg else None})

    # ― explicit modes ―
    def _last_user(self):
        return next((m for m in reversed(self.history) if m.role == "user"), None)

    def _direct_image(self) -> None:
        user = self._last_user()
        prompt = (user.content if user else "").strip()
        info = _model_info("image", self.s.image_model) or {}
        if info.get("tool"):
            return self._direct_image_tool(user, prompt, info)
        if not prompt:
            raise openrouter.OpenRouterError("Image mode needs a text prompt")
        chars = self.characters  # every attached character
        dropped: list[str] = []
        refs = [m["file"] for m in (user.media if user else []) if m["kind"] == "image" and m.get("file")]
        if self._accepts_refs():
            refs, dropped = _plan_refs(
                refs + self._pinned_images(),
                chars,
                self.s.image_limit,
                after=len(refs),
                max_refs=self._max_refs(),
                choices=self.s.ref_choices,
            )
        self._generate_image(prompt, self.s.image_options.aspect_ratio, refs, chars=chars, dropped=dropped)

    def _direct_image_tool(self, user, prompt: str, info: dict) -> None:
        """An image tool (upscale, background remover…): the attached image is
        the whole input. The model's name stands in for the prompt, so the
        card can be retried."""
        files = [m["file"] for m in (user.media if user else []) if m["kind"] == "image" and m.get("file")]
        if not files:
            raise openrouter.OpenRouterError("This tool needs an image — attach one")
        self._generate_image(prompt or info.get("name") or "Image tool", None, files[:1])

    def _direct_video(self) -> None:
        user = self._last_user()
        prompt = (user.content if user else "").strip()
        frames = [m["file"] for m in (user.media if user else []) if m["kind"] == "image" and m.get("file")]
        info = _model_info("video", self.s.video_model) or {}
        if not prompt and info.get("no_prompt"):
            prompt = info.get("name") or "Video tool"  # the source file is the whole input
        # Reference-to-video: a prompt that mentions refs as [@name], or any
        # attached video/audio, routes to the model's refs branch with a named
        # list of all attachments. A lone image with no mention stays plain
        # image-to-video.
        ref_mode = info.get("ref_mode")
        has_av = any(m.get("file") and m["kind"] in ("video", "audio") for m in (user.media if user else []))
        ref_items = self._ref_items(ref_mode) if ref_mode and ("[@" in prompt or has_av) else None
        if not prompt and not frames and not ref_items:
            raise openrouter.OpenRouterError("Video mode needs a prompt or an image")
        # Attached images: the first frame, the last frame (first+last-frame
        # models) and, for reference models, all of them are references
        self._generate_video(
            prompt,
            self.s.video_options.duration,
            self.s.video_options.aspect_ratio,
            frames[0] if frames else None,
            chars=self.characters,
            last_frame=frames[1] if len(frames) > 1 else None,
            attached=frames,
            ref_items=ref_items,
        )

    def _ref_items(self, ref_mode: dict) -> list[dict]:
        """A named refs list from this turn's attachments for a reference-to-
        video model: each image/video/audio becomes {file, name, type} with a
        handle (image1, video1…) the prompt mentions as [@name], capped per the
        model's ref_mode per-type limits and total max. Order matches the
        composer, so [@video1] resolves to the same attachment on both sides."""
        user = self._last_user()
        types = set(ref_mode.get("types") or ("image", "video", "audio"))
        limits = ref_mode.get("limits") or {}
        total_max = ref_mode.get("max")
        counts: dict[str, int] = {}
        items: list[dict] = []
        for m in user.media if user else []:
            kind = m.get("kind")
            if not m.get("file") or kind not in types:
                continue
            counts[kind] = counts.get(kind, 0) + 1
            if limits.get(kind) and counts[kind] > limits[kind]:
                continue  # over this type's cap — leave it out (its [@name] won't resolve)
            items.append({"file": m["file"], "name": f"{kind}{counts[kind]}", "type": kind})
            if total_max and len(items) >= total_max:
                break
        return items

    def _direct_audio(self) -> None:
        user = self._last_user()
        prompt = (user.content if user else "").strip()
        if not prompt:
            raise openrouter.OpenRouterError("Audio mode needs a text prompt")
        self._generate_audio(prompt)

    def _generate_audio(self, prompt: str) -> None:
        if not self.s.audio_model:
            raise openrouter.OpenRouterError("No audio model selected")
        params = audio_params(self.s.audio_options)
        if (_model_info("audio", self.s.audio_model) or {}).get("audio_input"):
            params["source_audio"] = self._latest_audio()  # the clip to clone the voice from
        item = _new_media("audio", "generated", prompt=prompt, model=self.s.audio_model, params=params)
        self._add_media(item)
        try:
            job = submit_audio_generation(self.conv_id, self.s.audio_model, prompt, params)
        except openrouter.OpenRouterError as e:
            self._update_media(item, **_failure_fields(e))
            raise
        self._update_media(
            item, job_id=job["id"], params={**params, **job.get("params", {})}, **_exchange(job.get("log"))
        )
        polling.start_video_poller(self.conv_id, self.message_id, item["id"], job["id"])

    # ― chat with tools ―
    def _chat(self, tools_enabled: bool) -> None:
        if not self.s.text_model:
            raise openrouter.OpenRouterError("No text model selected")
        info = _model_info("text", self.s.text_model)
        use_tools = tools_enabled and (info is None or info.get("supports_tools"))
        vision = info is None or "image" in (info.get("input_modalities") or [])
        messages = self._build_llm_messages(vision, as_tool_calls=bool(use_tools and self._tools()))

        offer_tools = True
        for round_no in range(MAX_TOOL_ROUNDS):
            # Last round: withhold tools so the loop can't run forever. Rebuilt
            # each round: a character created mid-turn joins the name lists.
            tools = self._tools() if use_tools else []
            round_tools = (tools or None) if offer_tools and round_no < MAX_TOOL_ROUNDS - 1 else None
            text, tool_calls = self._stream_round(messages, round_tools)
            if self.cancel.is_set() or not tool_calls:
                return
            messages.append({"role": "assistant", "content": text or None, "tool_calls": tool_calls})
            results = []
            for call in tool_calls:
                result = self._run_tool(call)
                results.append(result)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
                if self.cancel.is_set():
                    return
            # A moderation block ends the turn: the user chooses Retry or
            # another model on the failed card (no automatic re-attempt)
            if any(r.get("moderated") for r in results):
                return
            # Saving a character or an instruction makes nothing to show — carry on
            no_media = ("create_character", "create_instruction")
            made_media = any(c["function"]["name"] not in no_media for c in tool_calls)
            if made_media and all(r.get("ok") for r in results):
                # The media was made. If the model also wrote its reply, the
                # reply is complete — asking it to continue just makes it
                # start over (duplicate story + duplicate image). If it called
                # the tool before writing anything, let it write, without tools.
                if text.strip():
                    return
                offer_tools = False
            # (After a non-moderation failure the model keeps its tools and
            # can explain or try again.)

    def _tools(self) -> list[dict]:
        names = [c.name for c in self.characters]
        tools = [TOOLS_CREATE_CHARACTER] if self.s.image_model else []
        if self.s.image_model:
            tools.insert(0, _with_character_arg(TOOLS_IMAGE, names))
        if self.s.video_model:
            tools.append(_with_character_arg(TOOLS_VIDEO, names))
        if self.s.audio_model:
            tools.append(TOOLS_AUDIO)
        tools.append(TOOLS_CREATE_INSTRUCTION)  # needs no media model: applies to the chat model itself
        return tools

    def _stream_round(self, messages: list[dict], tools: list[dict] | None) -> tuple[str, list[dict]]:
        """One chat completion, streamed to the UI."""
        text = ""
        calls: dict[int, dict] = {}
        finish = None
        if self.content and not self.content.endswith("\n\n"):
            self._append("\n\n")
        stream_chat = venice.stream_chat if venice.is_venice(self.s.text_model) else openrouter.stream_chat
        for chunk in stream_chat(
            self.s.text_model,
            messages,
            tools,
            session_id=self.conv_id,
            max_seconds=CHAT_ROUND_SECONDS,
            should_stop=self.cancel.is_set,
        ):
            if self.cancel.is_set():
                break
            usage = chunk.get("usage")
            if usage and usage.get("cost"):
                self.cost += float(usage["cost"])
            for choice in chunk.get("choices") or []:
                finish = choice.get("finish_reason") or finish
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    text += delta["content"]
                    self._append(delta["content"])
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(
                        tc.get("index", 0), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                    )
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    slot["function"]["name"] += fn.get("name") or ""
                    slot["function"]["arguments"] += fn.get("arguments") or ""
        tool_calls = [c for _, c in sorted(calls.items()) if c["function"]["name"]]
        for i, c in enumerate(tool_calls):
            c["id"] = c["id"] or f"call_{i}"
        # Diagnostics: distinguishes "model never called the tool" from
        # "we failed to parse the call" when media goes missing
        print(
            f"💬 chat msg {self.message_id} {self.s.text_model}: finish={finish} "
            f"tools_offered={bool(tools)} tool_calls={[c['function']['name'] for c in tool_calls]} "
            f"raw_call_slots={len(calls)} text_chars={len(text)}"
        )
        return text, tool_calls

    def _append(self, text: str) -> None:
        self.content += text
        self.emit({"type": "delta", "text": text})

    def _run_tool(self, call: dict) -> dict:
        name = call["function"]["name"]
        try:
            args = json.loads(call["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "error": "Arguments were not valid JSON"}
        if name == "create_character":
            return self._create_character(args)
        if name == "create_instruction":
            return self._create_instruction(args)
        if name == "generate_audio":
            return self._audio_tool(args)
        if name not in ("generate_image", "generate_video"):
            return {"ok": False, "error": f"Unknown tool {name}"}
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return {"ok": False, "error": "prompt is required"}
        source = self._latest_image() if args.get("source_image") == "latest" else None
        if args.get("source_image") == "latest" and not source:
            return {"ok": False, "error": "There is no earlier image in the conversation to use"}
        chars = self._pick_characters(args.get("characters"), prompt)
        try:
            if name == "generate_image":
                return self._image_tool(prompt, args, source, chars)
            return self._video_tool(prompt, args, source, chars)
        except openrouter.OpenRouterError as e:
            return {"ok": False, "error": str(e), "moderated": _is_moderation_error(e)}

    def _audio_tool(self, args: dict) -> dict:
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return {"ok": False, "error": "prompt is required"}
        try:
            self._generate_audio(prompt)
        except openrouter.OpenRouterError as e:
            return {"ok": False, "error": str(e), "moderated": _is_moderation_error(e)}
        return {"ok": True, "result": AUDIO_TOOL_RESULT}

    def _image_tool(self, prompt: str, args: dict, source: str | None, chars: list) -> dict:
        # Aspect ratio is the composer's to set, not the chat model's. A ratio
        # picked there wins; left on "auto" it becomes the image model's own
        # "auto" value if it has one, else nothing — the model's natural shape.
        ratio = self.s.image_options.aspect_ratio or _auto_ratio("image", self.s.image_model)
        refs, dropped = self._image_refs(args, source, chars)
        ref_args = {k: args[k] for k in ("source_image", "keep_consistent", "characters") if k in args}
        self._generate_image(prompt, ratio, refs, ref_args, chars, dropped)
        result: dict[str, Any] = {"ok": True, "result": IMAGE_TOOL_RESULT}
        if chars:
            result["characters"] = [c.name for c in chars]
        pinned = self._pinned_images()
        if refs:
            result["reference_images"] = len(refs)
            if dropped:
                result["references_left_out"] = f"{len(dropped)} (the image model takes at most {len(refs)})"
            if set(refs) & set(pinned):
                result["pinned_by_user"] = len(set(refs) & set(pinned))
        elif (ref_args or pinned) and not self._accepts_refs():
            result["note"] = "The selected image model can't take reference images, so none were sent."
        return result

    def _video_tool(self, prompt: str, args: dict, source: str | None, chars: list) -> dict:
        # The composer's settings beat the model's guesses; an animated image's own shape does too
        opts = self.s.video_options
        ratio = opts.aspect_ratio or (None if source else args.get("aspect_ratio"))
        last = None
        if "last_frame" in ((_model_info("video", self.s.video_model) or {}).get("frame_images") or []):
            # First+last-frame models: the two most recent images, older one first
            recent = self._latest_images(2)
            if len(recent) == 2:
                source, last = recent[1], recent[0]
        self._generate_video(prompt, opts.duration or args.get("duration"), ratio, source, chars, last_frame=last)
        return {"ok": True, "result": VIDEO_TOOL_RESULT}

    def _latest_image(self) -> str | None:
        images = self._latest_images(1)
        return images[0] if images else None

    def _latest_images(self, n: int) -> list[str]:
        """The n most recent finished images (this turn first, then history)."""
        found: list[str] = []
        for item in reversed(self.media):
            if item["kind"] == "image" and item["status"] == "done" and item.get("file"):
                found.append(item["file"])
        for msg in reversed(self.history):
            for item in reversed(msg.media):
                if item["kind"] == "image" and item.get("status") == "done" and item.get("file"):
                    found.append(item["file"])
        return found[:n]

    def _pinned_images(self) -> list[str]:
        """Images the user pinned on this branch, oldest first."""
        return [
            item["file"]
            for msg in self.history
            for item in msg.media
            if item.get("pinned")
            and item["kind"] == "image"
            and item.get("status", "done") == "done"
            and item.get("file")
        ]

    def _pick_characters(self, names, prompt: str) -> list:
        """The attached characters in a picture: those the model named in the
        tool call, plus any whose name is in its prompt (models sometimes
        forget the argument). Unattached characters are never used."""
        named = characters.named(self.characters, names)  # "Chloe" can mean attached "Chloe Muscle"
        # "Chloe" in the prompt of a picture of "Chloe Muscle" is her, not an attached "Chloe"
        mentioned = characters.mentioned(self.characters, prompt, prefer=named)
        return list({c.id: c for c in named + mentioned}.values())

    def _attach(self, chars: list) -> None:
        """Attach characters to the chat (they stay for later turns) and tell the UI."""
        new = [c for c in chars if c.id not in {a.id for a in self.characters}]
        if not new:
            return
        self.characters += new
        conv = self.db.get_conversation(self.conv_id)
        own = conv.character_ids if conv else []
        own = [*own, *(c.id for c in new if c.id not in own)]  # the chat's own; its defaults' stay inherited
        self.db.update_conversation(self.conv_id, character_ids=own)
        self.emit(
            {
                "type": "characters",
                "character_ids": own,
                "characters": [c.to_dict() for c in self.characters],
            }
        )

    def _create_character(self, args: dict) -> dict:
        name = str(args.get("name") or "").strip()[:100]
        if not name:
            return {"ok": False, "error": "name is required"}
        existing = next(
            (c for c in characters.available(self.conv_id, self.db) if c.name.strip().lower() == name.lower()), None
        )
        if existing:
            how = (
                "use it by name"
                if existing.id in {c.id for c in self.characters}
                else "the user can attach it to this chat with the characters button"
            )
            return {"ok": False, "error": f"There's already a character called {name}; {how}"}
        try:
            n = max(1, min(4, int(args.get("images") or 1)))
        except (TypeError, ValueError):
            n = 1
        files = [p for p in (_conv_dir(self.conv_id) / f for f in self._latest_images(n)) if p.is_file()]
        if not files:
            return {"ok": False, "error": "There is no image in the conversation to make the character from"}
        char = characters.create_from_files(
            name, str(args.get("description") or "").strip()[:4000], files, self.conv_id, self.db
        )
        self._attach([char])
        return {
            "ok": True,
            "result": f"Character {name} saved with {len(files)} reference image(s) and attached "
            f"to this chat. Name them in generate_image's `characters` to use them.",
        }

    def _create_instruction(self, args: dict) -> dict:
        """Save a reusable instruction snippet and attach it to this chat — the
        instruction counterpart of _create_character. It's added alongside any
        snippets and groups already attached, and takes effect from the next
        reply (this turn's system prompt is already built)."""
        name = str(args.get("name") or "").strip()[:255]
        content = str(args.get("content") or "").strip()[:20000]
        if not name:
            return {"ok": False, "error": "name is required"}
        if not content:
            return {"ok": False, "error": "content is required"}
        existing = next((i for i in self.db.list_instructions() if i.name.strip().lower() == name.lower()), None)
        if existing:
            return {"ok": False, "error": f"There's already an instruction called {name}; pick another name."}
        item = self.db.save_instruction(name=name, content=content)
        conv = self.db.get_conversation(self.conv_id)
        ids = [*(conv.instruction_ids if conv else []), item.id]
        self.db.update_conversation(self.conv_id, instruction_ids=ids)
        self.emit({"type": "instructions", "instruction_ids": ids, "instruction": item.to_dict()})
        return {
            "ok": True,
            "result": f"Instruction “{name}” saved and attached to this chat; it applies from your next reply. "
            f"The user can edit it, group it, or attach it to other chats from the Instructions panel.",
        }

    def _characters_usable(self) -> bool:
        """Whether this turn can use characters — mirrors characterSupport in
        ChatView. Their point is reference images, so it takes an image model
        that accepts them (and, in Auto, a chat model that can call it).
        Chat mode just tells the chat model about them; Video mode only
        uses them with video models that take reference images."""
        if self.s.mode == "text":
            return True
        if self.s.mode == "video":
            # Only video models that take reference images (Venice's refs→video)
            info = _model_info("video", self.s.video_model) or {}
            return bool(info.get("reference_images") or info.get("family") == "motion")
        if not self.s.image_model or not self._accepts_refs():
            return False
        if self.s.mode == "auto":
            info = _model_info("text", self.s.text_model)
            return info is None or bool(info.get("supports_tools"))
        return True

    def _accepts_refs(self) -> bool:
        info = _model_info("image", self.s.image_model)
        return not info or "image" in (info.get("input_modalities") or [])

    def _max_refs(self) -> int | None:
        """How many reference images the image model takes (None = unknown)."""
        return (_model_info("image", self.s.image_model) or {}).get("max_refs")

    def _image_refs(self, args: dict, source: str | None, chars: list) -> tuple[list[str], list[str]]:
        """Reference images for generate_image, and those that didn't fit
        (see _plan_refs for the priority): the edit source (source_image),
        the images of the characters it named, the images the user pinned,
        and the most recent images if the model asked (keep_consistent).
        Pins are the user's choice; the app never adds references on its own."""
        if not self._accepts_refs():
            return [], []  # this image model can't take references
        lead = [source] if source else []
        pinned = self._pinned_images()
        recent = []
        if args.get("keep_consistent") is True:
            recent = [f for f in self._latest_images(CONSISTENCY_REFS) if f not in pinned and f not in lead]
        chat_refs = _dedupe(lead + pinned + recent[: max(CONSISTENCY_REFS - len(lead), 0)])
        return _plan_refs(
            chat_refs, chars, self.s.image_limit, after=len(lead), max_refs=self._max_refs(), choices=self.s.ref_choices
        )

    # ― generation ―
    def _add_media(self, item: dict) -> None:
        self.media.append(item)
        self.db.append_chat_media_item(self.message_id, item)
        self.emit({"type": "media", "message_id": self.message_id, "item": dict(item)})

    def _update_media(self, item: dict, **fields) -> None:
        item.update(fields)
        self.db.update_chat_media_item(self.message_id, item["id"], **fields)
        self.emit({"type": "media", "message_id": self.message_id, "item": dict(item)})

    def _generate_image(
        self,
        prompt: str,
        aspect_ratio: str | None,
        ref_files: list[str],
        ref_args: dict | None = None,
        chars: list | None = None,
        dropped: list[str] | None = None,
    ) -> None:
        if not self.s.image_model:
            raise openrouter.OpenRouterError("No image model selected")
        # Params are stored on the item so a failed image can be retried as-is
        params = {"aspect_ratio": aspect_ratio, "resolution": self.s.image_options.resolution, "refs": ref_files}
        if dropped:
            params["refs_dropped"] = dropped  # more than the image model takes
        if ref_args:
            params["ref_args"] = ref_args  # the model's own reference choices, replayed in history
        if chars:
            params["characters"] = [c.id for c in chars]  # described in the prompt at generation time
            params["character_names"] = [c.name for c in chars]  # for display
        context = None
        if _is_conversational(self.s.image_model):
            # Like the Gemini app: the image model gets the conversation
            direct = self.s.mode == "image"
            params.update(
                context=True, direct=direct, history_limit=self.s.history_limit, image_limit=self.s.image_limit
            )
            context = _image_context(
                self.conv_id,
                self.history,
                self.s.history_limit,
                self.content,
                None if direct else prompt,
                ref_files,
                self.instructions,
                chars,
                self.s.image_limit,
            )
        item = _new_media("image", "generated", prompt=prompt, model=self.s.image_model, params=params)
        self._add_media(item)
        try:
            names, cost, credits, sent = _run_image_generation(
                self.conv_id, self.s.image_model, prompt, params, context
            )
        except openrouter.OpenRouterError as e:
            self._update_media(item, **_failure_fields(e))
            raise
        if cost:
            self.cost += float(cost)
        sent, exchange = _take_log(sent)
        for i, name in enumerate(names):
            if i == 0:
                self._update_media(
                    item,
                    status="done",
                    file=name,
                    cost=cost,
                    credits=credits,
                    params={**params, **sent},
                    **exchange,
                )
            else:
                self._add_media(_saved_media("image", "generated", name, prompt=prompt, model=self.s.image_model))

    def _generate_video(
        self,
        prompt: str,
        duration: int | None,
        aspect_ratio: str | None,
        first_frame: str | None,
        chars: list | None = None,
        last_frame: str | None = None,
        attached: list[str] | None = None,
        ref_items: list[dict] | None = None,
    ) -> None:
        if not self.s.video_model:
            raise openrouter.OpenRouterError("No video model selected")
        duration, aspect_ratio, resolution = _fit_video_params(
            self.s.video_model, duration, aspect_ratio, self.s.video_options.resolution
        )
        # Reference-to-video supersedes the singular first frame: the attachments
        # all ride in the named refs list instead.
        if ref_items:
            first_frame = None
        params = {
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "first_frame": first_frame,
            "generate_audio": self.s.video_options.generate_audio,
        }
        if ref_items:
            params["ref_items"] = ref_items
        if chars:
            params["characters"] = [c.id for c in chars]
        params.update(self._video_inputs(first_frame, last_frame, attached or [], chars or []))
        item = _new_media("video", "generated", prompt=prompt, model=self.s.video_model, params=params)
        self._add_media(item)
        try:
            job = _submit_video_generation(self.conv_id, self.s.video_model, prompt, params)
        except openrouter.OpenRouterError as e:
            self._update_media(item, **_failure_fields(e))
            raise
        # Pollo reports what it was actually sent, defaults included
        self._update_media(
            item, job_id=job["id"], params={**params, **job.get("params", {})}, **_exchange(job.get("log"))
        )
        polling.start_video_poller(self.conv_id, self.message_id, item["id"], job["id"])

    def _video_inputs(self, first_frame: str | None, last_frame: str | None, attached: list[str], chars: list) -> dict:
        """The extra inputs the video model's family takes (Venice): reference
        images (attached ones, the frame, characters' images and pins), a
        last frame, or the chat's latest video."""
        info = _model_info("video", self.s.video_model) or {}
        out: dict[str, Any] = {}
        if info.get("reference_images") or info.get("family") == "motion":
            own = _dedupe([*attached, *([first_frame] if first_frame else []), *self._pinned_images()])
            out["refs"], _ = _plan_refs(
                own,
                chars,
                None,
                after=len(attached) or (1 if first_frame else 0),
                max_refs=info.get("max_refs"),
                choices=self.s.ref_choices,
            )
        if last_frame and "last_frame" in (info.get("frame_images") or []):
            out["last_frame"] = last_frame
        if info.get("video_input"):
            out["source_video"] = self._latest_video()
        if info.get("audio_input"):
            out["source_audio"] = self._latest_audio()
        return out

    def _latest_video(self) -> str | None:
        """The most recent finished video (this turn first, then history)."""
        return self._latest_media_file("video")

    def _latest_audio(self) -> str | None:
        """The most recent audio attachment (this turn first, then history) —
        the uploaded track a lip-sync model drives a portrait with."""
        return self._latest_media_file("audio")

    def _latest_media_file(self, kind: str) -> str | None:
        for item in [*reversed(self.media), *(i for m in reversed(self.history) for i in reversed(m.media))]:
            if item["kind"] == kind and item.get("status") == "done" and item.get("file"):
                return item["file"]
        return None

    # ― history → OpenRouter messages ―
    def _build_llm_messages(self, vision: bool, as_tool_calls: bool = False) -> list[dict]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(today=datetime.now().strftime("%A %d %B %Y"))}]
        if self.instructions:
            # The user's own custom instructions, verbatim
            messages.append({"role": "system", "content": self.instructions})
        note = _characters_note(self.characters)
        if note:
            messages.append({"role": "system", "content": note})
        return messages + _conversation(
            self.conv_id, self.history, self.s.history_limit, vision, as_tool_calls, self.s.image_limit
        )

    # ― title ―
    def _start_title(self) -> dict | None:
        """A new chat's first turn asks a text model for a short title while
        the reply is made (CHAT_TITLE_MODEL, else the chat model)."""
        conv = self.db.get_conversation(self.conv_id)
        if not conv or conv.title != DEFAULT_TITLE:
            return None
        first = next((m for m in self.history if m.role == "user" and m.content), None)
        if not first:
            return None
        job: dict[str, Any] = {"prompt": first.content, "title": None, "cost": 0.0, "thread": None}
        model = os.environ.get("CHAT_TITLE_MODEL") or self.s.text_model
        direct = self.s.mode in ("image", "video", "audio")  # no text model involved: the prompt titles the chat
        if model and not direct and (venice.is_configured() if venice.is_venice(model) else openrouter.is_configured()):

            def work():
                # No title from the model: the prompt stands in
                with contextlib.suppress(Exception):
                    job["title"], job["cost"] = generation._generate_title(model, first.content)

            job["thread"] = _ctx_thread(work, name=f"chat-title-{self.message_id}")
            job["thread"].start()
        return job

    def _finish_title(self, job: dict | None) -> None:
        """Title the chat: the model's title if it came back in time, else the
        start of the first prompt. Its cost goes on this reply."""
        if not job:
            return
        title = None
        if job["thread"]:
            job["thread"].join(timeout=TITLE_WAIT_SECONDS)
            if not job["thread"].is_alive():
                title = job["title"]
                self.cost += job["cost"] or 0
        if not title:
            title = " ".join(job["prompt"].split())
            if len(title) > 60:
                title = title[:57].rsplit(" ", 1)[0] + "…"
        conv = self.db.get_conversation(self.conv_id)
        if not conv or conv.title != DEFAULT_TITLE:  # renamed meanwhile
            return
        self.db.update_conversation(self.conv_id, title=title)
        self.emit({"type": "title", "title": title})
