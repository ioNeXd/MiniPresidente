from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from threading import Event

import av


@dataclass(frozen=True)
class VideoCodecConfig:
    width: int
    height: int
    fps: int
    bitrate_kbps: int
    keyframe_interval_s: float = 2.0


def _packed_rgb_frame(data: bytes, width: int, height: int) -> av.VideoFrame:
    frame = av.VideoFrame(width, height, "rgb24")
    plane = frame.planes[0]
    row_size = width * 3
    padded = bytearray(plane.line_size * height)
    for row in range(height):
        start = row * row_size
        padded[row * plane.line_size:row * plane.line_size + row_size] = data[start:start + row_size]
    plane.update(bytes(padded))
    return frame


def _packed_rgb_bytes(frame: av.VideoFrame) -> bytes:
    rgb = frame.reformat(format="rgb24")
    plane = rgb.planes[0]
    row_size = rgb.width * 3
    raw = bytes(plane)
    return b"".join(raw[row * plane.line_size:row * plane.line_size + row_size]
                    for row in range(rgb.height))


class H264Encoder:
    """Codifica frames RGB crus em pacotes H.264 independentes."""

    def __init__(self, config: VideoCodecConfig):
        self.config = config
        self._codec = av.CodecContext.create("libx264", "w")
        self._codec.width = config.width
        self._codec.height = config.height
        self._codec.pix_fmt = "yuv420p"
        self._codec.framerate = Fraction(config.fps, 1)
        self._codec.time_base = Fraction(1, config.fps)
        self._codec.bit_rate = config.bitrate_kbps * 1000
        self._codec.bit_rate_tolerance = config.bitrate_kbps * 1000
        self._codec.options = {"preset": "veryfast", "tune": "zerolatency"}
        self._codec.gop_size = max(1, round(config.fps * config.keyframe_interval_s))
        self._next_pts = 0
        self._keyframe_requested = Event()

    def request_keyframe(self) -> None:
        """Force the next encoded frame to be an I-frame."""
        self._keyframe_requested.set()

    def encode_frame(self, rgb_frame: bytes, width: int, height: int) -> list[bytes]:
        if (width, height) != (self.config.width, self.config.height):
            raise ValueError("Frame dimensions do not match codec configuration")
        if len(rgb_frame) != width * height * 3:
            raise ValueError("RGB frame has an invalid size")
        frame = _packed_rgb_frame(rgb_frame, width, height)
        frame.pts = self._next_pts
        self._next_pts += 1
        if self._keyframe_requested.is_set():
            frame.pict_type = av.video.frame.PictureType.I
            self._keyframe_requested.clear()
        return [bytes(packet) for packet in self._codec.encode(frame)]

    def flush(self) -> list[bytes]:
        return [bytes(packet) for packet in self._codec.encode(None)]


class H264Decoder:
    """Decodifica pacotes H.264 em frames RGB crus (width * height * 3 bytes)."""

    def __init__(self):
        self._codec = av.CodecContext.create("h264", "r")

    def decode_packet(self, data: bytes) -> list[bytes]:
        if not data:
            raise ValueError("Encoded packet cannot be empty")
        return [_packed_rgb_bytes(frame) for frame in self._codec.decode(av.Packet(data))]
