from pathlib import Path


def get_from_file(file_path: str) -> str:
    try:
        with open(file_path, 'r') as f:
            content = f.read().strip()

        if not content:
            raise ValueError(f"{file_path} file is empty")

        return content
    except FileNotFoundError:
        raise FileNotFoundError(f"{file_path} file not found")
    except Exception as e:
        raise RuntimeError(f"Error reading {file_path} file: {e}")


def _get_optional_file(project: str, filename: str) -> str | None:
    """Read a project file, returning None if missing/empty."""
    try:
        return get_from_file(f"projects/{project}/{filename}")
    except (FileNotFoundError, ValueError, RuntimeError):
        return None


def get_prompt(project: str) -> str:
    return get_from_file(f"projects/{project}/prompt.txt")


def get_image_url(project: str) -> str | None:
    """Get image URL from project, returns None if not found (text-only mode)."""
    return _get_optional_file(project, "image_url.txt")


def get_image_path(project: str) -> Path | None:
    """Get image path from project, returns None if not found (text-only mode)."""
    project_dir = Path(f"projects/{project}")
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        path = project_dir / f"image{ext}"
        if path.exists():
            return path
    return None


def get_video_url(project: str) -> str | None:
    """Get video URL from project for ref/edit mode, returns None if not found."""
    return _get_optional_file(project, "video_url.txt")


def get_subject_url(project: str) -> str | None:
    """Get subject/reference image URL for ref mode, returns None if not found."""
    return _get_optional_file(project, "subject_url.txt")


def get_audio_url(project: str) -> str | None:
    """Get audio URL for ref mode, returns None if not found."""
    return _get_optional_file(project, "audio_url.txt")
