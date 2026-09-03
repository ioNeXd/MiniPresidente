from __future__ import annotations

import logging
import queue
import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from app.capture import grab_rgb
from app.config import MAX_CLIENT_QUEUE, MAX_FRAME_BYTES
from app.session_config import SessionConfig
from app.video_codec import H264Encoder, VideoCodecConfig

logger = logging.getLogger(__name__)

HANDSHAKE_MAGIC = b"MPH264"
HANDSHAKE_FORMAT = ">6sIII"
HANDSHAKE_SIZE = struct.calcsize(HANDSHAKE_FORMAT)
Packet = bytes | None
CaptureFn = Callable[[int, int], tuple[bytes, int, int]]


def _frame_packet(data: bytes) -> bytes:
    if not 0 < len(data) <= MAX_FRAME_BYTES:
        raise ValueError("Encoded packet size is out of bounds")
    return struct.pack(">I", len(data)) + data


def make_handshake(width: int, height: int, fps: int) -> bytes:
    return struct.pack(HANDSHAKE_FORMAT, HANDSHAKE_MAGIC, width, height, fps)


@dataclass
class _Client:
    conn: socket.socket
    packets: queue.Queue[Packet]
    thread: threading.Thread | None = None


class StreamServer:
    def __init__(self, session_config: SessionConfig,
                 capture_fn: CaptureFn = grab_rgb):
        self.monitor_index = session_config.monitor_index
        self.fps = session_config.video_fps
        self.max_width = session_config.max_width
        self.bitrate_kbps = session_config.video_bitrate_kbps
        self._capture_fn = capture_fn
        self._sock: Optional[socket.socket] = None
        self._running = False
        self.port = 0
        self._clients: list[_Client] = []
        self._clients_lock = threading.Lock()
        self._capture_thread: Optional[threading.Thread] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._stream_ready = threading.Event()
        self._handshake: bytes | None = None

    def start(self) -> int:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._capture_thread.start()
        self._accept_thread.start()
        logger.info("StreamServer started on port %d", self.port)
        return self.port

    def stop(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        capture_thread = self._capture_thread
        if capture_thread is not None:
            capture_thread.join(timeout=2.0)
        try:
            if self._stream_ready.is_set() and hasattr(self, "_encoder"):
                for packet in self._encoder.flush():
                    self._broadcast(packet)
        finally:
            with self._clients_lock:
                clients = list(self._clients)
            for client in clients:
                client.packets.put(None)
            for client in clients:
                if client.thread is not None:
                    client.thread.join(timeout=2.0)
            accept_thread = self._accept_thread
            if accept_thread is not None:
                accept_thread.join(timeout=2.0)
            logger.info("StreamServer stopped")

    def _capture_loop(self) -> None:
        interval = 1.0 / max(1, self.fps)
        while self._running:
            started = time.monotonic()
            try:
                rgb, width, height = self._capture_fn(self.monitor_index, self.max_width)
                if not self._stream_ready.is_set():
                    self._encoder = H264Encoder(VideoCodecConfig(
                        width, height, self.fps, self.bitrate_kbps))
                    self._handshake = _frame_packet(make_handshake(width, height, self.fps))
                    self._stream_ready.set()
                packets = self._encoder.encode_frame(rgb, width, height)
                for packet in packets:
                    self._broadcast(packet)
            except Exception:
                logger.exception("Error capturing or encoding frame")
            elapsed = time.monotonic() - started
            if elapsed < interval:
                time.sleep(interval - elapsed)

    def _broadcast(self, packet: bytes) -> None:
        if len(packet) > MAX_FRAME_BYTES:
            logger.warning("Encoded packet exceeds allowed max, skipping")
            return
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            framed = _frame_packet(packet)
            try:
                client.packets.put_nowait(framed)
            except queue.Full:
                try:
                    client.packets.get_nowait()
                except queue.Empty:
                    pass
                try:
                    client.packets.put_nowait(framed)
                except queue.Full:
                    pass

    def _accept_loop(self) -> None:
        while self._running:
            sock = self._sock
            if sock is None:
                break
            try:
                conn, _addr = sock.accept()
            except OSError:
                break
            client = _Client(conn, queue.Queue(maxsize=MAX_CLIENT_QUEUE))
            with self._clients_lock:
                self._clients.append(client)
            if self._stream_ready.is_set() and hasattr(self, "_encoder"):
                self._encoder.request_keyframe()
            client.thread = threading.Thread(target=self._serve_client, args=(client,), daemon=True)
            client.thread.start()

    def _serve_client(self, client: _Client) -> None:
        try:
            if not self._stream_ready.wait(timeout=5.0) or self._handshake is None:
                return
            client.conn.sendall(self._handshake)
            while self._running or not client.packets.empty():
                packet = client.packets.get()
                if packet is None:
                    break
                client.conn.sendall(packet)
        except OSError:
            logger.info("Viewer disconnected")
        finally:
            with self._clients_lock:
                if client in self._clients:
                    self._clients.remove(client)
            try:
                client.conn.close()
            except OSError:
                pass
