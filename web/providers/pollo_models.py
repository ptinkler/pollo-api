"""How Pollo's models are presented: labels, types and which options each one
takes. A model's lengths, ratios and resolutions are NOT here — they live
with its endpoint in web/providers/pollo_engine/ (one table per kind), which
is the single source for them.
"""

# "hidden": the reason a model is left out of the model pickers unless
# "Show hidden" is on — not enabled for our key, or retired by choice. It
# still works if picked (and stays selected where it already is).
#
# "ref_mode" describes the model's Reference-To-Video branch, which the
# frontend exposes as a "Ref mode" toggle. From docs.pollo.ai/openapi.json:
# allowed ref "types", total "max" refs, optional per-type "limits", and
# optional "lengths"/"resolutions" when they differ from the image/text
# branches. "hide_options" lists options the ref branch lacks (web_search
# and image_tail never exist there). "max_length_with_video" caps duration
# when a video ref is present; "exclusive" ref types can't be combined.
MODEL_INFO = {
    # https://docs.pollo.ai
    "pollo20": {
        "label": "Pollo 2.0",
        "type": "img2vid",
        "options": ["generate_audio", "seed", "refs"],
        "ref_mode": {
            "types": ["image"],
            "max": 7,
            "lengths": list(range(1, 9)),
            "resolutions": ["540p", "720p", "1080p"],
        },
    },
    "pollo25": {
        "label": "Pollo 2.5",
        "type": "img2vid",
        "options": ["generate_audio", "mode"],
    },
    "pollo30": {
        "label": "Pollo 3.0",
        "type": "img2vid",
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 13, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "pollo30fast": {
        "label": "Pollo 3.0 Fast",
        "type": "img2vid",
        "hidden": "Pollo says it's currently unavailable (400)",  # checked with a real request 2026-10-07
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio"],
            "max": 13,
            "limits": {"image": 9, "video": 3, "audio": 3},
            "hide_options": ["seed"],
        },
    },
    "seedance20": {
        "label": "Seedance 2.0",
        "type": "img2vid",
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "seedance20fast": {
        "label": "Seedance 2.0 Fast",
        "type": "img2vid",
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "seedance20mini": {
        "label": "Seedance 2.0 Mini",
        "type": "img2vid",
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "seedance25": {
        "label": "Seedance 2.5",
        "type": "img2vid",
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio"],
            "max": 50,
            "limits": {"image": 30, "video": 10, "audio": 10},
        },
    },
    "seedance25draft": {
        "label": "Seedance 2.5 Draft",
        "type": "img2vid",
        "options": ["generate_audio", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio"],
            "max": 50,
            "limits": {"image": 30, "video": 10, "audio": 10},
        },
    },
    # "type": "extend" continues a source video (video_url) instead of
    # animating an image. Selectable like the motion models: the source video rides in on
    # video_input (the chat's latest video, or an uploaded one) — no reference
    # image. The user picks how many seconds to add (duration) and a resolution.
    "seedance25extend": {
        "hidden": "Not enabled for API access on this key (403)",  # 2026-11-09 real-media generation probe
        "label": "Seedance 2.5 Extend",
        "type": "extend",
        "options": ["generate_audio", "seed"],
        "video_input": True,
    },
    # lengths/resolutions fall back to the engine config (v1_video.py).
    "pollov2extender": {"label": "Pollo 2 Extender", "type": "extend", "options": [], "video_input": True},
    "geminiomniextend": {
        "label": "Gemini Omni Extend",
        "type": "extend",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    "flux3extend": {
        "label": "Flux 3 Extend",
        "type": "extend",
        "options": ["generate_audio"],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    "viduq2proextend": {"label": "Vidu Q2 Pro Extend", "type": "extend", "options": [], "video_input": True},
    "viduq2turboextend": {"label": "Vidu Q2 Turbo Extend", "type": "extend", "options": [], "video_input": True},
    # "type": "video_edit" rewrites a source video from a text instruction.
    # Selectable like Extend: source video on video_input, the edit instruction
    # is the prompt. No duration/aspect ratio; resolution falls back to the
    # engine config (v1_video.py).
    "wanedit27": {
        "label": "Wan 2.7 Edit",
        "type": "video_edit",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    "wanedit30": {
        "label": "Wan 3.0 Edit",
        "type": "video_edit",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    "wanedit30prime": {
        "label": "Wan 3.0 Prime Edit",
        "type": "video_edit",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    "geminiomniedit": {
        "label": "Gemini Omni Edit",
        "type": "video_edit",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    "happyhorse10": {
        "label": "HappyHorse 1.0 Edit",
        "type": "video_edit",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    "viduq2proedit": {
        "label": "Vidu Q2 Pro Edit",
        "type": "video_edit",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    "runwayalephedit": {
        "label": "Runway Gen-4 Aleph Edit",
        "type": "video_edit",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    # "type": "upscale" enlarges / enhances a source video (video_input). No
    # prompt, duration or aspect ratio: the resolution picker carries Pollo's
    # `scale` (original / 2x / 4x / hd / 4K) and `modes` the enhancement mode.
    "pollovideoupscale": {
        "hidden": "Not enabled for API access on this key (403)",  # 2026-11-09 real-media generation probe
        "label": "Pollo Video Upscale",
        "type": "upscale",
        "options": ["mode"],
        "modes": ["standard", "face", "denoise", "sharpen", "anime"],
        "video_input": True,
    },
    "topazvideoupscale": {
        "label": "Topaz Video Upscale",
        "type": "upscale",
        "options": ["mode"],
        "modes": ["standard", "face", "denoise", "sharpen", "anime"],
        "video_input": True,
    },
    # Video tools: source video in, video out; no prompt. The resolution picker
    # carries the one choice (output format / subtitle language).
    "videobgremove": {
        "label": "Video Background Remover",
        "type": "bgremove",
        "options": [],
        "video_input": True,
    },
    "videosubtitleremove": {
        "hidden": "Not enabled for API access on this key (403)",  # 2026-11-09 real-media generation probe
        "label": "Video Subtitle Remover",
        "type": "subtitle_remove",
        "options": ["mode"],
        "modes": ["standard", "advanced"],
        "video_input": True,
    },
    # Face swap: source video (video_input) + the face image (first_frame).
    "faceswap": {"label": "Face Swap", "type": "faceswap", "options": [], "video_input": True},
    # Wan 2.2 Animate Mix: a motion model like the ones below.
    "wananimatemix": {
        "hidden": "Not enabled for API access on this key (403)",  # 2026-11-09 real-media generation probe
        "label": "Wan 2.2 Animate Mix",
        "type": "motion",
        "options": ["mode"],
        "modes": ["std", "pro"],
        "video_input": True,
    },
    # "type": "motion" = act / motion transfer: animate a reference image
    # (first_frame) with the motion of a source video (video_input). Same shape
    # as above; tagged "motion". Some models take a std/pro mode, some don't.
    "wananimatemove": {
        "hidden": "Not enabled for API access on this key (403)",  # 2026-11-09 real-media generation probe
        "label": "Wan Animate Move",
        "type": "motion",
        "options": ["mode"],
        "modes": ["std", "pro"],
        "video_input": True,
    },
    "klingmotion26": {
        "hidden": "Not enabled for API access on this key (403)",  # 2026-11-09 real-media generation probe
        "label": "Kling 2.6 Motion",
        "type": "motion",
        "options": ["mode"],
        "modes": ["std", "pro"],
        "video_input": True,
    },
    "klingmotion3": {
        "hidden": "Not enabled for API access on this key (403)",  # 2026-11-09 real-media generation probe
        "label": "Kling 3.0 Motion",
        "type": "motion",
        "options": ["mode"],
        "modes": ["std", "pro"],
        "video_input": True,
    },
    "actionimitation": {"label": "Action Imitation", "type": "motion", "options": [], "video_input": True},
    "actionimitationv2": {
        "label": "Action Imitation v2",
        "type": "motion",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    "runwayacttwo": {
        "label": "Runway Act-Two",
        "type": "motion",
        "options": [],
        "video_input": True,
        "hidden": "Not enabled for API access on this key (403)",
    },
    # "type": "lipsync" drives a reference image (first_frame) with an uploaded
    # audio track (audio_input). No source video; resolution falls back to the
    # engine config (v1_video.py) where the model offers one.
    "omnihuman": {
        "label": "OmniHuman",
        "type": "lipsync",
        "options": [],
        "hidden": "Not enabled for API access on this key (403)",
    },
    "omnihuman15": {
        "label": "OmniHuman 1.5",
        "type": "lipsync",
        "options": [],
        "hidden": "Not enabled for API access on this key (403)",
    },
    "hedracharv3": {
        "label": "Hedra Character 3",
        "type": "lipsync",
        "options": [],
        "hidden": "Not enabled for API access on this key (403)",
    },
    "h3lipsync": {
        "label": "Pollo H3 Lip-sync",
        "type": "lipsync",
        "options": [],
        "hidden": "Not enabled for API access on this key (403)",
    },
    "minimaxh3": {
        "label": "MiniMax H3",
        "type": "img2vid",
        "options": ["image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "minimaxh3max": {
        "label": "MiniMax H3 Max",
        "type": "img2vid",
        "options": ["image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 12, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "wan27": {
        "label": "Wan 2.7",
        "type": "img2vid",
        "options": ["seed", "image_tail", "negative_prompt", "audio_url", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio"],
            "max": 10,
            "limits": {"image": 5, "video": 5, "audio": 1},
            "max_length_with_video": 10,
            "hide_options": ["audio_url"],
        },
        "deprecated": True,
    },
    "wan30": {
        "label": "Wan 3.0",
        "type": "img2vid",
        "options": ["generate_audio", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio", "file", "link"],
            "max": 22,
            "limits": {"image": 10, "video": 5, "audio": 5, "file": 1, "link": 1},
            "exclusive": ["file", "link"],
        },
    },
    "wan30prime": {
        "label": "Wan 3.0 Prime",
        "type": "img2vid",
        "options": ["generate_audio", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio", "file", "link"],
            "max": 22,
            "limits": {"image": 10, "video": 5, "audio": 5, "file": 1, "link": 1},
            "exclusive": ["file", "link"],
        },
    },
    # --- Newer frontier models (added 2026-11). lengths/ratios/resolutions
    # fall back to the engine config (v1_video.py), so they live in one place. ---
    "sora2": {"label": "Sora 2", "type": "img2vid", "options": []},
    "sora2pro": {"label": "Sora 2 Pro", "type": "img2vid", "options": []},
    "veo31": {"label": "Veo 3.1", "type": "img2vid", "options": ["generate_audio", "image_tail"]},
    "veo31fast": {"label": "Veo 3.1 Fast", "type": "img2vid", "options": ["generate_audio", "image_tail"]},
    "veo31lite": {"label": "Veo 3.1 Lite", "type": "img2vid", "options": ["image_tail"]},
    "hailuo23": {"label": "Hailuo 2.3", "type": "img2vid", "options": []},
    "hailuo03": {"label": "Hailuo 03", "type": "img2vid", "options": ["image_tail"]},
    "pollo26": {
        "label": "Pollo 2.6",
        "type": "img2vid",
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
    },
    "pollo26fast": {
        "label": "Pollo 2.6 Fast",
        "type": "img2vid",
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
    },
    "wan25": {"label": "Wan 2.5", "type": "img2vid", "options": ["generate_audio", "seed"]},
    "wan26": {"label": "Wan 2.6", "type": "img2vid", "options": ["generate_audio", "seed"]},
    "grokvideo15": {"label": "Grok Imagine Video 1.5", "type": "img2vid", "options": []},
    "klingv4": {
        "label": "Kling 4.0",
        "type": "img2vid",
        "options": ["image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 10, "video": 5, "audio": 3}},
    },
    "klingv4flash": {
        "label": "Kling 4.0 Flash",
        "type": "img2vid",
        "options": ["image_tail", "refs"],
        "ref_mode": {"types": ["image", "video"], "max": 15, "limits": {"image": 10, "video": 5}},
    },
    "klingv21": {
        "label": "Kling 2.1",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "options": [],
        "note": "Image-to-video only — needs a source image.",
    },
    "klingv21master": {
        "label": "Kling 2.1 Master",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "options": [],
    },
    "klingv25turbo": {
        "label": "Kling 2.5 Turbo",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "options": ["image_tail"],
    },
    "klingvideoo1": {
        "label": "Kling Video O1",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "options": ["image_tail"],
    },
    "klingv26": {
        "label": "Kling 2.6",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "options": ["generate_audio", "image_tail"],
    },
    "klingv3": {
        "label": "Kling 3.0",
        "type": "img2vid",
        "options": ["generate_audio", "image_tail"],
    },
    "klingv3turbo": {
        "label": "Kling 3.0 Turbo",
        "type": "img2vid",
        "options": [],
    },
    "klingv3omni": {
        "label": "Kling 3.0 Omni",
        "type": "img2vid",
        "options": ["generate_audio", "image_tail", "refs"],
        # With a video ref: ≤4 images + ≤1 video; without a video: up to 7 images (docs 2026-11).
        # Omni can't generate a soundtrack when a video ref is present.
        "ref_mode": {
            "types": ["image", "video"],
            "max": 7,
            "limits": {"image": 4, "video": 1},
            "no_audio_with_video": True,
        },
    },
    "pollojourney": {
        "label": "Pollo Journey 8.2",
        "type": "image",
        "options": ["seed", "images"],
    },
    "seedream": {
        "label": "Seedream 5.0 Lite",
        "type": "image",
        "options": ["images"],
    },
    "nanobanana2": {
        "label": "Nano Banana 2",
        "type": "image",
        "options": ["images"],
    },
    "klingv3image": {
        "label": "Kling 3.0 Image",
        "type": "image",
        "options": ["images"],
    },
    "klingv3omniimage": {
        "label": "Kling 3.0 Omni Image",
        "type": "image",
        "options": ["images"],
    },
    "seedreamflash": {
        "label": "Seedream 5.0 Flash",
        "type": "image",
        "options": ["images"],
    },
    "seedreampro": {
        "label": "Seedream 5.0 Pro",
        "type": "image",
        "options": ["images"],
    },
    "qwenimage3": {
        "label": "Qwen Image 3",
        "type": "image",
        "options": ["images"],
    },
    "qwenimage3pro": {
        "label": "Qwen Image 3 Pro",
        "type": "image",
        "options": ["images"],
    },
    "qwenimageflash": {
        "label": "Qwen Image Flash",
        "type": "image",
        "hidden": "Pollo says it's currently unavailable",  # 403 on 2026-10-06; "currently unavailable" on 2026-10-18
        "options": [],
    },
    # --- Newer frontier image models (added 2026-11). Ratios/resolutions live
    # in the engine config (v1_image.py). ---
    "nanobananapro": {"label": "Nano Banana Pro", "type": "image", "options": ["images"]},
    "nanobanana21": {"label": "Nano Banana 2.1", "type": "image", "options": ["images"]},
    "fluxkontextpro": {"label": "Flux Kontext Pro", "type": "image", "options": ["images"]},
    "fluxkontextmax": {"label": "Flux Kontext Max", "type": "image", "options": ["images"]},
    "flux2max": {"label": "Flux 2 Max", "type": "image", "options": ["images"]},
    "gptimage25": {"label": "GPT Image 2.5", "type": "image", "options": ["images"]},
    "seedream45": {"label": "Seedream 4.5", "type": "image", "options": ["images"]},
    "midjourneyv82": {"label": "Midjourney v8.2", "type": "image", "options": ["images"]},
    "grokimage20": {"label": "Grok Imagine Image 2.0", "type": "image", "options": ["images"]},
    "recraftv3": {"label": "Recraft v3", "type": "image", "options": []},
    "ideogramv2turbo": {"label": "Ideogram v2 Turbo", "type": "image", "options": []},
    # Audio models. "type": "speech" = text-to-speech ("voice" option: a voice
    # id from Pollo's voice list; "tuning": speed/volume/pitch), "music" = Suno
    # ("instrumental", lyrics mode via style + title, "duration" on v5.5).
    "seedaudio10": {"label": "Seed Audio 1.0", "type": "speech", "options": ["tuning"]},
    # ref2audio: speaks in the voice of an uploaded clip (audio_input).
    "seedaudioref10": {
        "label": "Seed Audio 1.0 (voice clone)",
        "type": "speech",
        "options": ["tuning"],
        "audio_input": True,
    },
    "minimaxspeech28hd": {"label": "MiniMax Speech 2.8 HD", "type": "speech", "options": ["voice"]},
    "elevenv3": {"label": "ElevenLabs v3", "type": "speech", "options": ["voice"]},
    "sunov45plus": {"label": "Suno v4.5+", "type": "music", "options": ["instrumental", "lyrics"]},
    "sunov5": {"label": "Suno v5", "type": "music", "options": ["instrumental", "lyrics"]},
    "sunov55": {"label": "Suno v5.5", "type": "music", "options": ["instrumental", "lyrics", "duration"]},
    # Image tools ("tool": source image in, image out; no prompt). The upscale
    # factor rides the resolution picker.
    "imageupscale": {"label": "Image Upscale", "type": "image", "tool": "upscale", "options": []},
    "imagebgremove": {"label": "Image Background Remover", "type": "image", "tool": "bgremove", "options": []},
}
