"""Minimal MLLP client for testing HL7 message delivery."""

import socket
import sys
from pathlib import Path

VT = b"\x0b"
FS = b"\x1c"
CR = b"\x0d"


def send(host: str, port: int, hl7_path: str) -> str:
    msg = Path(hl7_path).read_bytes().replace(b"\n", b"\r")
    frame = VT + msg + FS + CR
    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(frame)
        buf = b""
        while not buf.endswith(FS + CR):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    return buf.strip(VT + FS + CR).decode("latin-1")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <hl7_file> [host] [port]")
        sys.exit(1)

    hl7_file = sys.argv[1]
    host = sys.argv[2] if len(sys.argv) > 2 else "localhost"
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 6661

    print(f"Sending {hl7_file} to {host}:{port}...")
    response = send(host, port, hl7_file)
    print(f"Response:\n{response}")
