"""
Pollo's video and image models as the Generate page shows them: labels,
lengths, ratios, resolutions and which options each one takes.
"""

# "legacy": True marks a model as living on Pollo's pre-v1 API
# (POLLO_API_BASE, no "/v1/" in the URL) — see BaseV1VideoGenerator's
# docstring in img2vid/pollo/generators.py. These are hidden from the model
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
    # ── v1 API (current — https://docs.pollo.ai) ─────────────────────
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
        "hidden": "Not enabled for API access on this key (403)",  # checked with real requests 2026-10-06
        "ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "resolutions": ["1K", "1.5K", "2K"],
        "options": ["images"],
    },
    "seedreamprov1": {
        "label": "Seedream 5.0 Pro",
        "type": "image",
        "hidden": "Not enabled for API access on this key (403)",  # checked with real requests 2026-10-06
        "ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "qwenimage3v1": {
        "label": "Qwen Image 3",
        "type": "image",
        "hidden": "Pollo doesn't serve it to this key yet (404)",  # checked with real requests 2026-10-06
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "qwenimage3prov1": {
        "label": "Qwen Image 3 Pro",
        "type": "image",
        "hidden": "Pollo doesn't serve it to this key yet (404)",  # checked with real requests 2026-10-06
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],
        "resolutions": ["1K", "2K"],
        "options": ["images"],
    },
    "qwenimageflashv1": {
        "label": "Qwen Image Flash",
        "type": "image",
        "hidden": "Not enabled for API access on this key (403)",  # checked with real requests 2026-10-06
        "ratios": ["1:1", "3:4", "4:3", "16:9", "9:16"],
        "options": [],
    },
}
