"""直链处理：判断、挑候选、剥签名、按名重拼、降级顺序。"""
from __future__ import annotations

import unittest

from weizhujiao_dl.links import (
    filename_from_url,
    link_plan,
    looks_like_direct_link,
    pick_direct_link,
    rebuild_url,
    strip_query,
)

BASE = "https://app.teachermate.com.cn/9cdLn-1693370741604-"
PLAIN = BASE + "Chapter+One+From+C+to+C%2B%2B.ppt"        # 名字已经写得对
SIGNED = PLAIN + "?e=1&token=abc"
WRONG_PLAIN = BASE + "wrong.pdf"                            # 名字和课件对不上
WRONG_SIGNED = WRONG_PLAIN + "?e=1&token=abc"


class TestLooksLikeDirectLink(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(looks_like_direct_link(PLAIN))
        self.assertTrue(looks_like_direct_link("http://x/y.PDF"))

    def test_rejects(self):
        self.assertFalse(looks_like_direct_link(""))
        self.assertFalse(looks_like_direct_link(None))
        self.assertFalse(looks_like_direct_link("请看这里"))
        self.assertFalse(looks_like_direct_link("https://x/y.html"))


class TestPickDirectLink(unittest.TestCase):
    def test_prefers_same_name(self):
        other = BASE + "other.pdf"
        picked = pick_direct_link([other, PLAIN], "Chapter One From C to C++.ppt")
        self.assertEqual(picked, PLAIN)

    def test_falls_back_to_same_extension(self):
        picked = pick_direct_link(["https://h/a.docx"], "b.pdf")
        self.assertEqual(picked, "https://h/a.docx")

    def test_first_when_no_name(self):
        self.assertEqual(pick_direct_link(["https://h/a.pdf", "https://h/b.pdf"]), "https://h/a.pdf")

    def test_none_when_empty(self):
        self.assertIsNone(pick_direct_link([], "a.pdf"))
        self.assertIsNone(pick_direct_link(["不是链接"], "a.pdf"))


class TestUrlRewrite(unittest.TestCase):
    def test_strip_query(self):
        self.assertEqual(strip_query(SIGNED), PLAIN)

    def test_rebuild_encodes_plus_and_space(self):
        broken = BASE + "Chapter One From C to C .ppt"
        fixed = rebuild_url(broken, "Chapter One From C to C++.ppt")
        self.assertEqual(fixed, PLAIN)

    def test_rebuild_without_filename_noop(self):
        self.assertEqual(rebuild_url(PLAIN, None), PLAIN)

    def test_rebuild_without_platform_prefix_noop(self):
        """认不出平台前缀就别动链接（旧实现 rfind('-') 会盲目切）。"""
        url = "https://cdn.example.com/music/a-b-c.pdf"
        self.assertEqual(rebuild_url(url, "x.pdf"), url)

    def test_filename_from_url_strips_prefix(self):
        self.assertEqual(filename_from_url(PLAIN), "Chapter One From C to C++.ppt")

    def test_filename_from_url_plain(self):
        self.assertEqual(filename_from_url("https://h/%E8%AF%BE%E4%BB%B6.pdf"), "课件.pdf")

    def test_filename_from_url_empty_path(self):
        self.assertEqual(filename_from_url("https://h/"), "download")


class TestLinkPlan(unittest.TestCase):
    def test_wrong_name_adds_rewrite_step(self):
        plan = link_plan(WRONG_SIGNED, "Chapter One From C to C++.ppt")
        labels = [label for label, _ in plan]
        self.assertEqual(labels, ["无签名直链", "带签名原始链接", "按课件名重写文件名"])
        self.assertEqual(plan[0][1], WRONG_PLAIN)
        self.assertEqual(plan[1][1], WRONG_SIGNED)
        self.assertEqual(plan[2][1], PLAIN)

    def test_correct_name_has_no_rewrite_step(self):
        """名字本来就对时不该多打一次请求（去重后只剩两步）。"""
        plan = link_plan(SIGNED, "Chapter One From C to C++.ppt")
        self.assertEqual([label for label, _ in plan], ["无签名直链", "带签名原始链接"])

    def test_no_query_no_signed_step(self):
        plan = link_plan(WRONG_PLAIN, "Chapter One From C to C++.ppt")
        self.assertEqual([label for label, _ in plan], ["无签名直链", "按课件名重写文件名"])

    def test_no_filename_keeps_two_steps(self):
        plan = link_plan(SIGNED, None)
        self.assertEqual([label for label, _ in plan], ["无签名直链", "带签名原始链接"])


if __name__ == "__main__":
    unittest.main()
