"""The two pure helpers the transcript and case data depend on."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agent import clean_text, digits


def test_clean_text_strips_expressive_tags():
    """Expressive TTS embeds <expr/> tags; staff must never see them in the transcript."""
    raw = '<expr type="expression" label="calm"/> Hello,  <expr label="happy"/>how can I\nhelp?'
    assert clean_text(raw) == "Hello, how can I help?"


def test_clean_text_plain_passthrough():
    """Text without tags is untouched, so a future TTS without tags still works."""
    assert clean_text("Case C-1001 is open.") == "Case C-1001 is open."


def test_digits_normalizes_spoken_phone():
    """Callers say numbers with dots, dashes and spaces; lookup must match what create stored."""
    assert digits("925.915-7062") == "9259157062"
    assert digits("(555) 123 4567") == "5551234567"
