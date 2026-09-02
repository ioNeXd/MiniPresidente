import pytest

from app.session_config import (
    AUDIO_BITRATE_OPTIONS,
    GLOBAL_VIDEO_BITRATE_MAX,
    RESOLUTION_PRESETS,
    VIDEO_FPS_OPTIONS,
    SessionConfig,
    nearest_resolution_bucket,
)


def test_resolution_presets_match_documented_table():
    assert RESOLUTION_PRESETS == {
        "360p": {"width": 640, "height": 360, "fps": 30, "bitrate": 400, "min": 200, "max": 800},
        "480p": {"width": 854, "height": 480, "fps": 30, "bitrate": 800, "min": 400, "max": 1500},
        "720p": {"width": 1280, "height": 720, "fps": 30, "bitrate": 2500, "min": 1000, "max": 6000},
        "1080p": {"width": 1920, "height": 1080, "fps": 30, "bitrate": 5000, "min": 2500, "max": 12000},
        "1440p": {"width": 2560, "height": 1440, "fps": 30, "bitrate": 8000, "min": 4000, "max": 20000},
    }
    assert GLOBAL_VIDEO_BITRATE_MAX == 20000


def test_nearest_bucket_uses_total_pixels():
    assert nearest_resolution_bucket(3440, 1440) == "1440p"


def test_session_config_rejects_invalid_quality_values():
    with pytest.raises(ValueError, match="video_fps"):
        SessionConfig("", "", "", video_fps=29)
    with pytest.raises(ValueError, match="video_bitrate_kbps"):
        SessionConfig("", "", "", resolution="1440p", video_bitrate_kbps=25000)
    with pytest.raises(ValueError, match="video_bitrate_kbps"):
        SessionConfig("", "", "", resolution="720p", video_bitrate_kbps=999)
    with pytest.raises(ValueError, match="audio_bitrate_kbps"):
        SessionConfig("", "", "", audio_bitrate_kbps=100)


def test_quality_option_lists_are_closed():
    assert VIDEO_FPS_OPTIONS == (5, 15, 30, 60, 120)
    assert AUDIO_BITRATE_OPTIONS == (64, 96, 128, 192, 256, 320)
