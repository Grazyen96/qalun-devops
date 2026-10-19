"""The one place the web layer calls QuranText.

The same steps the desktop app takes for a subtitle export, without a window:
detect and time the ayat, make a project from the match, write the subtitle
files from it. Only the local engine is used, so a job never uploads the
recording anywhere or bills anyone.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from qurantext.config.paths import QURAN_DB_PATH, resolve_quran_path
from qurantext.data.quran_db import ensure_quran_db, list_surahs
from qurantext.jobs.project import Project
from qurantext.jobs.project_render import export_project_subtitles
from qurantext.pipelines.detection import run_detection
from qurantext.utils.progress import ProgressCallback

SUBTITLE_FORMATS = ("srt", "vtt")


@lru_cache(maxsize=1)
def surahs() -> tuple[dict, ...]:
    """Every surah's number, name and ayah count, from the text that ships with QuranText."""
    conn = ensure_quran_db(resolve_quran_path(None), QURAN_DB_PATH)
    try:
        return tuple(list_surahs(conn))
    finally:
        conn.close()


def surah_name(number: int) -> str:
    """The name QuranText's range search filters by: it matches names, not numbers."""
    for surah in surahs():
        if surah["surah_num"] == number:
            return surah["name"]
    raise ValueError(f"There is no surah {number}.")


def run_qurantext(
    audio: Path,
    *,
    mode: str,
    surah: int | None,
    workdir: Path,
    progress: ProgressCallback,
) -> dict[str, Path]:
    match = workdir / "matches.json"
    run_detection(
        quran=resolve_quran_path(None),
        output=match,
        mode=mode,
        audio=audio,
        engine="local",
        surah=None if surah is None else surah_name(surah),
        echo=False,
        progress=progress,
    )
    project = Project.from_match_file(match, audio, mode=mode)
    # The stem is a video's path because that is what the export expects: it
    # swaps the suffix, and would cut a stem with a dot in it at that dot.
    written = export_project_subtitles(project, workdir / "subtitles.mp4", SUBTITLE_FORMATS)
    files = {path.suffix.lstrip("."): path for path in written}
    files["json"] = match
    return files
