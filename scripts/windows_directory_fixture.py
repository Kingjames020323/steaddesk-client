"""Synthetic, loopback-only directory presence for the Windows Actions UI drill."""
import ipaddress
import json
import os
import socket
import socketserver
import threading
from pathlib import Path

ONLINE = b"987654321"
OFFLINE = b"987654322"


def reply(packet):
    # Pinned rendezvous.proto OnlineRequest (field 23), repeated peers (field 2).
    # Ignore every other envelope and every inventory except our disposable pair.
    if not packet.startswith(b"\xba\x01") or packet[2:3] != bytes([len(packet) - 3]):
        return None
    peers = []
    data = packet[3:]
    while data:
        if len(data) < 2 or data[0] not in (10, 18) or data[1] > len(data) - 2:
            return None
        field, size = data[:2]
        if field == 18:
            peers.append(data[2:2 + size])
        data = data[2 + size:]
    if set(peers) != {ONLINE, OFFLINE} or len(peers) != 2:
        return None
    bits = 0x80 >> peers.index(ONLINE)
    # BytesCodec length prefix, OnlineResponse (field 24), one-byte state mask.
    return bytes([6 << 2, 0xc2, 1, 3, 10, 1, bits])


class _Presence(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        first = self.rfile.read(1)
        if not first or first[0] & 3:
            return
        result = reply(self.rfile.read(first[0] >> 2))
        if result:
            self.wfile.write(result)


def seed(account, product):
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("STEADDESK_EDITION") != "support":
        raise RuntimeError("Directory fixture requires the isolated Actions support job")
    for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        assert ipaddress.ip_address(address).is_loopback
        class Server(socketserver.ThreadingTCPServer):
            address_family = family
            daemon_threads = True
        server = Server((address, 21115), _Presence)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    # Runner.rc VERSIONINFO, sanitized by path_provider_windows 2.2.1.
    group_file = Path(os.environ["APPDATA"]) / "Purslane Tech Pte. Ltd" / product / "support-groups-v1.json"
    group_file.parent.mkdir(parents=True, exist_ok=True)
    with group_file.open("x", encoding="utf-8") as f:
        json.dump({"version": 2, "accounts": {account: [{
            "id": "00000000-0000-4000-8000-000000000001", "name": "Display fixture",
            "device_ids": [ONLINE.decode(), OFFLINE.decode()], "updated_at": "2026-01-01T00:00:00Z"
        }]}}, f)
