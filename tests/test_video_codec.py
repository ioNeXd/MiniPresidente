from __future__ import annotations

import av
from PIL import Image

from app.video_codec import H264Decoder, H264Encoder, VideoCodecConfig


def test_h264_round_trip_and_bitrate():
    width, height, fps = 320, 240, 10
    frame_count = 20
    config = VideoCodecConfig(width, height, fps, bitrate_kbps=200)
    encoder = H264Encoder(config)
    packets: list[bytes] = []
    for index in range(frame_count):
        pixels = bytes((position + index * 17) % 256 for position in range(width * height * 3))
        image = Image.frombytes("RGB", (width, height), pixels)
        packets.extend(encoder.encode_frame(image.tobytes(), width, height))
    packets.extend(encoder.flush())

    decoder = H264Decoder()
    decoded = [frame for packet in packets for frame in decoder.decode_packet(packet)]
    assert decoded
    assert len(decoded[0]) == width * height * 3
    duration_s = frame_count / fps
    bitrate = sum(map(len, packets)) * 8 / duration_s / 1000
    assert config.bitrate_kbps * 0.5 <= bitrate <= config.bitrate_kbps * 2.0


def test_h264_flush_without_frames():
    config = VideoCodecConfig(64, 48, 10, 200)
    assert H264Encoder(config).flush() == []


def test_h264_encoder_requests_keyframe_on_next_frame():
    encoder = H264Encoder(VideoCodecConfig(64, 48, 10, 200))
    encoded_frames = []

    class RecordingCodec:
        def encode(self, frame):
            encoded_frames.append(frame)
            return []

    encoder._codec = RecordingCodec()
    rgb = bytes(64 * 48 * 3)
    encoder.request_keyframe()
    encoder.encode_frame(rgb, 64, 48)
    encoder.encode_frame(rgb, 64, 48)

    assert encoded_frames[0].pict_type == av.video.frame.PictureType.I
    assert encoded_frames[1].pict_type != av.video.frame.PictureType.I
