"""命名规则：从卡片文字认文件名、清成合法文件名。"""
from __future__ import annotations

import unittest

from weizhujiao_dl.naming import DEFAULT_NAME, filename_from_label, safe_filename


class TestFilenameFromLabel(unittest.TestCase):
    def test_with_read_mark(self):
        label = "K0002-1-1 Chapter One From C to C++.ppt 已读 Chapter One From C to C++.ppt"
        self.assertEqual(filename_from_label(label), "Chapter One From C to C++.ppt")

    def test_without_read_mark_strips_id(self):
        self.assertEqual(filename_from_label("K0003-1 第三章 线性表.pdf"), "第三章 线性表.pdf")

    def test_unread_mark(self):
        self.assertEqual(filename_from_label("K0005-1 数据结构.pdf 未读 数据结构.pdf"),
                         "数据结构.pdf")

    def test_id_glued_to_name_is_kept(self):
        self.assertEqual(filename_from_label("K0004-2-3实验报告.docx"), "K0004-2-3实验报告.docx")

    def test_dash_inside_name_kept(self):
        self.assertEqual(filename_from_label("K0006-1 第一章-绪论.pptx"), "第一章-绪论.pptx")

    def test_chinese_colon_already_fine(self):
        self.assertEqual(filename_from_label("K0007-1 实验：第三次实验报告.doc"),
                         "实验：第三次实验报告.doc")

    def test_no_doc_extension(self):
        self.assertIsNone(filename_from_label("K0008-1 直播回放 已读"))
        self.assertIsNone(filename_from_label(""))
        self.assertIsNone(filename_from_label(None))

    def test_uppercase_extension(self):
        self.assertEqual(filename_from_label("K0009-1 SLIDES.PPTX"), "SLIDES.PPTX")


class TestSafeFilename(unittest.TestCase):
    def test_illegal_chars_replaced(self):
        self.assertEqual(safe_filename('a<b>c:d"e/f\\g|h?i*j'), "a_b_c_d_e_f_g_h_i_j")

    def test_trailing_dots_and_spaces(self):
        self.assertEqual(safe_filename("  报告.pdf . . "), "报告.pdf")

    def test_collapses_whitespace(self):
        self.assertEqual(safe_filename("a   b\tc.pdf"), "a b c.pdf")

    def test_empty_falls_back(self):
        self.assertEqual(safe_filename("   "), DEFAULT_NAME)
        self.assertEqual(safe_filename(None), DEFAULT_NAME)

    def test_long_name_keeps_extension(self):
        out = safe_filename("长" * 300 + ".pdf", max_len=60)
        self.assertTrue(out.endswith(".pdf"))
        self.assertLessEqual(len(out), 60)

    def test_long_name_without_extension_truncated(self):
        out = safe_filename("长" * 100, max_len=10)
        self.assertEqual(len(out), 10)

    def test_windows_reserved_names_prefixed(self):
        self.assertEqual(safe_filename("CON.txt"), "_CON.txt")
        self.assertEqual(safe_filename("com1.pdf"), "_com1.pdf")


if __name__ == "__main__":
    unittest.main()
