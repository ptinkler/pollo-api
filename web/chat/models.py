"""Pydantic request bodies for the chat API."""

from pydantic import BaseModel, Field

from .constants import DEFAULT_IMAGE_LIMIT


class ConversationCreate(BaseModel):
    title: str | None = None
    kind: str | None = None  # "chat" (default) or "gallery" — the thread's landing view
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    space_id: int | None = None  # the chat's space (null = unfiled)
    # Attached to this chat itself; the global and space defaults apply on top
    instruction_ids: list[int] = []
    instruction_group_ids: list[int] = []
    character_ids: list[int] = []
    hidden_defaults: dict[str, list[int]] = {}  # defaults switched off in this chat only
    paused_instructions: dict[str, list[int]] = {}  # snippets/groups paused in this chat


class ConversationUpdate(BaseModel):
    title: str | None = None
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    space_id: int | None = None  # explicit null moves the chat to Unfiled
    instruction_ids: list[int] | None = None  # explicit [] detaches all snippets
    instruction_group_ids: list[int] | None = None  # explicit [] detaches all groups
    character_ids: list[int] | None = None
    # Defaults switched off in this chat only: {kind: [ids]} (kinds as in _KINDS)
    hidden_defaults: dict[str, list[int]] | None = None
    # Instruction snippets/groups paused in this chat: {"instruction" |
    # "instruction_group": [ids]} — attached but not sent until resumed
    paused_instructions: dict[str, list[int]] | None = None
    pinned: bool | None = None
    kind: str | None = None  # "chat" or "gallery"


class InstructionIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(default="", max_length=20000)


class InstructionGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    snippet_ids: list[int] = []


# Global defaults and a space's defaults share this shape (three id-lists)
class DefaultsIn(BaseModel):
    default_character_ids: list[int] = []
    default_instruction_ids: list[int] = []
    default_instruction_group_ids: list[int] = []


class SpaceIn(DefaultsIn):
    name: str = Field(min_length=1, max_length=255)


class TurnOptions(BaseModel):
    aspect_ratio: str | None = None
    resolution: str | None = None
    duration: int | None = None
    generate_audio: bool | None = None


class RefChoices(BaseModel):
    """The composer's reference picks: chat files or "char:" refs."""

    on: list[str] = []  # sent ahead of the automatic picks
    off: list[str] = []  # never sent


class TurnSettings(BaseModel):
    mode: str = "auto"  # auto | text | image | video
    history_limit: int | None = Field(default=None, ge=1)  # past messages sent to the chat model; None = all
    image_limit: int | None = Field(default=DEFAULT_IMAGE_LIMIT, ge=0)  # chat images per request; None = all
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    # The composer's picks, applied in every mode (Auto included). Unset =
    # the chat model's choice (Auto), else the media model's default.
    image_options: TurnOptions = TurnOptions()
    video_options: TurnOptions = TurnOptions()
    ref_choices: RefChoices = RefChoices()


class EstimateRequest(BaseModel):
    model: str
    kind: str  # image | video
    duration: int | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    generate_audio: bool | None = None
    n_images: int = 0


class SendMessage(TurnSettings):
    content: str = ""
    attachments: list[str] = []  # filenames returned by the attachments endpoint
    lane: str | None = None  # 'gallery' = a standalone exchange beside the chat


class RetryMessage(TurnSettings):
    message_id: int  # the assistant message to regenerate


class EditMessage(TurnSettings):
    message_id: int  # the user message to rewrite and resend
    content: str


class SwitchBranch(BaseModel):
    message_id: int  # show the branch this message is on (its newest version)


class ForkConversation(BaseModel):
    message_id: int  # a prompt (the new chat ends with it and its reply) or a reply


class EnhancePrompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    model: str  # the chat model that rewrites it
    kind: str = "image"  # "image" or "video"
