"""QuranText's real pipeline on a real recording.

Skipped unless QALUN_E2E_AUDIO names a short recitation (about a minute is
plenty); the recording is not in the repository. QALUN_E2E_SURAH gives its
surah, since a short clip is quicker to time when the range search is narrowed.

    QALUN_E2E_AUDIO=~/clips/furqan-7-11.mp3 QALUN_E2E_SURAH=25 pytest -m e2e
"""

import os
from pathlib import Path

import pytest

from qalun_web.pipeline import run_qurantext

AUDIO = os.getenv("QALUN_E2E_AUDIO")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not AUDIO, reason="QALUN_E2E_AUDIO names no recording"),
]


def test_a_recitation_comes_back_as_subtitles_and_a_match(tmp_path):
    surah = os.getenv("QALUN_E2E_SURAH")
    events = []

    files = run_qurantext(
        Path(AUDIO).expanduser(),
        mode="recitation",
        surah=int(surah) if surah else None,
        workdir=tmp_path,
        progress=events.append,
    )

    assert sorted(files) == ["json", "srt", "vtt"]
    srt = files["srt"].read_text(encoding="utf-8-sig")
    assert " --> " in srt
    # Arabic letters, so the cues carry the ayat and not an empty shell.
    assert any("؀" <= ch <= "ۿ" for ch in srt)
    assert files["vtt"].read_text(encoding="utf-8").startswith("WEBVTT")
    assert events, "the pipeline reported no progress"
