"""Run the WSL bridge and keep a scannable QR PNG up to date."""

from __future__ import annotations

import os
import re
from pathlib import Path
import subprocess
import sys

import qrcode

# Ensure stdout and stderr handle utf-8 safely
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
QR_PATH = ROOT / "runtime" / "whatsapp-pairing.png"
PAYLOAD_PATH = ROOT / "runtime" / "whatsapp-qr-payload.txt"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

COMMAND = [
    "wsl.exe",
    "-d",
    "Ubuntu",
    "--",
    "bash",
    "-lc",
    "cd /mnt/c/Users/weikh/projects/daily-team-calendar-summary/integrations/whatsapp-mcp/whatsapp-bridge "
    "&& exec env WEBHOOK_ENABLED=false FORWARD_SELF=false WHATSAPP_DEVICE_NAME=SW-Calendar-Summary "
    "../bin/whatsapp-bridge-ubuntu",
]


def main() -> int:
    QR_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("[*] Starting WhatsApp bridge process in WSL...")
    process = subprocess.Popen(
        COMMAND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    try:
        for raw_line in process.stdout:
            line = ANSI.sub("", raw_line).rstrip()
            marker = "Emitting QR code "
            if marker in line:
                payload = line.split(marker, 1)[1].strip()
                PAYLOAD_PATH.write_text(payload, encoding="utf-8")
                img = qrcode.make(payload)
                img.save(QR_PATH)
                print(f"\n[+] PAIRING_QR_READY={QR_PATH}")
                print(f"[+] QR code payload saved to {PAYLOAD_PATH}")
                print("[*] Please scan the QR code using WhatsApp on your phone (Linked Devices -> Link a Device).\n", flush=True)
            elif "Successfully paired" in line or "Client connected" in line or "Pairing successful" in line or "logged in" in line.lower():
                print(f"[+] WhatsApp Pairing Status: {line}", flush=True)
            else:
                # Print status line safely
                try:
                    print(f"  {line}", flush=True)
                except Exception:
                    pass
    except KeyboardInterrupt:
        print("\n[*] Stopping bridge...")
        process.terminate()
    return process.wait()


if __name__ == "__main__":
    sys.exit(main())
