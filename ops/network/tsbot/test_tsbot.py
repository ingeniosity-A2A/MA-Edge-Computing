#!/usr/bin/env python3
"""Regression tests for tsbot's Tailscale command boundary."""

import unittest
from unittest.mock import patch

import tsbot


class AllowlistTests(unittest.TestCase):
    def test_read_only_commands_are_allowed(self):
        for argv in (
            ["status", "--json"],
            ["status"],
            ["netcheck", "--format=json"],
            ["ip", "-4"],
            ["version"],
            ["dns", "status", "--json"],
        ):
            with self.subTest(argv=argv):
                self.assertTrue(tsbot.allowed(argv))

    def test_parameterized_exit_node_commands_are_allowed(self):
        self.assertTrue(tsbot.allowed(["set", "--exit-node="]))
        self.assertTrue(tsbot.allowed(["set", "--exit-node=100.91.36.108"]))
        self.assertTrue(tsbot.allowed(["set", "--exit-node=vps-73b462c2"]))

    def test_boolean_preferences_are_allowed(self):
        for name in ("accept-routes", "advertise-exit-node", "shields-up"):
            for value in ("true", "false"):
                with self.subTest(name=name, value=value):
                    self.assertTrue(tsbot.allowed(["set", f"--{name}={value}"]))

    def test_expected_ping_shapes_are_allowed(self):
        self.assertTrue(tsbot.allowed([
            "ping", "--until-direct=false", "-c", "2", "--timeout=3s", "100.121.129.77"
        ]))
        self.assertTrue(tsbot.allowed([
            "ping", "--until-direct=false", "-c", "2", "--timeout=3s", "brianqs-s26-ultra-1"
        ]))

    @patch("tsbot.run_ts")
    def test_peer_probe_accepts_derp_and_direct_paths(self, mocked_run):
        mocked_run.return_value = {"code": 0, "out": "pong via DERP", "err": ""}
        result = tsbot.probe_peer("100.121.129.77")
        self.assertTrue(result["ok"])
        mocked_run.assert_called_once_with(
            ["ping", "--until-direct=false", "-c", "2", "--timeout=3s", "100.121.129.77"],
            timeout=25,
        )

    def test_connectivity_and_policy_commands_remain_forbidden(self):
        for argv in (
            ["up"],
            ["down"],
            ["logout"],
            ["login"],
            ["serve"],
            ["funnel"],
            ["cert"],
            ["ssh"],
            ["debug"],
        ):
            with self.subTest(argv=argv):
                self.assertFalse(tsbot.allowed(argv))

    def test_malformed_or_injected_arguments_are_rejected(self):
        for argv in (
            ["set", "--exit-node=not a hostname"],
            ["set", "--exit-node=100.1.2.3;up"],
            ["set", "--accept-routes=yes"],
            ["set", "--shields-up"],
            ["ping", "-c", "99", "100.121.129.77"],
            ["ping", "-c", "3", "--timeout=3s", "100.121.129.77;up"],
        ):
            with self.subTest(argv=argv):
                self.assertFalse(tsbot.allowed(argv))

    @patch("tsbot.subprocess.run")
    def test_run_ts_passes_allowed_args_without_a_shell(self, mocked_run):
        mocked_run.return_value.returncode = 0
        mocked_run.return_value.stdout = "ok"
        mocked_run.return_value.stderr = ""
        result = tsbot.run_ts(["set", "--exit-node="])
        self.assertEqual(result["code"], 0)
        mocked_run.assert_called_once_with(
            ["tailscale", "set", "--exit-node="],
            capture_output=True,
            text=True,
            timeout=15,
        )

    @patch("tsbot.subprocess.run")
    def test_run_ts_blocks_forbidden_args_before_execution(self, mocked_run):
        result = tsbot.run_ts(["up"])
        self.assertEqual(result["code"], 126)
        mocked_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
