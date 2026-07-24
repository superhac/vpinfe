from __future__ import annotations

import types
import unittest
from unittest import mock

from frontend import launch_service


class _FakePopen:
    """Minimal stand-in for subprocess.Popen good enough for launch_table."""

    def __init__(self, lines=()):
        self.stdout = list(lines)
        self.waited = False

    def wait(self):
        self.waited = True
        return 0


def _make_api(events):
    table = types.SimpleNamespace(
        fullPathVPXfile="/tables/example.vpx",
        fullPathTable="/tables/example",
        tableDirName="Example",
        metaConfig={},
    )
    return types.SimpleNamespace(
        _iniConfig=types.SimpleNamespace(config={}),
        filteredTables=[table],
        frontend_browser=None,
        send_event_all_windows_incself=lambda event: events.append(event["type"]),
    )


def _launch_kwargs(popen):
    # Neutral stubs for every collaborator launch_table pulls in, so the test
    # exercises the event lifecycle without touching the real launcher, DOF, or
    # play-tracking side effects.
    vpxbin_path = types.SimpleNamespace(exists=lambda: True)
    return dict(
        get_effective_launcher=lambda vpxbin, meta: (vpxbin_path, "vpxbinpath", None),
        build_vpx_launch_command=lambda **kwargs: ["/opt/vpx", "-play", "/tables/example.vpx"],
        parse_launch_env_overrides=lambda raw: {},
        resolve_launch_tableini_override=lambda *a, **k: "",
        stop_dof_service=lambda: None,
        stop_libdmdutil_service=lambda clear=False: None,
        start_dof_service_if_enabled=lambda ini: None,
        get_plugin_profile_from_meta=lambda meta: "",
        resolve_launch_plugin_profile=lambda profile: "",
        popen=popen,
    )


class LaunchServiceLifecycleTests(unittest.TestCase):
    def _run_launch(self, popen):
        events = []
        api = _make_api(events)
        with mock.patch.object(launch_service, "SettingsConfig") as settings_cls, \
                mock.patch.object(launch_service, "delete_vpinball_log_on_start_if_configured"), \
                mock.patch.object(launch_service.table_play_service, "track_table_play"), \
                mock.patch.object(launch_service.table_play_service, "increment_start_count"), \
                mock.patch.object(launch_service.table_play_service, "add_runtime_minutes"), \
                mock.patch.object(launch_service.table_play_service, "update_score_from_nvram"), \
                mock.patch.object(launch_service.table_play_service, "delete_nvram_if_configured"), \
                mock.patch.object(launch_service, "save_last_table"), \
                mock.patch.object(launch_service, "get_active_profile", return_value=None):
            settings_cls.from_config.return_value = types.SimpleNamespace(
                vpx_bin_path="/opt/vpx",
                global_ini_override="",
                global_table_ini_override_enabled=False,
                global_table_ini_override_mask="",
                vpx_launch_env="",
            )
            launch_service.launch_table(api, 0, **_launch_kwargs(popen))
        return events

    def test_complete_fires_on_normal_launch(self):
        events = self._run_launch(lambda cmd, **kwargs: _FakePopen(["Startup done\n"]))
        self.assertEqual(events, ["TableLaunching", "TableRunning", "TableLaunchComplete"])

    def test_complete_still_emitted_when_launch_raises(self):
        # A raising popen is the whole point of the fix: TableLaunchComplete must
        # still go out so the frontend re-enables input, and the failure must
        # still propagate so it gets logged upstream.
        events = []
        api = _make_api(events)

        def boom(cmd, **kwargs):
            raise RuntimeError("popen failed")

        with mock.patch.object(launch_service, "SettingsConfig") as settings_cls, \
                mock.patch.object(launch_service, "delete_vpinball_log_on_start_if_configured"), \
                mock.patch.object(launch_service.table_play_service, "track_table_play"), \
                mock.patch.object(launch_service, "save_last_table"), \
                mock.patch.object(launch_service, "get_active_profile", return_value=None):
            settings_cls.from_config.return_value = types.SimpleNamespace(
                vpx_bin_path="/opt/vpx",
                global_ini_override="",
                global_table_ini_override_enabled=False,
                global_table_ini_override_mask="",
                vpx_launch_env="",
            )
            with self.assertRaises(RuntimeError):
                launch_service.launch_table(api, 0, **_launch_kwargs(boom))

        self.assertIn("TableLaunching", events)
        self.assertEqual(events[-1], "TableLaunchComplete")

    def test_complete_not_emitted_when_launcher_missing(self):
        # Early return before TableLaunching -> no lifecycle events at all.
        events = []
        api = _make_api(events)
        missing = types.SimpleNamespace(exists=lambda: False)
        kwargs = _launch_kwargs(lambda cmd, **k: _FakePopen())
        kwargs["get_effective_launcher"] = lambda vpxbin, meta: (missing, "vpxbinpath", None)
        with mock.patch.object(launch_service, "SettingsConfig") as settings_cls:
            settings_cls.from_config.return_value = types.SimpleNamespace(vpx_bin_path="/opt/vpx")
            launch_service.launch_table(api, 0, **kwargs)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
