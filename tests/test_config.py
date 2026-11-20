"""配置合并与校验。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from weizhujiao_dl.config import Settings, read_env_file
from weizhujiao_dl.errors import ConfigError


def args(**kw):
    base = {"env": str(Path(tempfile.gettempdir()) / "no_such.env"),
                "course_url": None, "xpath": None, "out": None, "state": None, "json": None,
                "limit": None, "dry_run": False, "headless": False, "force": False,
                "user_data_dir": None, "chrome_binary": None, "timeout": 20,
                "download_timeout": 60, "delay_min": 1.0, "delay_max": 2.0,
                "retries": 2, "verbose": 0, "quiet": False}
    base.update(kw)
    return SimpleNamespace(**base)


class TestReadEnvFile(unittest.TestCase):
    def test_quotes_comments_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".env"
            p.write_text(
                "# 注释\n"
                "\n"
                'COURSE_LIST_URL="https://x/y?a=1"\n'
                "COURSE_BUTTON_LOCATOR_XPATH='//a/b'\n"
                "export OUT_DIR=D:\\课件\n"
                "EMPTY=\n",
                encoding="utf-8")
            values = read_env_file(p)
        self.assertEqual(values["COURSE_LIST_URL"], "https://x/y?a=1")
        self.assertEqual(values["COURSE_BUTTON_LOCATOR_XPATH"], "//a/b")
        self.assertEqual(values["OUT_DIR"], "D:\\课件")
        self.assertEqual(values["EMPTY"], "")

    def test_missing_file_is_empty(self):
        self.assertEqual(read_env_file("no_such_file.env"), {})


class TestSettingsBuild(unittest.TestCase):
    def test_cli_overrides_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".env"
            p.write_text('COURSE_LIST_URL="https://env/file"\n'
                         "COURSE_BUTTON_LOCATOR_XPATH=//env\n", encoding="utf-8")
            settings = Settings.build(args(env=str(p), course_url="https://cli/x"))
        self.assertEqual(settings.course_url, "https://cli/x")
        self.assertEqual(settings.button_xpath, "//env")

    def test_environ_used_when_no_cli(self):
        settings = Settings.build(
            args(), environ={"COURSE_LIST_URL": "https://env/only",
                             "COURSE_BUTTON_LOCATOR_XPATH": "//env"})
        self.assertEqual(settings.course_url, "https://env/only")

    def test_missing_url_raises(self):
        with self.assertRaises(ConfigError):
            Settings.build(args(), environ={})

    def test_missing_xpath_raises(self):
        with self.assertRaises(ConfigError):
            Settings.build(args(course_url="https://x"), environ={})

    def test_bad_limit_raises(self):
        with self.assertRaises(ConfigError):
            Settings.build(args(course_url="https://x", xpath="//a", limit=0), environ={})

    def test_delay_range_swapped(self):
        s = Settings.build(args(course_url="https://x", xpath="//a",
                                delay_min=5, delay_max=1), environ={})
        self.assertEqual((s.delay_min, s.delay_max), (1.0, 5.0))

    def test_negative_delay_raises(self):
        with self.assertRaises(ConfigError):
            Settings.build(args(course_url="https://x", xpath="//a", delay_min=-1), environ={})

    def test_retries_clamped_non_negative(self):
        s = Settings.build(args(course_url="https://x", xpath="//a", retries=-3), environ={})
        self.assertEqual(s.retries, 0)

    def test_default_state_and_out_dir(self):
        s = Settings.build(args(course_url="https://x", xpath="//a", out="out"), environ={})
        self.assertEqual(s.out_dir.name, "out")
        self.assertEqual(s.state_file.name, ".wzd-state.json")

    def test_state_override(self):
        s = Settings.build(args(course_url="https://x", xpath="//a",
                                out="out", state="st.json"), environ={})
        self.assertEqual(s.state_file.name, "st.json")


if __name__ == "__main__":
    unittest.main()
