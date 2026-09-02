from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DEFAULT_FPS, DEFAULT_JPEG_QUALITY, DEFAULT_MAX_WIDTH

VIDEO_FPS_OPTIONS = (5, 15, 30, 60, 120)
AUDIO_BITRATE_OPTIONS = (64, 96, 128, 192, 256, 320)
GLOBAL_VIDEO_BITRATE_MAX = 20000

RESOLUTION_PRESETS = {
    "360p": {"width": 640, "height": 360, "fps": 30, "bitrate": 400, "min": 200, "max": 800},
    "480p": {"width": 854, "height": 480, "fps": 30, "bitrate": 800, "min": 400, "max": 1500},
    "720p": {"width": 1280, "height": 720, "fps": 30, "bitrate": 2500, "min": 1000, "max": 6000},
    "1080p": {"width": 1920, "height": 1080, "fps": 30, "bitrate": 5000, "min": 2500, "max": 12000},
    "1440p": {"width": 2560, "height": 1440, "fps": 30, "bitrate": 8000, "min": 4000, "max": 20000},
}


def nearest_resolution_bucket(width: int, height: int) -> str:
    pixels = width * height
    return min(
        RESOLUTION_PRESETS,
        key=lambda name: abs(pixels - RESOLUTION_PRESETS[name]["width"] * RESOLUTION_PRESETS[name]["height"]),
    )


def resolution_limits(resolution: str, native_size: tuple[int, int] | None = None) -> dict:
    if resolution == "origem":
        if native_size is None:
            raise ValueError("native_size is required for origem resolution")
        return RESOLUTION_PRESETS[nearest_resolution_bucket(*native_size)]
    try:
        return RESOLUTION_PRESETS[resolution]
    except KeyError as exc:
        raise ValueError(f"Unknown resolution: {resolution}") from exc


@dataclass
class SessionConfig:
    username: str
    room_name: str
    room_id: str
    manual_advertise_ip: str = ""
    seed_peers: list[str] = field(default_factory=list)
    fps: int = DEFAULT_FPS
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    max_width: int = DEFAULT_MAX_WIDTH
    monitor_index: int = 1
    native_size: tuple[int, int] | None = None
    video_bitrate_kbps: int = 5000
    resolution: str = "1080p"
    video_fps: int = 30
    audio_bitrate_kbps: int = 128

    def __post_init__(self) -> None:
        self.validate(self.native_size)

    def validate(self, native_size: tuple[int, int] | None = None) -> None:
        if self.fps not in VIDEO_FPS_OPTIONS:
            raise ValueError(f"fps must be one of {VIDEO_FPS_OPTIONS}")
        if self.video_fps not in VIDEO_FPS_OPTIONS:
            raise ValueError(f"video_fps must be one of {VIDEO_FPS_OPTIONS}")
        effective_native_size = native_size if native_size is not None else self.native_size
        limits = resolution_limits(self.resolution, effective_native_size)
        maximum = min(limits["max"], GLOBAL_VIDEO_BITRATE_MAX)
        if not limits["min"] <= self.video_bitrate_kbps <= maximum:
            raise ValueError(
                f"video_bitrate_kbps must be between {limits['min']} and {maximum} for {self.resolution}")
        if self.audio_bitrate_kbps not in AUDIO_BITRATE_OPTIONS:
            raise ValueError(f"audio_bitrate_kbps must be one of {AUDIO_BITRATE_OPTIONS}")
