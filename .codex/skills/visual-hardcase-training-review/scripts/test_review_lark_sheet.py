#!/usr/bin/env python3
"""Focused tests for Feishu cloud-sheet review helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from review_lark_sheet import attach_float_images
from review_training_workbook import build_wiki_headers, has_format_constraint


class AttachFloatImagesTest(unittest.TestCase):
    def test_maps_float_images_in_image_columns_to_matching_rows(self) -> None:
        rows = [
            {"_row_number": "797", "图片1": "", "图片2": ""},
            {"_row_number": "798", "图片1": ""},
        ]
        float_images = [
            {"address": "G797", "url": "https://example.test/row797-img1.png"},
            {"address": "H797", "url": "https://example.test/row797-img2.png"},
            {"address": "G798", "url": "https://example.test/row798-img1.png"},
            {"address": "U797", "url": "https://example.test/validation.png"},
            {"address": "G800", "url": "https://example.test/outside.png"},
        ]

        attach_float_images(rows, float_images)

        self.assertEqual(rows[0]["图片1"], "https://example.test/row797-img1.png")
        self.assertEqual(rows[0]["图片2"], "https://example.test/row797-img2.png")
        self.assertEqual(rows[1]["图片1"], "https://example.test/row798-img1.png")

    def test_preserves_existing_image_text(self) -> None:
        rows = [{"_row_number": "797", "图片1": "https://example.test/existing.png"}]
        float_images = [{"address": "G797", "url": "https://example.test/from-float.png"}]

        attach_float_images(rows, float_images)

        self.assertEqual(rows[0]["图片1"], "https://example.test/existing.png")


class HasFormatConstraintTest(unittest.TestCase):
    def test_accepts_exact_output_only_wording(self) -> None:
        prompt = "如图所示，与图1挂件玩偶为同一款玩偶的是哪一张图片？仅输出相应的图片编号"

        self.assertTrue(has_format_constraint(prompt))

    def test_accepts_ordered_letter_output_wording(self) -> None:
        prompt = (
            "从图1到图2发生了哪些视觉上的变化，选出符合变化的选项？"
            "按照英语字母表中的顺序从前往后依次大写输出（字母中间无需符号、空格和换行隔开）"
        )

        self.assertTrue(has_format_constraint(prompt))


class LlmWikiAuthHeaderTest(unittest.TestCase):
    def test_uses_bearer_token_without_printing_value(self) -> None:
        with patch.dict("os.environ", {"LLM_WIKI_API_TOKEN": "secret-token"}, clear=False):
            headers = build_wiki_headers()

        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Authorization"], "Bearer secret-token")

    def test_omits_authorization_when_token_is_empty(self) -> None:
        with patch.dict("os.environ", {"LLM_WIKI_API_TOKEN": "  "}, clear=False):
            headers = build_wiki_headers()

        self.assertEqual(headers, {"Content-Type": "application/json"})


if __name__ == "__main__":
    unittest.main()
