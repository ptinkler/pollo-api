"""Tests for img2vid.common.get_task — task status polling."""
import pytest
from unittest.mock import patch, MagicMock

from img2vid.common.get_task import get_task_status, get_credit_balance


class TestGetTaskStatus:
    def test_success_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "generations": [
                    {"status": "succeed", "failMsg": None, "url": "https://video.com/out.mp4"}
                ]
            }
        }
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            results = get_task_status("task123", "api-key-123")
        assert len(results) == 1
        assert results[0] == ("succeed", None, "https://video.com/out.mp4", None)

    def test_success_with_credit(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "credit": 21,
                "generations": [
                    {"status": "succeed", "failMsg": None, "url": "https://video.com/out.mp4", "credit": "21"}
                ]
            }
        }
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            results = get_task_status("task123", "api-key-123")
        assert results[0][3] == 21

    def test_success_with_top_level_credit_only(self):
        """When per-generation credit is missing, top-level credit is used."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "credit": 15,
                "generations": [
                    {"status": "succeed", "failMsg": None, "url": "https://video.com/out.mp4"}
                ]
            }
        }
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            results = get_task_status("task123", "api-key-123")
        assert results[0][3] == 15

    def test_result_key_with_videoUrl(self):
        """API response with 'result' key and 'videoUrl' field."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "credit": 21,
                "result": [
                    {"status": "succeed", "failMsg": None, "videoUrl": "https://cdn.pollo.ai/video.mp4", "credit": "21"}
                ]
            }
        }
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            results = get_task_status("task123", "api-key-123")
        assert results[0] == ("succeed", None, "https://cdn.pollo.ai/video.mp4", 21)

    def test_error_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "generations": [
                    {"status": "error", "failMsg": "Something broke", "url": None}
                ]
            }
        }
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            results = get_task_status("task123", "api-key-123")
        assert results[0][0] == "error"
        assert results[0][1] == "Something broke"

    def test_processing_status(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "generations": [
                    {"status": "processing", "failMsg": None, "url": None}
                ]
            }
        }
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            results = get_task_status("task123", "api-key-123")
        assert results[0] == ("processing", None, None, None)

    def test_no_generations(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"generations": []}}
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            results = get_task_status("task123", "api-key-123")
        assert results == [("error", "No generations found.", None, None)]

    def test_api_error_status_code(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "data": {
                "issues": [{"message": "Bad request"}]
            }
        }
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            results = get_task_status("task123", "api-key-123")
        assert results[0][0] == "error"
        assert results[0][1] == "Bad request"

    def test_api_error_no_issues(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"data": {"issues": []}}
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            # No issues means the for-loop doesn't trigger, returns HTTP error fallback
            results = get_task_status("task123", "api-key-123")
        assert results == [("error", "HTTP 400", None, None)]

    def test_multiple_generations(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "generations": [
                    {"status": "succeed", "failMsg": None, "url": "https://v1.mp4"},
                    {"status": "processing", "failMsg": None, "url": None},
                ]
            }
        }
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp):
            results = get_task_status("task123", "api-key-123")
        assert len(results) == 2

    def test_cloudflare_block_returns_cloudflare_blocked_status(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "<html><title>Just a moment...</title>cloudflare</html>"
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp), \
             patch("img2vid.common.get_task.is_cloudflare_block", return_value=True):
            results = get_task_status("task123", "api-key-123")
        assert results[0][0] == "cloudflare_blocked"
        assert "Cloudflare" in results[0][1]

    def test_headers_include_api_key(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"generations": [{"status": "succeed", "failMsg": None, "url": "x"}]}}
        with patch("img2vid.common.get_task.requests.request", return_value=mock_resp) as mock_req:
            get_task_status("task123", "my-key")
        mock_req.assert_called_once_with(
            "GET",
            "https://pollo.ai/api/platform/generation/task123/status",
            headers={"x-api-key": "my-key"},
            timeout=30,
        )


class TestGetCreditBalance:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"availableCredits": 500, "totalCredits": 1000}
        with patch("img2vid.common.get_task.requests.get", return_value=mock_resp):
            result = get_credit_balance("api-key-123")
        assert result == {"availableCredits": 500, "totalCredits": 1000}

    def test_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("img2vid.common.get_task.requests.get", return_value=mock_resp):
            result = get_credit_balance("bad-key")
        assert result is None

    def test_network_error(self):
        with patch("img2vid.common.get_task.requests.get", side_effect=Exception("timeout")):
            result = get_credit_balance("api-key-123")
        assert result is None


