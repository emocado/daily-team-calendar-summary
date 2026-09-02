import datetime as dt
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from zoneinfo import ZoneInfo

from src.safe_whatsapp_mcp import SafeWhatsappService, WorkflowError, _handle


class SafeWhatsappMcpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "runtime").mkdir()
        db = self.root / "messages.db"
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("CREATE TABLE chats (jid TEXT, name TEXT)")
            conn.execute("INSERT INTO chats VALUES (?, ?)", ("12345@g.us", "Me, Myself and I"))
            conn.commit()
        (self.root / "token").write_text("secret", encoding="utf-8")
        config = {
            "timezone": "Asia/Singapore",
            "whatsapp": {
                "group_name": "Me, Myself and I",
                "group_jid": "12345@g.us",
                "bridge_url": "http://127.0.0.1:8080/api",
                "database_path": str(db),
                "bridge_token_path": str(self.root / "token"),
                "auto_start_command": [],
            },
        }
        self.config_path = self.root / "config" / "workflow.json"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        self.service = SafeWhatsappService(self.config_path, self.root / "runtime" / "state.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_status_verifies_exact_pinned_group(self):
        self.assertTrue(self.service.status()["group_verified"])

    def test_mismatched_group_fails_closed(self):
        self.service.wa["group_jid"] = "other@g.us"
        with self.assertRaisesRegex(WorkflowError, "no longer matches"):
            self.service._verify_destination()

    def test_send_is_idempotent_for_same_day(self):
        today = dt.datetime.now(ZoneInfo("Asia/Singapore")).date().isoformat()
        with mock.patch.object(self.service, "_ensure_bridge"), mock.patch.object(
            self.service, "_bridge_request", return_value={"success": True, "message": "sent"}
        ) as bridge:
            first = self.service.send_daily_summary(today, "hello")
            second = self.service.send_daily_summary(today, "hello")
        self.assertEqual("sent", first["status"])
        self.assertEqual("already_sent", second["status"])
        bridge.assert_called_once()

    def test_different_second_message_is_refused(self):
        today = dt.datetime.now(ZoneInfo("Asia/Singapore")).date().isoformat()
        with mock.patch.object(self.service, "_ensure_bridge"), mock.patch.object(
            self.service, "_bridge_request", return_value={"success": True}
        ):
            self.service.send_daily_summary(today, "first")
            with self.assertRaisesRegex(WorkflowError, "different summary"):
                self.service.send_daily_summary(today, "second")

    def test_mcp_exposes_no_arbitrary_recipient_parameter(self):
        response = _handle(self.service, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        send_tool = next(t for t in response["result"]["tools"] if t["name"] == "send_daily_summary")
        self.assertNotIn("recipient", send_tool["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
