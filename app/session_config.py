from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DEFAULT_FPS, DEFAULT_JPEG_QUALITY, DEFAULT_MAX_WIDTH


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
