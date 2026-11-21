"""The subtitle builder must reproduce the narration exactly: no repeats, no drops, in order."""
import importlib.util
import sys
from pathlib import Path

import pytest

VIDEO = Path(__file__).resolve().parent.parent / "video" / "make_video.py"
pytest.importorskip("edge_tts")
pytest.importorskip("playwright")
pytest.importorskip("imageio_ffmpeg")

spec = importlib.util.spec_from_file_location("make_video", VIDEO)
mv = importlib.util.module_from_spec(spec)
sys.modules["make_video"] = mv
spec.loader.exec_module(mv)


def spoken(text):
    """Fake voice-engine timings: one word every 0.4 s, punctuation stripped as the engine does."""
    out = []
    for i, raw in enumerate(text.split()):
        out.append({"t": i * 0.4, "d": 0.35, "w": raw.strip(".,:;?!")})
    return out


TEXT = ("Who holds the Operator? aspas, in 97 percent of MIBR's Operator rounds. In the first twenty seconds the "
        "Operator sets up at B Yellow in 16 of 37 of them. Pick one, and it replays in 2D, straight from the feed: "
        "every player, every ability, every kill.")


def test_cues_cover_the_script_exactly_once_and_in_order():
    cues = mv.cues_for(TEXT, spoken(TEXT))
    assert " ".join(t for _, _, t in cues) == TEXT          # nothing repeated, nothing dropped
    starts = [a for a, _, _ in cues]
    assert starts == sorted(starts)
    assert all(b > a for a, b, _ in cues)


def test_cues_stay_readable():
    cues = mv.cues_for(TEXT, spoken(TEXT))
    assert max(len(t) for _, _, t in cues) <= mv.MAX_CUE_CHARS + 12   # a long single word may overshoot a little
    assert "Who holds the Operator?" in [t for _, _, t in cues]       # sentences end a cue


def test_repeated_words_map_to_the_right_occurrence():
    text = "In the first round, in the second round, in the third round they held the same angle."
    cues = mv.cues_for(text, spoken(text))
    assert " ".join(t for _, _, t in cues) == text


def test_a_word_the_engine_rephrases_does_not_break_alignment():
    text = "They won 54% of rounds. Then they lost."
    words = spoken(text)
    words[2]["w"] = "54 percent"          # the engine reads the symbol aloud
    cues = mv.cues_for(text, words)
    joined = " ".join(t for _, _, t in cues)
    assert joined.startswith("They won") and joined.endswith("Then they lost.")
