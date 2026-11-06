"""Tests for Bug #18: KokoroTTSEngine.synthesize() dynamic language tag selection.

Verifies:
1. British English voices (bf_emma, bm_george) select lang="en-gb".
2. American English voices (af_bella, af_heart, am_adam, am_michael) select lang="en-us".
3. International voices select appropriate language codes (ja, zh, es, fr, hi, it, pt-br).
4. Explicit lang override via kwargs takes precedence.
5. Setting active_voice_name to a British voice propagates lang="en-gb" during default synthesis.
"""

from unittest.mock import MagicMock
import numpy as np
import pytest

from app.voice.kokoro_engine import KokoroTTSEngine


@pytest.fixture
def mock_kokoro_engine():
    """Create a KokoroTTSEngine with a mocked _kokoro session."""
    engine = KokoroTTSEngine(default_voice="af_bella")
    mock_session = MagicMock()
    # Mock create() to return dummy audio samples and sample rate
    mock_session.create.return_value = (np.zeros(2400, dtype=np.float32), 24000)
    mock_session.get_voices.return_value = [
        "af_bella",
        "af_heart",
        "am_adam",
        "bf_emma",
        "bm_george",
        "jf_teio",
        "zf_xiaobei",
        "ef_dora",
        "ff_siwis",
        "hf_alpha",
    ]
    engine._kokoro = mock_session
    engine._is_loaded = True
    return engine, mock_session


def test_kokoro_british_voices_select_en_gb(mock_kokoro_engine):
    """Verify British female and male voices use lang='en-gb'."""
    engine, mock_session = mock_kokoro_engine

    # 1. British female (bf_emma)
    engine.synthesize("Good afternoon, sir.", voice="bf_emma")
    assert mock_session.create.call_args[1]["lang"] == "en-gb"
    assert mock_session.create.call_args[1]["voice"] == "bf_emma"

    # 2. British male (bm_george)
    mock_session.create.reset_mock()
    engine.synthesize("Indeed, quite right.", voice="bm_george")
    assert mock_session.create.call_args[1]["lang"] == "en-gb"
    assert mock_session.create.call_args[1]["voice"] == "bm_george"


def test_kokoro_american_voices_select_en_us(mock_kokoro_engine):
    """Verify American female and male voices use lang='en-us'."""
    engine, mock_session = mock_kokoro_engine

    # 1. American female (af_bella)
    engine.synthesize("Hey buddy, what's up?", voice="af_bella")
    assert mock_session.create.call_args[1]["lang"] == "en-us"
    assert mock_session.create.call_args[1]["voice"] == "af_bella"

    # 2. American male (am_adam)
    mock_session.create.reset_mock()
    engine.synthesize("Let's get going.", voice="am_adam")
    assert mock_session.create.call_args[1]["lang"] == "en-us"
    assert mock_session.create.call_args[1]["voice"] == "am_adam"


def test_kokoro_international_voices_select_proper_lang(mock_kokoro_engine):
    """Verify international voices resolve to their correct language tags."""
    engine, mock_session = mock_kokoro_engine

    test_cases = [
        ("jf_teio", "ja"),
        ("zf_xiaobei", "zh"),
        ("ef_dora", "es"),
        ("ff_siwis", "fr"),
        ("hf_alpha", "hi"),
    ]

    for voice, expected_lang in test_cases:
        mock_session.create.reset_mock()
        engine.synthesize("Testing international voice", voice=voice)
        assert mock_session.create.call_args[1]["lang"] == expected_lang
        assert mock_session.create.call_args[1]["voice"] == voice


def test_kokoro_explicit_lang_kwargs_override(mock_kokoro_engine):
    """Verify kwargs['lang'] overrides the voice prefix detection."""
    engine, mock_session = mock_kokoro_engine

    # Explicit override on an American voice to use en-gb
    engine.synthesize("Pip pip cheerio", voice="af_bella", lang="en-gb")
    assert mock_session.create.call_args[1]["lang"] == "en-gb"
    assert mock_session.create.call_args[1]["voice"] == "af_bella"


def test_kokoro_active_voice_name_british_default(mock_kokoro_engine):
    """Verify active_voice_name set to British voice defaults to en-gb without kwargs."""
    engine, mock_session = mock_kokoro_engine
    engine.active_voice_name = "bf_emma"

    engine.synthesize("Hello from London.")
    assert mock_session.create.call_args[1]["lang"] == "en-gb"
    assert mock_session.create.call_args[1]["voice"] == "bf_emma"
