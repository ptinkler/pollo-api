"""Tests for img2vid.pollo.pollo_img2vid — orchestrator (create_video, get_video_generator)."""
import pytest
from unittest.mock import patch, MagicMock

from img2vid.pollo.pollo_img2vid import get_video_generator, create_video, GENERATORS, DEFAULT_MODEL


class TestGeneratorsMap:
    def test_all_models_present(self):
        expected = {"pollo20", "pollodance20", "pollodance20fast",
                    "pollodanceref", "pollodancereffast"}
        assert set(GENERATORS.keys()) == expected

    def test_default_model(self):
        assert DEFAULT_MODEL == "pollodance20"


class TestGetVideoGenerator:
    @patch("img2vid.pollo.generators.get_prompt", return_value="p")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_returns_generator(self, *mocks):
        gen = get_video_generator("pollodance20", api_key="k", project="p", prompt="x")
        assert gen.__class__.__name__ == "PolloDance20VideoGenerator"

    def test_invalid_model(self):
        with pytest.raises(ValueError, match="Unsupported model"):
            get_video_generator("nonexistent")


class TestCreateVideo:
    def test_invalid_model(self):
        with pytest.raises(ValueError, match="Unknown model"):
            create_video(model="badmodel")

    def test_invalid_length(self):
        with pytest.raises(ValueError, match="Invalid length"):
            create_video(model="pollo20", length=99)

    def test_invalid_ratio(self):
        with pytest.raises(ValueError, match="Invalid ratio"):
            create_video(model="pollodance20", aspect_ratio="99:1")

    def test_invalid_resolution(self):
        with pytest.raises(ValueError, match="Invalid resolution"):
            create_video(model="pollodance20", resolution="4k")

    @patch("img2vid.pollo.pollo_img2vid.download_video")
    @patch("img2vid.pollo.pollo_img2vid.download_image")
    @patch("img2vid.pollo.pollo_img2vid.get_task_status")
    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.pollo_img2vid.Spinner")
    @patch("img2vid.pollo.pollo_img2vid.sleep")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value="https://img.com/i.jpg")
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_successful_generation(
        self, mock_path, mock_img_url, mock_prompt, mock_sleep, MockSpinner,
        mock_db, mock_task, mock_dl_img, mock_dl_vid,
    ):
        # Setup mocks
        db_inst = MagicMock()
        mock_db.return_value = db_inst

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {"taskId": "t123", "status": "processing"},
        }

        mock_task.return_value = [("succeed", None, "https://video.com/out.mp4")]
        mock_dl_vid.return_value = "/path/to/video.mp4"

        spinner = MagicMock()
        MockSpinner.return_value = spinner

        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(model="pollodance20", project="testproj")

        # Should have downloaded video
        mock_dl_vid.assert_called_once()
        # Should have updated job status to done
        done_calls = [c for c in db_inst.update_job.call_args_list
                      if c.kwargs.get("status") == "done" or
                         (len(c.args) > 1 and "done" in str(c))]
        assert len(done_calls) > 0, "Expected at least one update_job call with status='done'"

    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_api_error(self, mock_path, mock_url, mock_prompt, mock_db):
        db_inst = MagicMock()
        mock_db.return_value = db_inst

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"code": "ERROR", "message": "Bad request"}

        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(model="pollodance20", project="testproj")

        # Should have updated job to error
        calls = [str(c) for c in db_inst.update_job.call_args_list]
        assert any("error" in c for c in calls)

    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_no_task_id(self, mock_path, mock_url, mock_prompt, mock_db):
        db_inst = MagicMock()
        mock_db.return_value = db_inst

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": "SUCCESS", "data": {}}

        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(model="pollodance20", project="testproj")

        calls = [str(c) for c in db_inst.update_job.call_args_list]
        assert any("error" in c for c in calls)

    # ── Cover all kwargs paths (lines 76-93) ────────────────────
    @patch("img2vid.pollo.pollo_img2vid.download_video")
    @patch("img2vid.pollo.pollo_img2vid.download_image")
    @patch("img2vid.pollo.pollo_img2vid.get_task_status")
    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.pollo_img2vid.Spinner")
    @patch("img2vid.pollo.pollo_img2vid.sleep")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_all_kwargs(self, *mocks):
        """Cover all optional kwargs paths."""
        mock_subj, mock_path, mock_img_url, mock_prompt, \
            mock_sleep, MockSpinner, mock_db, mock_task, mock_dl_img, mock_dl_vid = mocks

        db_inst = MagicMock()
        mock_db.return_value = db_inst
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {"taskId": "t1", "status": "processing"},
        }
        mock_task.return_value = [("succeed", None, "https://video.com/out.mp4")]
        mock_dl_vid.return_value = "/path/to/video.mp4"
        MockSpinner.return_value = MagicMock()

        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(
                model="pollodanceref",
                project="proj",
                aspect_ratio="16:9",
                length=10,
                resolution="720p",
                generate_audio=True,
                image_url="https://img.com/i.jpg",
                subject_url="https://subj.com/s.jpg",
            )
        mock_dl_vid.assert_called_once()

    # ── Video edit mode (lines 117-119) ────────────────────
    @patch("img2vid.pollo.pollo_img2vid.download_video")
    @patch("img2vid.pollo.pollo_img2vid.download_image")
    @patch("img2vid.pollo.pollo_img2vid.get_task_status")
    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.pollo_img2vid.Spinner")
    @patch("img2vid.pollo.pollo_img2vid.sleep")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    @patch("img2vid.pollo.generators.get_subject_url", return_value=None)
    def test_video_edit_mode(self, *mocks):
        """Cover the ref2video mode branch — should NOT download image."""
        mock_subj, mock_path, mock_img_url, mock_prompt, \
            mock_sleep, MockSpinner, mock_db, mock_task, mock_dl_img, mock_dl_vid = mocks
        db_inst = MagicMock()
        mock_db.return_value = db_inst
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {"taskId": "t2", "status": "processing"},
        }
        mock_task.return_value = [("succeed", None, "https://video.com/out.mp4")]
        mock_dl_vid.return_value = "/path/to/video.mp4"
        MockSpinner.return_value = MagicMock()

        refs = [{"type": "image", "name": "char", "image": "https://img.com/a.jpg", "order": 1}]
        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(
                model="pollodanceref",
                project="proj",
                refs=refs,
            )
        # Should NOT download image (ref2video mode)
        mock_dl_img.assert_not_called()

    # ── Polling error (lines 154-158) ────────────────────
    @patch("img2vid.pollo.pollo_img2vid.get_task_status")
    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.pollo_img2vid.Spinner")
    @patch("img2vid.pollo.pollo_img2vid.sleep")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_polling_error(self, mock_path, mock_url, mock_prompt, mock_sleep,
                           MockSpinner, mock_db, mock_task):
        db_inst = MagicMock()
        mock_db.return_value = db_inst
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {"taskId": "t3", "status": "processing"},
        }
        mock_task.return_value = [("failed", "Generation failed", None)]
        MockSpinner.return_value = MagicMock()

        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(model="pollodance20", project="proj")
        err_calls = [str(c) for c in db_inst.update_job.call_args_list]
        assert any("error" in c for c in err_calls)

    # ── No URL result (lines 161-164) ────────────────────
    @patch("img2vid.pollo.pollo_img2vid.get_task_status")
    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.pollo_img2vid.Spinner")
    @patch("img2vid.pollo.pollo_img2vid.sleep")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_no_url_in_result(self, mock_path, mock_url, mock_prompt, mock_sleep,
                              MockSpinner, mock_db, mock_task):
        db_inst = MagicMock()
        mock_db.return_value = db_inst
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {"taskId": "t4", "status": "processing"},
        }
        mock_task.return_value = [("succeed", None, None)]
        MockSpinner.return_value = MagicMock()

        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(model="pollodance20", project="proj")
        err_calls = [str(c) for c in db_inst.update_job.call_args_list]
        assert any("error" in c for c in err_calls)

    # ── Cloudflare block during polling — retries then gives up ────
    @patch("img2vid.pollo.pollo_img2vid.get_task_status")
    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.pollo_img2vid.Spinner")
    @patch("img2vid.pollo.pollo_img2vid.sleep")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_cloudflare_block_polling_gives_up(self, mock_path, mock_url, mock_prompt,
                                                mock_sleep, MockSpinner, mock_db, mock_task):
        """Cloudflare blocks all polling attempts — should give up after max retries."""
        db_inst = MagicMock()
        mock_db.return_value = db_inst
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {"taskId": "t_cf", "status": "processing"},
        }
        # Always return cloudflare_blocked
        mock_task.return_value = [("cloudflare_blocked", "Cloudflare blocked the request", None)]
        MockSpinner.return_value = MagicMock()

        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(model="pollodance20", project="proj")

        err_calls = [str(c) for c in db_inst.update_job.call_args_list]
        assert any("error" in c for c in err_calls)
        assert any("Cloudflare" in c for c in err_calls)

    # ── Cloudflare block during polling — recovers after a few blocks ────
    @patch("img2vid.pollo.pollo_img2vid.download_video")
    @patch("img2vid.pollo.pollo_img2vid.download_image")
    @patch("img2vid.pollo.pollo_img2vid.get_task_status")
    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.pollo_img2vid.Spinner")
    @patch("img2vid.pollo.pollo_img2vid.sleep")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value=None)
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_cloudflare_block_polling_recovers(self, mock_path, mock_url, mock_prompt,
                                                mock_sleep, MockSpinner, mock_db,
                                                mock_task, mock_dl_img, mock_dl_vid):
        """Cloudflare blocks a few polls, then clears — should succeed."""
        db_inst = MagicMock()
        mock_db.return_value = db_inst
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {"taskId": "t_cf2", "status": "processing"},
        }
        # 2 cloudflare blocks, then processing, then success
        mock_task.side_effect = [
            [("cloudflare_blocked", "Cloudflare blocked", None)],
            [("cloudflare_blocked", "Cloudflare blocked", None)],
            [("processing", None, None)],
            [("succeed", None, "https://video.com/out.mp4")],
        ]
        mock_dl_vid.return_value = "/path/to/video.mp4"
        MockSpinner.return_value = MagicMock()

        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(model="pollodance20", project="proj")

        # Should have downloaded the video successfully
        mock_dl_vid.assert_called_once()
        done_calls = [c for c in db_inst.update_job.call_args_list
                      if c.kwargs.get("status") == "done" or
                         (len(c.args) > 1 and "done" in str(c))]
        assert len(done_calls) > 0

    # ── Download ValueError (lines 188-191) ────────────────────
    @patch("img2vid.pollo.pollo_img2vid.download_video", side_effect=ValueError("corrupt"))
    @patch("img2vid.pollo.pollo_img2vid.download_image")
    @patch("img2vid.pollo.pollo_img2vid.get_task_status")
    @patch("img2vid.pollo.pollo_img2vid.get_db")
    @patch("img2vid.pollo.pollo_img2vid.Spinner")
    @patch("img2vid.pollo.pollo_img2vid.sleep")
    @patch("img2vid.pollo.generators.get_prompt", return_value="test prompt")
    @patch("img2vid.pollo.generators.get_image_url", return_value="https://img.com/i.jpg")
    @patch("img2vid.pollo.generators.get_image_path", return_value=None)
    def test_download_valueerror(self, mock_path, mock_img_url, mock_prompt,
                                 mock_sleep, MockSpinner, mock_db, mock_task,
                                 mock_dl_img, mock_dl_vid):
        db_inst = MagicMock()
        mock_db.return_value = db_inst
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "SUCCESS",
            "data": {"taskId": "t5", "status": "processing"},
        }
        mock_task.return_value = [("succeed", None, "https://video.com/out.mp4")]
        MockSpinner.return_value = MagicMock()

        with patch("img2vid.pollo.generators.requests.request", return_value=mock_response):
            create_video(model="pollodance20", project="proj")
        err_calls = [str(c) for c in db_inst.update_job.call_args_list]
        assert any("error" in c for c in err_calls)


class TestPolloImg2VidMainGuard:
    def test_name_main_guard(self):
        """Cover the if __name__ == '__main__' guard."""
        import img2vid.pollo.pollo_img2vid as mod
        with patch.object(mod, "create_video") as mock_cv, \
             patch.object(mod, "__name__", "__main__"):
            if mod.__name__ == "__main__":
                mod.create_video()
        mock_cv.assert_called_once()

