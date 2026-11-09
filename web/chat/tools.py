"""The system/title prompts and the generate_* / create_* tool schemas the
chat model is given, plus the helper that adds the `characters` argument."""

TITLE_PROMPT = """Write a short title, 2 to 6 words, for a chat that starts with the message below. \
Reply with the title alone: no quotes, no "Title:", no full stop.

Message:
{prompt}"""

SYSTEM_PROMPT = """You are an assistant in a chat app. You have generate_image, generate_video and \
generate_audio tools, which create media with the models the user has selected; the result is shown \
to the user in the chat.

When tools aren't available, bracketed notes in the conversation history record media that was \
produced earlier.

Today's date is {today}."""

IMAGE_TOOL_RESULT = "Image generated; it is shown to the user."
VIDEO_TOOL_RESULT = "Video job started; it is shown to the user once rendering finishes."
AUDIO_TOOL_RESULT = "Audio job started; it is shown to the user once it is ready."

TOOLS_IMAGE = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": (
            "Generate an image from a text prompt. Earlier images in the conversation can be passed to the "
            "image model as references, to keep characters consistent or to edit an image."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed description of the image to create."},
                "source_image": {
                    "type": "string",
                    "enum": ["none", "latest"],
                    "description": "'latest' to edit/transform the most recent image in the conversation.",
                },
                "keep_consistent": {
                    "type": "boolean",
                    "description": "true = also send the 2 most recent images in the conversation to the "
                    "image model as reference images. Default false. Images the user "
                    "has pinned are always sent as references.",
                },
            },
            "required": ["prompt"],
        },
    },
}

TOOLS_CREATE_CHARACTER = {
    "type": "function",
    "function": {
        "name": "create_character",
        "description": "Save a character (person, creature, mascot…) from the most recent image(s) in the "
        "conversation, so later images keep their look: from then on their description and "
        "reference images are sent to the image model whenever they appear. Use it when the user "
        "asks to make, save or keep using a character from an image. It's kept in this chat; "
        "the user can save it for use in other chats.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The character's name, as the user calls them."},
                "description": {
                    "type": "string",
                    "description": "Their appearance in detail, from the image: face, hair, build, "
                    "age, clothing, distinctive features, art style.",
                },
                "images": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 4,
                    "description": "How many of the most recent images show them (default 1: the latest).",
                },
            },
            "required": ["name", "description"],
        },
    },
}

TOOLS_CREATE_INSTRUCTION = {
    "type": "function",
    "function": {
        "name": "create_instruction",
        "description": "Save a reusable instruction snippet and attach it to this chat, so it is sent to you "
        "verbatim as a system instruction on every future reply here (and the user can group it or attach it "
        "to other chats). Use it when the user asks you to remember how they want you to behave — a tone, a "
        "format, a persona, standing do's and don'ts — or to save the way you're working now as a preset. "
        "Write the content compact and self-contained, as direct instructions to yourself ('You are…', "
        "'Always…', 'Never…'), not as a summary of the conversation. It is added alongside whatever is already "
        "attached and takes effect from your next reply.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "A short name for the preset, e.g. 'Picture-book storyteller'.",
                },
                "content": {
                    "type": "string",
                    "description": "The instruction text, written to be sent to you word for word.",
                },
            },
            "required": ["name", "content"],
        },
    },
}

TOOLS_AUDIO = {
    "type": "function",
    "function": {
        "name": "generate_audio",
        "description": (
            "Generate audio with the user's selected audio model: speech (the exact text to be spoken) or a "
            "song / music track (a description of it, or its lyrics). Voice and other settings are the "
            "user's to choose. Runs in the background."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The text to speak, or the music description / lyrics."},
            },
            "required": ["prompt"],
        },
    },
}

TOOLS_VIDEO = {
    "type": "function",
    "function": {
        "name": "generate_video",
        "description": (
            "Generate a short video from a text prompt, optionally animating the latest image in the "
            "conversation (used as the first frame). Runs in the background for a few minutes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the scene, action and camera motion.",
                },
                "duration": {"type": "integer", "description": "Length in seconds. Omit to use the model default."},
                "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]},
                "source_image": {
                    "type": "string",
                    "enum": ["none", "latest"],
                    "description": "'latest' to animate the most recent image in the conversation.",
                },
            },
            "required": ["prompt"],
        },
    },
}


def _with_character_arg(tool: dict, names: list[str]) -> dict:
    """A generate_* tool with a `characters` argument listing the usable characters."""
    if not names:
        return tool
    fn = tool["function"]
    params = fn["parameters"]
    return {
        **tool,
        "function": {
            **fn,
            "parameters": {
                **params,
                "properties": {
                    **params["properties"],
                    "characters": {
                        "type": "array",
                        "items": {"type": "string", "enum": names},
                        "description": "The user's characters who appear in it. Their descriptions and reference "
                        "images are sent to the model automatically, so the prompt needn't "
                        "describe their looks.",
                    },
                },
            },
        },
    }
