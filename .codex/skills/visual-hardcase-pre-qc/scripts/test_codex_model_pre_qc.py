#!/usr/bin/env python3
"""Focused tests for the Codex-backed pre-QC worker."""

from __future__ import annotations

import argparse
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_model_pre_qc import (
    build_prompt,
    codex_new_command,
    codex_resume_command,
    extract_image_tokens,
    field_slug,
    format_model_result,
    parse_json_text,
    resolve_codex_bin,
    source_requirement_summary,
    summarize_image_attachments,
)
from watch_newcomer_sheet import (
    is_repair_done,
    row_allows_result_overwrite,
    row_needs_pre_qc,
    write_pre_qc_result,
)


class ParseJsonTextTest(unittest.TestCase):
    def test_parses_plain_json(self) -> None:
        data = parse_json_text('{"rows": [], "batchSummary": {"total": 0}}')

        self.assertEqual(data["rows"], [])

    def test_parses_fenced_json(self) -> None:
        data = parse_json_text('```json\n{"rows": [{"rowNumber": 1}]}\n```')

        self.assertEqual(data["rows"][0]["rowNumber"], 1)


class FormatModelResultTest(unittest.TestCase):
    def test_formats_codex_model_result_and_preserves_detected_images(self) -> None:
        result = {
            "recommendation": "退回修改",
            "riskLevel": "高",
            "score": 72,
            "blockers": [],
            "issues": ["prompt存在歧义"],
            "suggestions": ["补充输出格式限定"],
            "badCaseCategory": "prompt歧义",
            "evidence": ["v3题型总览与准入标准 (wiki/concepts/v3题型总览与准入标准.md)"],
            "humanReview": ["需要人工看图确认答案是否唯一"],
            "reasoningSummary": "题目方向基本可行，但格式约束不足。",
        }
        mapped = {
            "图片文件夹或图片链接": "飞书单元格图片 token:abc",
            "answer": "A",
        }

        text = format_model_result(result, mapped, "session-1")

        self.assertNotIn("结论：", text)
        self.assertNotIn("AI预质检", text)
        self.assertNotIn("生成时间", text)
        self.assertNotIn("质检会话", text)
        self.assertNotIn("图片材料", text)
        self.assertNotIn("图片字段", text)
        self.assertIn("人工复核：需要人工看图确认答案是否唯一", text)

    def test_formats_source_requirement_and_demotes_pass_when_required_source_missing(self) -> None:
        result = {
            "recommendation": "通过",
            "riskLevel": "低",
            "score": 93,
            "blockers": [],
            "issues": [],
            "suggestions": [],
            "badCaseCategory": "未命中",
            "evidence": [],
            "humanReview": [],
            "reasoningSummary": "",
        }

        text = format_model_result(
            result,
            {"信源链接或标注图路径": ""},
            "",
            source_requirement={
                "taskType": "推理游戏-齿轮",
                "requiresSource": "是",
                "sourceProvided": False,
            },
        )

        self.assertNotIn("结论：", text)
        self.assertIn("信源要求：推理游戏-齿轮：需要信源；当前：未填写；依据：知识库", text)
        self.assertIn("知识库标记该题型需要信源", text)

    def test_hides_internal_mapped_key_from_user_facing_output(self) -> None:
        result = {
            "recommendation": "退回修改",
            "riskLevel": "中",
            "score": 80,
            "blockers": ['mapped 中“答案是否唯一”为“否”。'],
            "issues": ["payload.rows[].mapped 中存在字段未填"],
            "suggestions": ["检查 mapped 中“prompt”的格式限定"],
            "badCaseCategory": "答案唯一性不足",
            "evidence": [],
            "humanReview": ["raw 中“answer”需要人工确认"],
            "reasoningSummary": "mapped 中“题型分类”为“多图变化”。",
        }

        text = format_model_result(result, {}, "session-1")

        self.assertNotIn("mapped", text)
        self.assertNotIn("payload.rows[]", text)
        self.assertNotIn("raw", text)
        self.assertIn("S列【答案是否唯一】为“否”", text)
        self.assertIn("【prompt】的格式限定", text)
        self.assertIn("【answer】需要人工确认", text)


class BuildPromptTest(unittest.TestCase):
    def test_prompt_requires_pre_qc_skill_and_llm_wiki_search(self) -> None:
        args = argparse.Namespace(
            job_id="job-1",
            url="https://example.test/sheet",
            sheet_id="sheet1",
            result_field="预质检",
            require_model_validation=False,
        )
        rows = [
            {
                "rowNumber": 1,
                "mapped": {"题型分类": "读示数"},
                "sourceRequirement": {"requiresSource": "否"},
                "wikiEvidence": [],
                "_allowResultOverwrite": True,
                "_recheckReason": "是否返修完成=是",
            }
        ]

        prompt = build_prompt(args, rows)

        self.assertIn("$visual-hardcase-pre-qc", prompt)
        self.assertIn("visual_hardcase_guard.py", prompt)
        self.assertIn("wiki_search.py", prompt)
        self.assertIn("wikiEvidence 是预检索结果", prompt)
        self.assertNotIn("sourceRequirement", prompt)
        self.assertNotIn("_allowResultOverwrite", prompt)
        self.assertNotIn("_recheckReason", prompt)
        self.assertNotIn("jcnsrten12zb.feishu.cn", prompt)


class ImageTokenTest(unittest.TestCase):
    def test_extracts_unique_feishu_image_tokens(self) -> None:
        tokens = extract_image_tokens(
            {
                "图片1": "飞书单元格图片 token:tok_a (640x480)",
                "answer": "飞书单元格图片 token:tok_b\n飞书单元格图片 token:tok_a",
            }
        )

        self.assertEqual(tokens, ["tok_a", "tok_b"])

    def test_summarizes_image_attachment_sources(self) -> None:
        summary = summarize_image_attachments(
            [
                {"source": "图片1", "status": "attached"},
                {"source": "图片1", "status": "attached"},
                {"source": "answer", "status": "download_failed"},
            ]
        )

        self.assertEqual(summary, "图片1：已传给Codex2张；answer：下载失败1张")

    def test_field_slug_preserves_semantic_field_names(self) -> None:
        self.assertEqual(field_slug("图片3"), "image3")
        self.assertEqual(field_slug("answer"), "answer")


class SourceRequirementTest(unittest.TestCase):
    def test_source_requirement_summary(self) -> None:
        self.assertEqual(
            source_requirement_summary({
                "taskType": "ocr-票据",
                "requiresSource": "否",
                "sourceProvided": False,
            }),
            "ocr-票据：不需要信源；当前：未填写；依据：知识库",
        )


class RepairRecheckTest(unittest.TestCase):
    def args(self, **overrides: object) -> argparse.Namespace:
        base = {
            "force": False,
            "no_repair_recheck": False,
            "repair_done_field": "是否返修完成",
            "repair_done_value": "是",
            "result_field": "预质检",
            "url": "https://example.test/sheet",
            "sheet_id": "sheet1",
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    @patch("watch_newcomer_sheet.read_existing_result", return_value="旧结果")
    def test_repaired_row_with_existing_result_needs_recheck(self, _read_existing: object) -> None:
        row = {"_row_number": "100", "是否返修完成": "是"}
        args = self.args()

        self.assertTrue(is_repair_done(row, args))
        self.assertTrue(row_needs_pre_qc(args, "W", row))
        self.assertTrue(row_allows_result_overwrite(args, row))

    @patch("watch_newcomer_sheet.read_existing_result", return_value="旧结果")
    def test_existing_result_without_repair_done_is_skipped(self, _read_existing: object) -> None:
        row = {"_row_number": "100", "是否返修完成": "否"}
        args = self.args()

        self.assertFalse(row_needs_pre_qc(args, "W", row))
        self.assertFalse(row_allows_result_overwrite(args, row))

    @patch("watch_newcomer_sheet.read_existing_result", return_value="")
    def test_empty_result_still_runs(self, _read_existing: object) -> None:
        row = {"_row_number": "100", "是否返修完成": ""}

        self.assertTrue(row_needs_pre_qc(self.args(), "W", row))

    @patch("watch_newcomer_sheet.run_lark_cli")
    @patch("watch_newcomer_sheet.read_existing_result", return_value="旧结果")
    def test_row_level_overwrite_writes_without_global_force(
        self,
        read_existing: object,
        run_lark_cli: object,
    ) -> None:
        ok = write_pre_qc_result(self.args(), "W", 100, "新结果", allow_overwrite=True)

        self.assertTrue(ok)
        read_existing.assert_not_called()
        cli_args = run_lark_cli.call_args.args[0]
        self.assertIn("--allow-overwrite=true", cli_args)


class CodexCommandTest(unittest.TestCase):
    def test_builds_new_worker_session_command(self) -> None:
        args = argparse.Namespace(
            codex_bin="codex",
            codex_model="gpt-5.5",
            schema=str(Path("schema.json").resolve()),
        )

        cmd = codex_new_command(args, Path("out.json"))

        self.assertTrue(Path(cmd[0]).name.startswith("codex"))
        self.assertEqual(cmd[1], "exec")
        self.assertIn("--json", cmd)
        self.assertIn("--output-schema", cmd)
        self.assertIn("--output-last-message", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("gpt-5.5", cmd)

    def test_builds_new_worker_session_command_with_images(self) -> None:
        args = argparse.Namespace(
            codex_bin="codex",
            codex_model="gpt-5.5",
            schema=str(Path("schema.json").resolve()),
        )

        cmd = codex_new_command(args, Path("out.json"), [Path("row-1.png"), Path("row-2.png")])

        self.assertEqual(cmd.count("--image"), 2)
        self.assertIn("row-1.png", cmd)
        self.assertIn("row-2.png", cmd)

    def test_builds_resume_worker_session_command(self) -> None:
        args = argparse.Namespace(
            codex_bin="codex",
            codex_model="gpt-5.5",
            schema=str(Path("schema.json").resolve()),
        )

        cmd = codex_resume_command(args, "session-123", Path("out.json"))

        self.assertTrue(Path(cmd[0]).name.startswith("codex"))
        self.assertEqual(cmd[1:3], ["exec", "resume"])
        self.assertIn("session-123", cmd)
        self.assertIn("--output-schema", cmd)

    @unittest.skipUnless(os.name == "nt", "Windows-specific command resolution")
    def test_resolves_codex_to_cmd_on_windows(self) -> None:
        with patch("shutil.which", side_effect=lambda name: f"C:/bin/{name}" if name == "codex.cmd" else None):
            self.assertEqual(resolve_codex_bin("codex"), "C:/bin/codex.cmd")


if __name__ == "__main__":
    unittest.main()
