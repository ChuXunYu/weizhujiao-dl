"""编排：整条链路（含 403→带参、404→改名）用假页面 + 假会话跑通。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from weizhujiao_dl.config import Settings
from weizhujiao_dl.errors import LoginRequired
from weizhujiao_dl.links import rebuild_url
from weizhujiao_dl.models import Courseware, Reason, Status
from weizhujiao_dl.runner import Runner
from weizhujiao_dl.state import StateStore

from .fakes import FakePage, FakeResponse, FakeSession

BASE = "https://app.teachermate.com.cn/9cdLn-1693370741604-"
NAME = "Chapter One From C to C++.ppt"
PLAIN = BASE + "Chapter+One+From+C+to+C%2B%2B.ppt"
SIGNED = PLAIN + "?e=1&token=abc"
WRONG_PLAIN = BASE + "wrong.pdf"                          # 平台给的链接里名字不对
WRONG_SIGNED = WRONG_PLAIN + "?e=1&token=abc"
REBUILT = rebuild_url(WRONG_PLAIN, NAME)                  # = PLAIN


def make_settings(out_dir: Path, **kw) -> Settings:
    base = {"course_url": "https://teachermate.example/list", "button_xpath": "//button",
                "out_dir": out_dir, "state_file": out_dir / ".wzd-state.json"}
    base.update(kw)
    return Settings(**base)


class RunnerTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "downloads"
        self.state = StateStore(self.out / ".wzd-state.json")
        self.items = [Courseware(index=1, label="K0002-1 " + NAME + " 已读 " + NAME, filename=NAME)]

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, page, session, **kw) -> Runner:
        settings = make_settings(self.out, **kw)
        return Runner(settings=settings, page=page, session=session, state=self.state,
                      user_agent="ua-test", sleep=lambda _s: None, rand=lambda _a, _b: 0.0)


class TestHappyPath(RunnerTestBase):
    def test_plain_link_success(self):
        session = FakeSession({PLAIN: FakeResponse(chunks=[b"data"])})
        summary = self.runner(FakePage(self.items, link=PLAIN), session).run()

        self.assertEqual(summary.count(Status.OK), 1)
        self.assertEqual(summary.total_found, 1)
        saved = self.out / NAME
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.read_bytes(), b"data")
        self.assertEqual(summary.downloaded_bytes, 4)
        self.assertTrue(self.out.joinpath(".wzd-state.json").is_file())

    def test_referer_and_ua_sent(self):
        session = FakeSession({PLAIN: FakeResponse()})
        self.runner(FakePage(self.items, link=PLAIN), session).run()
        headers = session.calls[0][1]["headers"]
        self.assertEqual(headers["User-Agent"], "ua-test")
        self.assertEqual(headers["Referer"], "https://preview.example/1")

    def test_returns_to_list_once_per_item(self):
        page = FakePage(self.items, link=PLAIN)
        self.runner(page, FakeSession({PLAIN: FakeResponse()})).run()
        self.assertEqual(page.backs, 1)


class TestSkipAndForce(RunnerTestBase):
    def test_skip_when_state_says_done(self):
        self.out.mkdir(parents=True)
        (self.out / NAME).write_bytes(b"abc")
        self.state.record(NAME, 3)
        session = FakeSession()
        summary = self.runner(FakePage(self.items, link=PLAIN), session).run()

        outcome = summary.outcomes[0]
        self.assertIs(outcome.status, Status.SKIPPED)
        self.assertIs(outcome.reason, Reason.ALREADY_DOWNLOADED)
        self.assertEqual(session.calls, [])

    def test_force_redownloads(self):
        self.out.mkdir(parents=True)
        (self.out / NAME).write_bytes(b"old")
        self.state.record(NAME, 3)
        session = FakeSession({PLAIN: FakeResponse(chunks=[b"new-data"])})
        summary = self.runner(FakePage(self.items, link=PLAIN), session, force=True).run()

        self.assertIs(summary.outcomes[0].status, Status.OK)
        self.assertEqual((self.out / NAME).read_bytes(), b"new-data")


class TestFallbackChain(RunnerTestBase):
    def test_403_then_signed_ok(self):
        session = FakeSession({PLAIN: FakeResponse(status=403),
                               SIGNED: FakeResponse(chunks=[b"ok"])})
        summary = self.runner(FakePage(self.items, link=SIGNED), session).run()

        outcome = summary.outcomes[0]
        self.assertIs(outcome.status, Status.OK, msg=outcome.detail)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(len(session.calls), 2)

    def test_404_then_rewritten_ok(self):
        session = FakeSession({WRONG_PLAIN: FakeResponse(status=404),
                               WRONG_SIGNED: FakeResponse(status=404),
                               REBUILT: FakeResponse(chunks=[b"fixed"])})
        summary = self.runner(FakePage(self.items, link=WRONG_SIGNED), session).run()

        outcome = summary.outcomes[0]
        self.assertIs(outcome.status, Status.OK, msg=outcome.detail)
        self.assertEqual(outcome.attempts, 3)
        self.assertEqual(session.urls[-1], REBUILT)

    def test_all_fail_reports_http_error(self):
        session = FakeSession({WRONG_PLAIN: FakeResponse(status=403),
                               WRONG_SIGNED: FakeResponse(status=403),
                               REBUILT: FakeResponse(status=403)})
        summary = self.runner(FakePage(self.items, link=WRONG_SIGNED), session).run()

        outcome = summary.outcomes[0]
        self.assertIs(outcome.status, Status.FAILED)
        self.assertIn(outcome.reason, {Reason.DENIED, Reason.HTTP_ERROR})
        self.assertEqual(len(session.calls), 3)

    def test_500_stops_immediately(self):
        session = FakeSession({PLAIN: FakeResponse(status=500)})
        summary = self.runner(FakePage(self.items, link=PLAIN), session).run()

        outcome = summary.outcomes[0]
        self.assertIs(outcome.reason, Reason.HTTP_ERROR)
        self.assertEqual(len(session.calls), 1)


class TestFailureReasons(RunnerTestBase):
    def test_no_link(self):
        summary = self.runner(FakePage(self.items, link=None), FakeSession()).run()
        outcome = summary.outcomes[0]
        self.assertIs(outcome.status, Status.FAILED)
        self.assertIs(outcome.reason, Reason.NO_LINK)

    def test_login_lost_aborts_loop(self):
        items = self.items * 3
        page = FakePage(items, link=PLAIN, preview_exc=LoginRequired("登录态没了"))
        summary = self.runner(page, FakeSession()).run()

        self.assertEqual(len(summary.outcomes), 1)
        self.assertIs(summary.outcomes[0].reason, Reason.LOGIN_REQUIRED)
        self.assertIn("登录态", summary.outcomes[0].detail)

    def test_wait_courseware_login_required_propagates(self):
        class LoginPage(FakePage):
            def wait_courseware(self, xpath):
                raise LoginRequired("跳登录页了")

        runner = self.runner(LoginPage(self.items), FakeSession())
        with self.assertRaises(LoginRequired):
            runner.run()


class TestDryRunAndLimit(RunnerTestBase):
    def test_dry_run_no_download(self):
        session = FakeSession()
        summary = self.runner(FakePage(self.items, link=PLAIN), session, dry_run=True).run()

        self.assertIs(summary.outcomes[0].status, Status.DRY)
        self.assertEqual(session.calls, [])
        self.assertFalse((self.out / NAME).exists())

    def test_limit(self):
        items = [Courseware(index=i, label="K000%d-1 f%d.pdf" % (i, i), filename="f%d.pdf" % i)
                 for i in range(1, 4)]
        session = FakeSession({PLAIN: FakeResponse()})
        summary = self.runner(FakePage(items, link=PLAIN), session, limit=2).run()

        self.assertEqual(summary.total_found, 3)
        self.assertEqual(len(summary.outcomes), 2)

    def test_name_guessed_from_url_when_missing(self):
        items = [Courseware(index=1, label="K0002-1 未知", filename=None)]
        session = FakeSession({PLAIN: FakeResponse(chunks=[b"x"])})
        summary = self.runner(FakePage(items, link=PLAIN), session).run()

        self.assertIs(summary.outcomes[0].status, Status.OK)
        self.assertTrue((self.out / NAME).is_file())


if __name__ == "__main__":
    unittest.main()
