"""
Everything that differs between kinds of source.

Adding a kind (podcast, film, talk) should be one entry here plus a migration
for the new choice, not branches spread across models, views, templates and
JavaScript. The pages read these definitions through `kinds_context`.
"""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SourceKind:
    value: str
    # What to call the source and the person behind it, on screen.
    label: str
    title_label: str
    creator_label: str
    # Placeholder for Capture's attribution line.
    attribution_hint: str
    # Where a passage sits: a page for print, a position in audio for recordings.
    locator: str
    locator_label: str
    locator_hint: str
    # Shown in the margin when a passage has no position of its own.
    marker: str = ""
    # Lyrics are read line by line; prose reflows into paragraphs.
    keeps_line_breaks: bool = False


BOOK = SourceKind(
    value="book",
    label="Book",
    title_label="Book title",
    creator_label="Author",
    attribution_hint="book | author | p. 42",
    locator="page",
    locator_label="Page number (optional)",
    locator_hint="e.g. 42",
)

SONG = SourceKind(
    value="song",
    label="Song",
    title_label="Song",
    creator_label="Artist",
    attribution_hint="song | artist | 2:31",
    locator="timestamp",
    locator_label="Timestamp (optional)",
    locator_hint="e.g. 2:31",
    marker="♪",
    keeps_line_breaks=True,
)

SOURCE_KINDS = {kind.value: kind for kind in (BOOK, SONG)}
DEFAULT_KIND = BOOK.value
KIND_CHOICES = [(kind.value, kind.label) for kind in SOURCE_KINDS.values()]


def get_kind(value: str | None) -> SourceKind:
    """The named kind, falling back to books for anything unknown."""
    return SOURCE_KINDS.get((value or "").strip().lower(), SOURCE_KINDS[DEFAULT_KIND])


def kinds_context() -> list[dict]:
    """The definitions in a form the pages can render and their scripts can read."""
    return [asdict(kind) for kind in SOURCE_KINDS.values()]
