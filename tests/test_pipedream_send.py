import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock
import urllib.error

PIPEDREAM_DIR = Path(__file__).resolve().parent.parent / "pipedream"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PIPEDREAM_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PipedreamSendRetryTests(unittest.TestCase):
    def _ok_response(self):
        response = mock.MagicMock()
        response.read.return_value = json.dumps({"idMessage": "ABC"}).encode("utf-8")
        response.__enter__.return_value = response
        return response

    def test_retries_network_error_with_short_timeout(self):
        for name in ("format_and_send", "all_in_one_workflow"):
            with self.subTest(module=name):
                module = _load(name)
                with mock.patch.object(module.request, "urlopen") as mock_urlopen, mock.patch.object(
                    module.time, "sleep"
                ) as mock_sleep:
                    mock_urlopen.side_effect = [
                        urllib.error.URLError("[Errno 110] Connection timed out"),
                        self._ok_response(),
                    ]
                    result = module.send_to_green_api("123@g.us", "hello")

                self.assertEqual("ABC", result["idMessage"])
                self.assertEqual(2, mock_urlopen.call_count)
                self.assertEqual(5.0, mock_urlopen.call_args.kwargs["timeout"])
                mock_sleep.assert_called_once()

    def test_worst_case_fits_pipedream_30s_limit(self):
        for name in ("format_and_send", "all_in_one_workflow"):
            with self.subTest(module=name):
                module = _load(name)
                with mock.patch.object(module.request, "urlopen") as mock_urlopen, mock.patch.object(
                    module.time, "sleep"
                ) as mock_sleep:
                    mock_urlopen.side_effect = urllib.error.URLError("timed out")
                    with self.assertRaises(RuntimeError):
                        module.send_to_green_api("123@g.us", "hello")

                timeouts = sum(call.kwargs["timeout"] for call in mock_urlopen.call_args_list)
                sleeps = sum(call.args[0] for call in mock_sleep.call_args_list)
                self.assertEqual(3, mock_urlopen.call_count)
                self.assertLess(timeouts + sleeps, 20)

    def test_does_not_retry_client_error(self):
        module = _load("format_and_send")
        http_error = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        http_error.read = lambda: b"bad token"
        with mock.patch.object(module.request, "urlopen", side_effect=http_error) as mock_urlopen, mock.patch.object(
            module.time, "sleep"
        ) as mock_sleep:
            with self.assertRaises(RuntimeError):
                module.send_to_green_api("123@g.us", "hello")
        self.assertEqual(1, mock_urlopen.call_count)
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
