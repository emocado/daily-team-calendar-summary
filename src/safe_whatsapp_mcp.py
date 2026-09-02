#!/usr/bin/env python3
"""Minimal, destination-locked WhatsApp MCP facade.

It deliberately exposes no inbox-reading or arbitrary-recipient tools. The
underlying bridge is the pinned verygoodplugins/whatsapp-mcp release.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from typing import Any
from urllib import error, request
from zoneinfo import ZoneInfo


PROTOCOL_VERSION = "2025-06-18"
SERVER_VERSION = "1.0.0"


class WorkflowError(RuntimeError):
    pass


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


class SafeWhatsappService:
    def __init__(self, config_path: Path, state_path: Path | None = None):
        self.config_path = config_path.resolve()
        self.root = self.config_path.parent.parent
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.wa = self.config["whatsapp"]
        self.timezone = ZoneInfo(self.config.get("timezone", "Asia/Singapore"))
        self.db_path = _resolve_path(self.root, self.wa["database_path"])
        self.token_path = _resolve_path(self.root, self.wa["bridge_token_path"])
        self.state_path = (state_path or self.root / "runtime" / "delivery-state.sqlite3").resolve()

    def _matching_groups(self) -> list[dict[str, str]]:
        if not self.db_path.exists():
            raise WorkflowError("WhatsApp message database is unavailable; pair the bridge first")
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT jid, name FROM chats WHERE name = ? AND jid LIKE '%@g.us' ORDER BY jid",
                (self.wa["group_name"],),
            ).fetchall()
        return [{"jid": jid, "name": name} for jid, name in rows]

    def resolve_group(self) -> str:
        groups = self._matching_groups()
        if len(groups) != 1:
            raise WorkflowError(
                f"Expected exactly one group named {self.wa['group_name']!r}; found {len(groups)}"
            )
        return groups[0]["jid"]

    def pin_group(self) -> str:
        jid = self.resolve_group()
        self.config["whatsapp"]["group_jid"] = jid
        self.config_path.write_text(json.dumps(self.config, indent=2) + "\n", encoding="utf-8")
        self.wa = self.config["whatsapp"]
        return jid

    def status(self) -> dict[str, Any]:
        pinned = self.wa.get("group_jid", "")
        try:
            resolved = self.resolve_group()
            group_ok = pinned == resolved
            group_error = None
        except WorkflowError as exc:
            resolved = None
            group_ok = False
            group_error = str(exc)
        return {
            "group_name": self.wa["group_name"],
            "pinned_group_jid": pinned,
            "resolved_group_jid": resolved,
            "group_verified": group_ok,
            "bridge_token_present": self.token_path.exists(),
            "database_present": self.db_path.exists(),
            "error": group_error,
        }

    def _verify_destination(self) -> str:
        pinned = self.wa.get("group_jid", "")
        if not pinned or pinned == "PIN_AFTER_QR_PAIRING" or not pinned.endswith("@g.us"):
            raise WorkflowError("WhatsApp group JID has not been pinned")
        resolved = self.resolve_group()
        if resolved != pinned:
            raise WorkflowError("Pinned WhatsApp group no longer matches the configured group name")
        return pinned

    def _start_bridge(self) -> None:
        command = self.wa.get("auto_start_command") or []
        if not command:
            return
        log_path = self.root / "runtime" / "whatsapp-bridge.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with log_path.open("ab") as log:
            subprocess.Popen(command, stdout=log, stderr=log, creationflags=flags)

    def _bridge_request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token_path.exists():
            raise WorkflowError("WhatsApp bridge token is unavailable; pair the bridge first")
        token = self.token_path.read_text(encoding="utf-8").strip()
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.wa["bridge_url"].rstrip("/") + path,
            data=body,
            method="GET" if payload is None else "POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError) as exc:
            raise WorkflowError(f"WhatsApp bridge request failed: {exc}") from exc

    def _ensure_bridge(self) -> None:
        try:
            self._bridge_request("/health")
            return
        except WorkflowError:
            self._start_bridge()
        for _ in range(20):
            time.sleep(0.5)
            try:
                self._bridge_request("/health")
                return
            except WorkflowError:
                continue
        raise WorkflowError("WhatsApp bridge did not become ready")

    def send_daily_summary(self, run_date: str, message: str) -> dict[str, Any]:
        try:
            parsed_date = dt.date.fromisoformat(run_date)
        except ValueError as exc:
            raise WorkflowError("run_date must use YYYY-MM-DD") from exc
        if parsed_date != dt.datetime.now(self.timezone).date():
            raise WorkflowError("run_date must equal today's date in the configured timezone")
        if not message.strip() or len(message) > 5000:
            raise WorkflowError("message must contain 1 to 5000 characters")

        destination = self._verify_destination()
        digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.state_path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS deliveries ("
                "run_date TEXT NOT NULL, destination TEXT NOT NULL, message_hash TEXT NOT NULL, "
                "sent_at TEXT NOT NULL, PRIMARY KEY (run_date, destination))"
            )
            conn.commit()
            prior = conn.execute(
                "SELECT message_hash, sent_at FROM deliveries WHERE run_date = ? AND destination = ?",
                (run_date, destination),
            ).fetchone()
            if prior:
                if prior[0] == digest:
                    return {"status": "already_sent", "sent_at": prior[1], "message_hash": digest}
                raise WorkflowError("A different summary was already sent to this group for this date")

        self._ensure_bridge()
        result = self._bridge_request("/send", {"recipient": destination, "message": message})
        if not result.get("success"):
            raise WorkflowError(f"WhatsApp did not confirm delivery: {result.get('message', 'unknown error')}")
        sent_at = dt.datetime.now(dt.timezone.utc).isoformat()
        with closing(sqlite3.connect(self.state_path)) as conn:
            conn.execute(
                "INSERT INTO deliveries(run_date, destination, message_hash, sent_at) VALUES (?, ?, ?, ?)",
                (run_date, destination, digest, sent_at),
            )
            conn.commit()
        return {"status": "sent", "sent_at": sent_at, "message_hash": digest}


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}
    if is_error:
        result["isError"] = True
    return result


def _handle(service: SafeWhatsappService, message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        version = message.get("params", {}).get("protocolVersion", PROTOCOL_VERSION)
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "safe-whatsapp-summary", "version": SERVER_VERSION},
            "instructions": "Only sends a daily summary to one pre-pinned WhatsApp group. It cannot read chats or choose recipients.",
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [
            {
                "name": "whatsapp_status",
                "description": "Verify the paired bridge and pinned test-group destination without sending.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                "annotations": {"readOnlyHint": True},
            },
            {
                "name": "send_daily_summary",
                "description": "Send today's already-formatted calendar summary exactly once to the pinned test group.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "run_date": {"type": "string", "description": "Asia/Singapore date in YYYY-MM-DD"},
                        "message": {"type": "string", "minLength": 1, "maxLength": 5000},
                    },
                    "required": ["run_date", "message"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
            },
        ]}
    elif method == "tools/call":
        params = message.get("params", {})
        try:
            if params.get("name") == "whatsapp_status":
                result = _tool_result(service.status())
            elif params.get("name") == "send_daily_summary":
                args = params.get("arguments", {})
                result = _tool_result(service.send_daily_summary(args["run_date"], args["message"]))
            else:
                raise WorkflowError("Unknown tool")
        except (WorkflowError, KeyError) as exc:
            result = _tool_result({"error": str(exc)}, is_error=True)
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(config_path: Path) -> None:
    service = SafeWhatsappService(config_path)
    for line in sys.stdin:
        try:
            response = _handle(service, json.loads(line))
            if response is not None:
                print(json.dumps(response, separators=(",", ":")), flush=True)
        except Exception as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--resolve-group", action="store_true")
    parser.add_argument("--pin", action="store_true")
    args = parser.parse_args()
    if args.resolve_group:
        service = SafeWhatsappService(args.config)
        jid = service.pin_group() if args.pin else service.resolve_group()
        print(jid)
    else:
        serve(args.config)


if __name__ == "__main__":
    main()
