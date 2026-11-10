"""Cached video lengths for the media library (see models.MediaDuration)."""

from .models import MediaDuration


class MediaMixin:
    def media_durations(self) -> dict[str, tuple[int, float | None]]:
        """Every known length: path → (mtime it was read at, seconds)."""
        with self._session() as session:
            return {r.path: (r.mtime_ns, r.seconds) for r in session.query(MediaDuration).all()}

    def set_media_durations(self, rows: list[tuple[str, int, float | None]]) -> None:
        """Record lengths just read, one transaction for the lot. A path that's
        already known is updated, so a re-encoded file replaces its row."""
        if not rows:
            return
        with self._session() as session:
            for path, mtime_ns, seconds in rows:
                existing = session.get(MediaDuration, path)
                if existing:
                    existing.mtime_ns, existing.seconds = mtime_ns, seconds
                else:
                    session.add(MediaDuration(path=path, mtime_ns=mtime_ns, seconds=seconds))
            session.commit()
