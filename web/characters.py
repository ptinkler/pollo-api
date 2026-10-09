"""
Characters — reusable people/creatures/mascots shared by chat and the
Generate page: a name, a description and a few reference images.

Attached to a chat (ChatConversation.character_ids) or a generation
(`character_ids` on /api/generate and /api/generate-image), a character's
description is added to the prompt and its images go to the model as
reference images, so it looks the same from one image to the next.

A character made inside a chat is *ad hoc* (Character.conversation_id set):
it only shows in that chat and is deleted with it, until it's promoted to a
saved character (conversation_id None), which can be attached anywhere.

Images live under <data>/characters/<id>/. Elsewhere they're referred to as
"char:<id>/<file>" (e.g. in a chat image's stored reference list).
"""
import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from img2vid.common import config
from img2vid.common.metadata import get_db

from .auth import verify_api_key
from .uploads import image_media_type, read_image_upload, safe_filename

router = APIRouter(prefix="/api/characters", dependencies=[Depends(verify_api_key)])

MAX_IMAGES = 6            # stored per character
REF_PREFIX = "char:"


# ── Storage ─────────────────────────────────────────────────────────

def char_dir(character_id: int) -> Path:
    # Read config at call time so tests can redirect ROOT_DIR
    return config.ROOT_DIR / "characters" / str(character_id)


def image_ref(character_id: int, file: str) -> str:
    return f"{REF_PREFIX}{character_id}/{file}"


def ref_path(ref: str) -> Path | None:
    """The file behind a "char:<id>/<file>" reference (None if it isn't one)."""
    if not ref.startswith(REF_PREFIX):
        return None
    cid, _, file = ref[len(REF_PREFIX):].partition("/")
    if not cid.isdigit() or not file or Path(file).name != file or file.startswith("."):
        return None
    return char_dir(int(cid)) / file


# ── Helpers for chat and generations ───────────────────────────────

def load(ids: list[int] | None, db=None) -> list:
    """The characters with these ids, in that order (missing ones skipped)."""
    db = db or get_db()
    chars = [db.get_character(i) for i in dict.fromkeys(ids or [])]
    return [c for c in chars if c]


def require(ids: list[int] | None, db=None) -> list:
    """Like load(), but 400 if any id doesn't exist."""
    chars = load(ids, db)
    if len(chars) != len(set(ids or [])):
        raise HTTPException(400, "Character not found")
    return chars


def available(conv_id: str | None, db=None) -> list:
    """The characters a chat can use: every saved one plus its own ad-hoc ones."""
    db = db or get_db()
    return [c for c in db.list_characters() if c.conversation_id is None or c.conversation_id == conv_id]


def _has_name(text: str, name: str) -> bool:
    name = name.strip()
    return bool(name) and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE) is not None


def _part_of(char, other) -> bool:
    """Whether char's name is a shorter whole-word part of other's ("Chloe" in "Chloe Muscle")."""
    return other.id != char.id and len(other.name.strip()) > len(char.name.strip()) and _has_name(other.name, char.name)


def _short_name(char, chars: list) -> str | None:
    """A multi-word name's first word ("Chloe" for "Chloe Muscle"), when it
    picks out this character alone: no other character is called that or
    shares the first word."""
    words = char.name.split()
    if len(words) < 2:
        return None
    first = words[0].lower()
    if any(c.id != char.id and (c.name.strip().lower() == first or c.name.split()[0].lower() == first)
           for c in chars):
        return None
    return words[0]


def mentioned(chars: list, text: str, prefer: list = ()) -> list:
    """The characters named in the text as a whole word (any case), by full
    name or by an unambiguous short name. A name that's part of a longer
    matched name, or of a `prefer` character's name, means that character:
    "Chloe" in a picture of "Chloe Muscle" is her, not another "Chloe"."""
    found = [c for c in chars if _has_name(text, c.name)]
    covering = found + list(prefer)
    found = [c for c in found if not any(_part_of(c, o) for o in covering)]
    short = [c for c in chars if c not in found and c not in prefer
             and (n := _short_name(c, chars)) and _has_name(text, n)]
    return found + short


def named(chars: list, names) -> list:
    """The characters these names (from the chat model) refer to, by full
    name or unambiguous short name."""
    out = []
    for n in names or []:
        n = str(n).strip().lower()
        hit = next((c for c in chars if c.name.strip().lower() == n), None) or \
            next((c for c in chars if (s := _short_name(c, chars)) and s.lower() == n), None)
        if hit and hit not in out:
            out.append(hit)
    return out


def create_from_files(name: str, description: str, files: list[Path], conversation_id: str | None, db=None):
    """A new character with copies of these image files (ad hoc in `conversation_id` if set)."""
    db = db or get_db()
    char = db.create_character(name, description, conversation_id)
    d = char_dir(char.id)
    d.mkdir(parents=True, exist_ok=True)
    names = []
    for f in files[:MAX_IMAGES]:
        name_on_disk = f"img_{uuid.uuid4().hex[:12]}{f.suffix.lower()}"
        shutil.copyfile(f, d / name_on_disk)
        names.append(name_on_disk)
    return db.update_character(char.id, images=names)


def copy_to_conversation(char, conversation_id: str, db=None):
    """A copy of a character, ad hoc in another chat (a branch of the one it
    was made in), its images kept under the same file names."""
    db = db or get_db()
    copy = db.create_character(char.name, char.description, conversation_id)
    d = char_dir(copy.id)
    d.mkdir(parents=True, exist_ok=True)
    files = [f for f in char.images if (char_dir(char.id) / f).is_file()]
    for f in files:
        shutil.copyfile(char_dir(char.id) / f, d / f)
    return db.update_character(copy.id, images=files)


def describe(chars: list) -> str:
    """The characters as a prompt block ('' for none)."""
    if not chars:
        return ""
    lines = [f"- {c.name}: {c.description.strip()}" if c.description.strip() else f"- {c.name}" for c in chars]
    return "Characters (keep each one's appearance consistent with this description and the reference images):\n" \
        + "\n".join(lines)


def with_characters(prompt: str, chars: list) -> str:
    """The prompt with the characters' descriptions appended."""
    block = describe(chars)
    return f"{prompt}\n\n{block}" if block else prompt


def reference_refs(chars: list, limit: int | None = None) -> list[str]:
    """The characters' "char:" image refs (up to `limit`, None = all): each
    character's first image, then their second, and so on — so every
    character gets in before any gets two."""
    refs: list[str] = []
    for i in range(MAX_IMAGES):
        for c in chars:
            files = c.images
            if i < len(files) and (char_dir(c.id) / files[i]).is_file():
                refs.append(image_ref(c.id, files[i]))
                if limit is not None and len(refs) >= limit:
                    return refs
    return refs


def delete_for_conversation(conv_id: str, db=None) -> None:
    """Delete a chat's ad-hoc characters and their files (the chat is being deleted)."""
    db = db or get_db()
    for c in db.list_characters():
        if c.conversation_id == conv_id:
            _delete(c.id, db)


def _delete(character_id: int, db) -> None:
    db.delete_character(character_id)
    shutil.rmtree(char_dir(character_id), ignore_errors=True)
    for conv in db.list_conversations(limit=100000):
        if character_id in conv.character_ids:
            db.update_conversation(conv.id, character_ids=[i for i in conv.character_ids if i != character_id])


# ── Request models ──────────────────────────────────────────────────

class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=4000)
    conversation_id: str | None = None   # set = ad hoc in that chat (and attached to it)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=4000)
    images: list[str] | None = None      # reorder (first = main) or drop images


class CopyFromChat(BaseModel):
    conversation_id: str
    file: str


class CopyFromGeneration(BaseModel):
    project: str
    filename: str


# ── Routes ──────────────────────────────────────────────────────────

def _require_char(character_id: int):
    char = get_db().get_character(character_id)
    if not char:
        raise HTTPException(404, "Character not found")
    return char


@router.get("")
def api_list_characters(conversation_id: str | None = None, include_adhoc: bool = False):
    """Saved characters, plus the ad-hoc ones of `conversation_id` (a chat
    shows its own), or every ad-hoc one too with include_adhoc (management page)."""
    db = get_db()
    titles = {}
    if include_adhoc:
        titles = {c.id: c.title for c in db.list_conversations(limit=100000)}
    items = []
    for c in db.list_characters():
        if c.conversation_id is None or include_adhoc or c.conversation_id == conversation_id:
            items.append({**c.to_dict(), "conversation_title": titles.get(c.conversation_id)})
    return {"characters": items}


@router.post("")
def api_create_character(data: CharacterIn):
    db = get_db()
    conv = None
    if data.conversation_id:
        conv = db.get_conversation(data.conversation_id)
        if not conv:
            raise HTTPException(400, "Conversation not found")
    char = db.create_character(data.name.strip(), data.description.strip(), data.conversation_id)
    if conv:
        db.update_conversation(conv.id, character_ids=conv.character_ids + [char.id])
    return char.to_dict()


@router.get("/{character_id}")
def api_get_character(character_id: int):
    return _require_char(character_id).to_dict()


@router.patch("/{character_id}")
def api_update_character(character_id: int, data: CharacterUpdate):
    char = _require_char(character_id)
    fields = data.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in fields:
        fields["name"] = fields["name"].strip()
    if "description" in fields:
        fields["description"] = fields["description"].strip()
    if "images" in fields:
        keep = [f for f in dict.fromkeys(fields["images"]) if f in char.images]
        if set(keep) != set(fields["images"]):
            raise HTTPException(400, "Unknown image")
        for f in set(char.images) - set(keep):
            (char_dir(character_id) / f).unlink(missing_ok=True)
        fields["images"] = keep
    return get_db().update_character(character_id, **fields).to_dict()


@router.delete("/{character_id}")
def api_delete_character(character_id: int):
    """Delete a character and its images. Chats/generations that used it keep
    working; it's just no longer sent."""
    _require_char(character_id)
    _delete(character_id, get_db())
    return {"deleted": character_id}


@router.post("/{character_id}/promote")
def api_promote_character(character_id: int):
    """Turn an ad-hoc chat character into a saved one, attachable anywhere."""
    _require_char(character_id)
    return get_db().update_character(character_id, conversation_id=None).to_dict()


def _add_image(char, content: bytes, ext: str) -> dict:
    if len(char.images) >= MAX_IMAGES:
        raise HTTPException(400, f"A character can have up to {MAX_IMAGES} images")
    name = f"img_{uuid.uuid4().hex[:12]}{ext}"
    d = char_dir(char.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(content)
    return get_db().update_character(char.id, images=char.images + [name]).to_dict()


def add_image_from_file(char, source: Path) -> dict:
    """Copy an image file into the character (used by the media library too)."""
    if not source.is_file() or not image_media_type(source):
        raise HTTPException(404, "Image not found")
    return _add_image(char, source.read_bytes(), source.suffix.lower())


@router.post("/{character_id}/images")
async def api_upload_character_image(character_id: int, file: UploadFile = File(...)):
    char = _require_char(character_id)
    content, ext = await read_image_upload(file)
    return _add_image(char, content, ext)


@router.post("/{character_id}/images/from-chat")
def api_character_image_from_chat(character_id: int, data: CopyFromChat):
    """Copy an image from a chat (uploaded or generated) into the character."""
    char = _require_char(character_id)
    return add_image_from_file(char, config.ROOT_DIR / "chat" / safe_filename(data.conversation_id) / safe_filename(data.file))


@router.post("/{character_id}/images/from-generation")
def api_character_image_from_generation(character_id: int, data: CopyFromGeneration):
    """Copy a generated image from a project into the character."""
    from . import api   # web.api imports this module's router, so import it lazily
    char = _require_char(character_id)
    proj = get_db().get_project_by_slug(data.project)
    if not proj:
        raise HTTPException(404, "Project not found")
    return add_image_from_file(char, api.ASSETS_DIR / proj.assets_folder / safe_filename(data.filename))


@router.get("/{character_id}/images/{filename}")
def api_character_image(character_id: int, filename: str):
    path = char_dir(character_id) / safe_filename(filename)
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type=image_media_type(path),
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})
