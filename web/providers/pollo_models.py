"""
Pollo's video and image models as the Generate page shows them: labels,
lengths, ratios, resolutions and which options each one takes.
"""

# "legacy": True marks a model as living on Pollo's pre-v1 API
# (POLLO_API_BASE, no "/v1/" in the URL) — see the family tables in
# web/providers/pollo_engine.py. These are hidden from the model
# dropdown unless the frontend's "legacy mode" toggle is on (GET
# /api/models filters them out by default; see get_models() in web/api.py).
# Models with no "legacy" key are on the current v1 API and always shown.
#
# "hidden": the reason a model is left out of the model pickers unless
# "Show hidden" is on — not enabled for our key, or retired by choice. It
# still works if picked (and stays selected where it already is).
#
# "ref_mode" (v1 models only) describes the model's Reference-To-Video
# branch, which the frontend exposes as a "Ref mode" toggle (the legacy API
# used separate "type": "ref" models instead). From docs.pollo.ai/openapi.json:
# allowed ref "types", total "max" refs, optional per-type "limits", and
# optional "lengths"/"resolutions" when they differ from the image/text
# branches. "hide_options" lists options the ref branch lacks (web_search
# and image_tail never exist there). "max_length_with_video" caps duration
# when a video ref is present; "exclusive" ref types can't be combined.
MODEL_INFO = {
    "pollodance20": {
        "label": "Pollo Dance 2.0",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "deprecated": True,
        "legacy": True,
    },
    "pollodance20fast": {
        "label": "Pollo Dance 2.0 Fast",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "deprecated": True,
        "legacy": True,
    },
    "pollo20": {
        "label": "Pollo 2.0",
        "type": "img2vid",
        "lengths": [5, 10],
        "ratios": ["9:16", "16:9"],
        "options": ["generate_audio", "web_search"],
        "legacy": True,
    },
    "pollo25": {
        "label": "Pollo 2.5",
        "type": "img2vid",
        "lengths": [4, 5, 6, 7, 8, 9, 10, 11, 12, 15],
        "resolutions": ["720p", "1080p"],
        "options": ["generate_audio", "web_search"],
        "legacy": True,
    },
    "pollodanceref": {
        "label": "Pollo Dance Ref",
        "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "deprecated": True,
        "legacy": True,
    },
    "pollodancereffast": {
        "label": "Pollo Dance Ref Fast",
        "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "deprecated": True,
        "legacy": True,
    },
    "seedance20": {
        "label": "Seedance 2.0",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "legacy": True,
    },
    "seedance20fast": {
        "label": "Seedance 2.0 Fast",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "legacy": True,
    },
    "seedance20mini": {
        "label": "Seedance 2.0 Mini",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "deprecated": True,
        "legacy": True,
    },
    "seedance25": {
        "label": "Seedance 2.5",
        "type": "img2vid",
        "lengths": list(range(4, 31)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9", "adaptive"],
        "resolutions": ["480p", "720p"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "legacy": True,
    },
    "seedance25draft": {
        "label": "Seedance 2.5 Draft",
        "hidden": "Not enabled for API access on this key (403)",  # checked with real requests 2026-10-18
        "type": "img2vid",
        "lengths": list(range(4, 31)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9", "adaptive"],
        "resolutions": ["480p"],
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
        "legacy": True,
    },
    "seedanceref": {
        "label": "Seedance 2.0 Ref",
        "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "legacy": True,
    },
    "seedancereffast": {
        "label": "Seedance 2.0 Ref Fast",
        "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "legacy": True,
    },
    "seedanceminiref": {
        "label": "Seedance 2.0 Mini Ref",
        "type": "ref",
        "lengths": list(range(4, 16)),
        "ratios": ["4:3", "3:4", "1:1", "16:9", "9:16", "21:9"],
        "options": ["generate_audio", "video_num", "refs", "image_meta"],
        "deprecated": True,
        "legacy": True,
    },
    "minimaxh3": {
        "label": "MiniMax H3",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480P", "768P", "2K"],
        "options": ["resolution", "image_tail", "prompt_optimizer"],
        "legacy": True,
    },
    "wan27": {
        "label": "Wan 2.7",
        "type": "img2vid",
        "lengths": list(range(2, 16)),
        "resolutions": ["720P", "1080P"],
        "options": ["seed", "image_tail", "negative_prompt", "audio_url"],
        "deprecated": True,
        "legacy": True,
    },
    "wan30": {
        "label": "Wan 3.0",
        "type": "img2vid",
        "lengths": list(range(2, 31)),
        "resolutions": ["480P", "720P", "1080P"],
        "options": ["generate_audio", "num_outputs"],
        "note": "numOutputs field name is unconfirmed (inferred, not yet verified against a live response).",
        "legacy": True,
    },
    "wan30prime": {
        "label": "Wan 3.0 Prime",
        "type": "img2vid",
        "lengths": list(range(2, 31)),
        "resolutions": ["480P", "720P", "1080P"],
        "options": ["generate_audio", "num_outputs"],
        "note": "numOutputs field name is unconfirmed (inferred, not yet verified against a live response).",
        "legacy": True,
    },
    "pollojourney": {
        "label": "Pollo Journey 8.2",
        "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["seed", "images"],
        "legacy": True,
    },
    "seedream": {
        "label": "Seedream 5.0 Lite",
        "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "21:9"],
        "resolutions": ["2K", "3K", "4K"],
        "options": ["images", "max_images"],
        "legacy": True,
    },
    "nanobanana2": {
        "label": "Nano Banana 2",
        "type": "image",
        "ratios": ["1:1", "9:16", "16:9", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"],
        "resolutions": ["1K", "2K", "4K"],
        "options": ["images", "max_images", "thinking_level"],
        "deprecated": True,
        "legacy": True,
    },
    "polloimage2": {
        "label": "Pollo Image 2.0",
        "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "4:5", "5:4"],
        "resolutions": ["1K", "2K", "4K"],  # 2K/4K run in Pollo's "professional" mode
        "options": ["images"],
        "legacy": True,
        "legacy_only": True,  # its v1 endpoint isn't enabled for API access — offered in both modes
    },
    # v1 API (current — https://docs.pollo.ai)
    "pollo20v1": {
        "label": "Pollo 2.0",
        "type": "img2vid",
        "lengths": [5, 10],
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["16:9", "9:16", "4:3", "3:4", "1:1"],
        "options": ["generate_audio", "seed", "refs"],
        "ref_mode": {
            "types": ["image"],
            "max": 7,
            "lengths": list(range(1, 9)),
            "resolutions": ["540p", "720p", "1080p"],
        },
    },
    "pollo25v1": {
        "label": "Pollo 2.5",
        "type": "img2vid",
        "lengths": [4, 5, 6, 7, 8, 9, 10, 11, 12, 15],
        "resolutions": ["720p", "1080p"],
        "ratios": ["16:9", "9:16"],
        "options": ["generate_audio", "mode"],
    },
    "pollodance20v1": {
        "label": "Pollo Dance 2.0",
        "type": "img2vid",
        "hidden": "No longer enabled for API access on this key",  # 2026-10-07
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio"],
            "max": 13,
            "limits": {"image": 9, "video": 3, "audio": 3},
            "hide_options": ["seed"],
        },
    },
    "pollodance20fastv1": {
        "label": "Pollo Dance 2.0 Fast",
        "type": "img2vid",
        "hidden": "No longer enabled for API access on this key",  # 2026-10-07
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio"],
            "max": 13,
            "limits": {"image": 9, "video": 3, "audio": 3},
            "hide_options": ["seed"],
        },
    },
    "pollo30v1": {
        "label": "Pollo 3.0",
        "type": "img2vid",
        "hidden": "Not enabled for API access on this key (403)",  # checked with a real request 2026-10-07
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p", "1080p", "4K"],  # 1080p/4K are sent with mode "pro"
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 13, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "pollo30fastv1": {
        "label": "Pollo 3.0 Fast",
        "type": "img2vid",
        "hidden": "Pollo says it's currently unavailable (400)",  # checked with a real request 2026-10-07
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio"],
            "max": 13,
            "limits": {"image": 9, "video": 3, "audio": 3},
            "hide_options": ["seed"],
        },
    },
    "seedance20v1": {
        "label": "Seedance 2.0",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p", "1080p", "4K"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "seedance20fastv1": {
        "label": "Seedance 2.0 Fast",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "seedance20miniv1": {
        "label": "Seedance 2.0 Mini",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "720p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "seedance25v1": {
        "label": "Seedance 2.5",
        "type": "img2vid",
        "lengths": list(range(4, 31)),
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
        "options": ["generate_audio", "web_search", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio"],
            "max": 50,
            "limits": {"image": 30, "video": 10, "audio": 10},
        },
    },
    "seedance25draftv1": {
        "label": "Seedance 2.5 Draft",
        "hidden": "Not enabled for API access on this key (403)",  # checked with real requests 2026-10-18
        "type": "img2vid",
        "lengths": list(range(4, 31)),
        "resolutions": ["480p"],
        "ratios": ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"],
        "options": ["generate_audio", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio"],
            "max": 50,
            "limits": {"image": 30, "video": 10, "audio": 10},
        },
    },
    # "type": "extend" continues a source video (video_url) instead of
    # animating an image. Selectable like Recast: the source video rides in on
    # video_input (the chat's latest video, or an uploaded one) — no reference
    # image. The user picks how many seconds to add (duration) and a resolution.
    "seedance25extendv1": {
        "label": "Seedance 2.5 Extend",
        "hidden": "Not enabled for API access on this key (403)",  # checked with real requests 2026-10-18
        "type": "extend",
        "lengths": list(range(4, 31)),
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": [],
        "options": ["generate_audio", "seed"],
        "video_input": True,
    },
    # lengths/resolutions fall back to the engine config (v1_video.py).
    "pollov2extenderv1": {"label": "Pollo 2 Extender", "type": "extend", "options": [], "video_input": True},
    "geminiomniextendv1": {"label": "Gemini Omni Extend", "type": "extend", "options": [], "video_input": True},
    "flux3extendv1": {"label": "Flux 3 Extend", "type": "extend", "options": ["generate_audio"], "video_input": True},
    "viduq2proextendv1": {"label": "Vidu Q2 Pro Extend", "type": "extend", "options": [], "video_input": True},
    "viduq2turboextendv1": {"label": "Vidu Q2 Turbo Extend", "type": "extend", "options": [], "video_input": True},
    # "type": "video_edit" rewrites a source video from a text instruction.
    # Selectable like Extend: source video on video_input, the edit instruction
    # is the prompt. No duration/aspect ratio; resolution falls back to the
    # engine config (v1_video.py).
    "wanedit27v1": {"label": "Wan 2.7 Edit", "type": "video_edit", "options": [], "video_input": True},
    "wanedit30v1": {"label": "Wan 3.0 Edit", "type": "video_edit", "options": [], "video_input": True},
    "wanedit30primev1": {"label": "Wan 3.0 Prime Edit", "type": "video_edit", "options": [], "video_input": True},
    "geminiomnieditv1": {"label": "Gemini Omni Edit", "type": "video_edit", "options": [], "video_input": True},
    "happyhorse10v1": {"label": "HappyHorse 1.0 Edit", "type": "video_edit", "options": [], "video_input": True},
    "viduq2proeditv1": {"label": "Vidu Q2 Pro Edit", "type": "video_edit", "options": [], "video_input": True},
    "runwayalepheditv1": {"label": "Runway Gen-4 Aleph Edit", "type": "video_edit", "options": [], "video_input": True},
    # "type": "upscale" enlarges / enhances a source video (video_input). No
    # prompt, duration or aspect ratio: the resolution picker carries Pollo's
    # `scale` (original / 2x / 4x / hd / 4K) and `modes` the enhancement mode.
    "pollovideoupscalev1": {
        "label": "Pollo Video Upscale",
        "type": "upscale",
        "resolutions": ["original", "2x", "4x", "hd", "4K"],
        "options": ["mode"],
        "modes": ["standard", "face", "denoise", "sharpen", "anime"],
        "video_input": True,
    },
    "topazvideoupscalev1": {
        "label": "Topaz Video Upscale",
        "type": "upscale",
        "resolutions": ["original", "2x", "4x", "hd", "4K"],
        "options": ["mode"],
        "modes": ["standard", "face", "denoise", "sharpen", "anime"],
        "video_input": True,
    },
    # "type": "recast" = Pollo Recast (wan-2-2-animate-mix): replaces the
    # subject in a source video with one reference image, keeping the motion.
    # A selectable model (unlike "extend"): the source video rides in on
    # video_input (latest chat video or an uploaded one), the reference image
    # on first_frame. No length/resolution/ratio — the source video sets them.
    "recastv1": {
        "label": "Pollo Recast",
        "type": "recast",
        "lengths": [],
        "resolutions": [],
        "ratios": [],
        "options": ["mode"],
        "modes": ["std", "pro"],
        "video_input": True,
    },
    # "type": "motion" = act / motion transfer: animate a reference image
    # (first_frame) with the motion of a source video (video_input). Same shape
    # as Recast; tagged "motion". Some models take a std/pro mode, some don't.
    "wananimatemovev1": {
        "label": "Wan Animate Move",
        "type": "motion",
        "options": ["mode"],
        "modes": ["std", "pro"],
        "video_input": True,
    },
    "klingmotion26v1": {
        "label": "Kling 2.6 Motion",
        "type": "motion",
        "options": ["mode"],
        "modes": ["std", "pro"],
        "video_input": True,
    },
    "klingmotion3v1": {
        "label": "Kling 3.0 Motion",
        "type": "motion",
        "options": ["mode"],
        "modes": ["std", "pro"],
        "video_input": True,
    },
    "actionimitationv1": {"label": "Action Imitation", "type": "motion", "options": [], "video_input": True},
    "actionimitationv2v1": {"label": "Action Imitation v2", "type": "motion", "options": [], "video_input": True},
    "runwayacttwov1": {"label": "Runway Act-Two", "type": "motion", "options": [], "video_input": True},
    # "type": "lipsync" drives a reference image (first_frame) with an uploaded
    # audio track (audio_input). No source video; resolution falls back to the
    # engine config (v1_video.py) where the model offers one.
    "omnihumanv1": {"label": "OmniHuman", "type": "lipsync", "options": []},
    "omnihuman15v1": {"label": "OmniHuman 1.5", "type": "lipsync", "options": []},
    "hedracharv3v1": {"label": "Hedra Character 3", "type": "lipsync", "options": []},
    "h3lipsyncv1": {"label": "Pollo H3 Lip-sync", "type": "lipsync", "options": []},
    "minimaxh3v1": {
        "label": "MiniMax H3",
        "type": "img2vid",
        "lengths": list(range(4, 16)),
        "resolutions": ["480p", "768p", "2K"],
        "ratios": ["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
        "options": ["image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 15, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "minimaxh3max": {
        "label": "MiniMax H3 Max",
        "type": "img2vid",
        "lengths": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "resolutions": ["480p", "768p", "1080p"],
        "ratios": ["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
        "options": ["image_tail", "refs"],
        "ref_mode": {"types": ["image", "video", "audio"], "max": 12, "limits": {"image": 9, "video": 3, "audio": 3}},
    },
    "wan27v1": {
        "label": "Wan 2.7",
        "type": "img2vid",
        "lengths": list(range(2, 16)),
        "resolutions": ["720p", "1080p"],
        "ratios": ["16:9", "1:1", "4:3", "3:4", "9:16"],
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
    "wan30v1": {
        "label": "Wan 3.0",
        "type": "img2vid",
        "lengths": list(range(2, 31)),
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["adaptive", "16:9", "9:16", "4:3", "3:4", "1:1"],
        "options": ["generate_audio", "seed", "image_tail", "refs"],
        "ref_mode": {
            "types": ["image", "video", "audio", "file", "link"],
            "max": 22,
            "limits": {"image": 10, "video": 5, "audio": 5, "file": 1, "link": 1},
            "exclusive": ["file", "link"],
        },
    },
    "wan30primev1": {
        "label": "Wan 3.0 Prime",
        "type": "img2vid",
        "lengths": list(range(2, 31)),
        "resolutions": ["480p", "720p", "1080p"],
        "ratios": ["adaptive", "16:9", "9:16", "4:3", "3:4", "1:1"],
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
    "sora2v1": {"label": "Sora 2", "type": "img2vid", "options": []},
    "sora2prov1": {"label": "Sora 2 Pro", "type": "img2vid", "options": []},
    "veo31v1": {"label": "Veo 3.1", "type": "img2vid", "options": ["generate_audio", "image_tail"]},
    "veo31fastv1": {"label": "Veo 3.1 Fast", "type": "img2vid", "options": ["generate_audio", "image_tail"]},
    "veo31litev1": {"label": "Veo 3.1 Lite", "type": "img2vid", "options": ["image_tail"]},
    "hailuo23v1": {"label": "Hailuo 2.3", "type": "img2vid", "options": []},
    "hailuo03v1": {"label": "Hailuo 03", "type": "img2vid", "options": ["image_tail"]},
    "pollo26v1": {
        "label": "Pollo 2.6",
        "type": "img2vid",
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
    },
    "pollo26fastv1": {
        "label": "Pollo 2.6 Fast",
        "type": "img2vid",
        "options": ["generate_audio", "web_search", "seed", "image_tail"],
    },
    "wan25v1": {"label": "Wan 2.5", "type": "img2vid", "options": ["generate_audio", "seed"]},
    "wan26v1": {"label": "Wan 2.6", "type": "img2vid", "options": ["generate_audio", "seed"]},
    "grokvideo15v1": {"label": "Grok Imagine Video 1.5", "type": "img2vid", "options": []},
    "klingv4v1": {"label": "Kling 4.0", "type": "img2vid", "options": ["image_tail"]},
    "klingv21v1": {
        "label": "Kling 2.1",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "lengths": [5, 10],
        "resolutions": ["std", "pro"],  # quality tiers, sent as Kling's "mode"
        "ratios": ["16:9", "9:16", "1:1"],
        "options": [],
        "note": "Image-to-video only — needs a source image.",
    },
    "klingv21masterv1": {
        "label": "Kling 2.1 Master",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "lengths": [5, 10],
        "ratios": ["16:9", "9:16", "1:1"],
        "options": [],
    },
    "klingv25turbov1": {
        "label": "Kling 2.5 Turbo",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "lengths": [5, 10],
        "resolutions": ["std", "pro"],  # quality tiers, sent as Kling's "mode"
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["image_tail"],
    },
    "klingvideoo1v1": {
        "label": "Kling Video O1",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "lengths": [5, 10],
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["image_tail"],
    },
    "klingv26v1": {
        "label": "Kling 2.6",
        "type": "img2vid",
        "hidden": "Superseded by the Kling 3.0 models",  # 2026-10-07
        "lengths": [5, 10],
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["generate_audio", "image_tail"],
    },
    "klingv3v1": {
        "label": "Kling 3.0",
        "type": "img2vid",
        "lengths": list(range(3, 16)),
        "resolutions": ["std", "pro", "4K"],  # quality tiers, sent as Kling's "mode"
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["generate_audio", "image_tail"],
    },
    "klingv3turbov1": {
        "label": "Kling 3.0 Turbo",
        "type": "img2vid",
        "lengths": list(range(3, 16)),
        "resolutions": ["720p", "1080p"],
        "ratios": ["16:9", "9:16", "1:1"],
        "options": [],
    },
    "klingv3omniv1": {
        "label": "Kling 3.0 Omni",
        "type": "img2vid",
        "lengths": list(range(3, 16)),
        "resolutions": ["std", "pro", "4K"],  # quality tiers, sent as Kling's "mode"
        "ratios": ["16:9", "9:16", "1:1"],
        "options": ["generate_audio", "image_tail"],
    },
    "pollojourneyv1": {
        "label": "Pollo Journey 8.2",
        "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["seed", "images"],
    },
    "seedreamv1": {
        "label": "Seedream 5.0 Lite",
        "type": "image",
        "ratios": ["1:1", "16:9", "3:2", "2:3", "3:4", "4:3", "9:16", "21:9"],
        "resolutions": ["2K", "3K", "4K"],
        "options": ["images"],
    },
    "nanobanana2v1": {
        "label": "Nano Banana 2",
        "type": "image",
        "ratios": ["1:1", "9:16", "16:9", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9", "1:4", "4:1", "8:1", "1:8"],
        "resolutions": ["0.5K", "1K", "2K", "4K"],
        "options": ["images"],
    },
    "klingv3imagev1": {
        "label": "Kling 3.0 Image",
        "type": "image",
        "ratios": ["1:1", "3:2", "2:3", "3:4", "4:3", "16:9", "9:16", "21:9"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "klingv3omniimagev1": {
        "label": "Kling 3.0 Omni Image",
        "type": "image",
        "ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9", "auto"],
        "resolutions": ["1K", "2K", "4K"],
        "options": ["images"],
    },
    "qwenimage": {
        "label": "Qwen Image",
        "type": "image",
        "hidden": "Not enabled for API access on this key (403)",  # checked with real requests 2026-10-06
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],  # text-to-image only; an edit keeps the image's shape
        "options": ["images"],
        "legacy": True,
        "legacy_only": True,  # v1 qwen/* endpoints 404 — offered in both modes
    },
    "seedreamflashv1": {
        "label": "Seedream 5.0 Flash",
        "type": "image",
        "hidden": "Not enabled for API access on this key (403)",  # real requests 2026-10-06, 2026-10-18
        "ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "resolutions": ["1K", "1.5K", "2K"],
        "options": ["images"],
    },
    "seedreamprov1": {
        "label": "Seedream 5.0 Pro",
        "type": "image",
        "hidden": "Not enabled for API access on this key (403)",  # real requests 2026-10-06, 2026-10-18
        "ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "qwenimage3v1": {
        "label": "Qwen Image 3",
        "type": "image",
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "qwenimage3prov1": {
        "label": "Qwen Image 3 Pro",
        "type": "image",
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "qwenimageflashv1": {
        "label": "Qwen Image Flash",
        "type": "image",
        "hidden": "Pollo says it's currently unavailable",  # 403 on 2026-10-06; "currently unavailable" on 2026-10-18
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],
        "options": [],
    },
    # --- Newer frontier image models (added 2026-11). Ratios/resolutions live
    # in the engine config (v1_image.py). ---
    "nanobananaprov1": {"label": "Nano Banana Pro", "type": "image", "options": ["images"]},
    "nanobanana21v1": {"label": "Nano Banana 2.1", "type": "image", "options": ["images"]},
    "fluxkontextprov1": {"label": "Flux Kontext Pro", "type": "image", "options": ["images"]},
    "fluxkontextmaxv1": {"label": "Flux Kontext Max", "type": "image", "options": ["images"]},
    "flux2maxv1": {"label": "Flux 2 Max", "type": "image", "options": ["images"]},
    "gptimage25v1": {"label": "GPT Image 2.5", "type": "image", "options": ["images"]},
    "seedream45v1": {"label": "Seedream 4.5", "type": "image", "options": ["images"]},
    "midjourneyv82v1": {"label": "Midjourney v8.2", "type": "image", "options": ["images"]},
    "grokimage20v1": {"label": "Grok Imagine Image 2.0", "type": "image", "options": ["images"]},
    "recraftv3v1": {"label": "Recraft v3", "type": "image", "options": []},
    "ideogramv2turbov1": {"label": "Ideogram v2 Turbo", "type": "image", "options": []},
    # Audio models. "type": "speech" = text-to-speech ("voice" option: a voice
    # id from Pollo's voice list; "tuning": speed/volume/pitch), "music" = Suno
    # ("instrumental", lyrics mode via style + title, "duration" on v5.5).
    "seedaudio10v1": {"label": "Seed Audio 1.0", "type": "speech", "options": ["tuning"]},
    "minimaxspeech28hdv1": {"label": "MiniMax Speech 2.8 HD", "type": "speech", "options": ["voice"]},
    "elevenv3v1": {"label": "ElevenLabs v3", "type": "speech", "options": ["voice"]},
    "sunov45plusv1": {"label": "Suno v4.5+", "type": "music", "options": ["instrumental", "lyrics"]},
    "sunov5v1": {"label": "Suno v5", "type": "music", "options": ["instrumental", "lyrics"]},
    "sunov55v1": {"label": "Suno v5.5", "type": "music", "options": ["instrumental", "lyrics", "duration"]},
}
