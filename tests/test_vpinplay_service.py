import unittest
from unittest.mock import MagicMock, patch

from common.vpinplay_service import _build_table_payload, sync_installed_tables


class TestVPinPlayService(unittest.TestCase):
    def test_build_table_payload_includes_user_score(self) -> None:
        payload = _build_table_payload(
            {
                "Info": {
                    "VPSId": "vps-123",
                    "Rom": "agent777",
                },
                "User": {
                    "Rating": 4,
                    "LastRun": 1234567890,
                    "StartCount": 12,
                    "RunTime": 34,
                    "Score": {
                        "rom": "agent777",
                        "resolved_rom": "agent777",
                        "score_type": "HIGH SCORE",
                        "value": 999999,
                    },
                },
                "VPXFile": {},
                "VPinFE": {},
            }
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["user"]["score"]["value"], 999999)
        self.assertEqual(payload["user"]["rating"], 4)
        self.assertEqual(payload["user"]["startCount"], 12)
        self.assertEqual(payload["user"]["runTime"], 34)

    def test_build_table_payload_ignores_non_dict_user_score(self) -> None:
        payload = _build_table_payload(
            {
                "Info": {
                    "VPSId": "vps-123",
                    "Rom": "agent777",
                },
                "User": {
                    "Score": "not-a-dict",
                },
                "VPXFile": {},
                "VPinFE": {},
            }
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIsNone(payload["user"]["score"])

    @patch("common.vpinplay_service.requests.post")
    @patch("common.vpinplay_service.get_version", return_value="test-version")
    @patch("common.vpinplay_service.TableParser")
    def test_sync_installed_tables_includes_initials_in_client_payload(
        self,
        mock_table_parser,
        _mock_get_version,
        mock_post,
    ) -> None:
        table = MagicMock()
        table.metaConfig = {
            "Info": {"VPSId": "vps-123", "Rom": "agent777"},
            "User": {},
            "VPXFile": {},
            "VPinFE": {},
        }
        parser_instance = mock_table_parser.return_value
        parser_instance.getAllTables.return_value = [table]

        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.text = "ok"
        response.json.return_value = {"ok": True}
        mock_post.return_value = response

        with patch("common.vpinplay_service.Path.exists", return_value=True), patch(
            "common.vpinplay_service.Path.is_dir", return_value=True
        ):
            sync_installed_tables(
                service_ip="https://api.vpinplay.com:8888",
                user_id="user-123",
                initials="ABC",
                machine_id="machine-123",
                table_root_dir="/tables",
            )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["client"]["userId"], "user-123")
        self.assertEqual(payload["client"]["initials"], "ABC")
        self.assertEqual(payload["client"]["machineId"], "machine-123")


if __name__ == "__main__":
    unittest.main()
