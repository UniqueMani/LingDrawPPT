import unittest

from backend.services.chart_code_llm import _extracted_to_mermaid, validate_mermaid


class MermaidGenerationTest(unittest.TestCase):
    def test_trend_xychart_quotes_chinese_months_and_uses_line(self):
        src = _extracted_to_mermaid(
            "trend",
            "trend_line",
            {"x": ["1月", "2月", "3月"], "y": [2.1, 2.5, 2.9]},
            "月度活跃用户波动",
        )

        self.assertIn('title "月度活跃用户波动"', src)
        self.assertIn('x-axis ["1月", "2月", "3月"]', src)
        self.assertIn("line [2.1, 2.5, 2.9]", src)
        self.assertEqual(validate_mermaid(src), [])

    def test_flowchart_sanitizes_node_text(self):
        src = _extracted_to_mermaid(
            "process",
            "process_flow",
            {"steps": ['识别[语义]', '生成"图表"', "人工复核"]},
            "流程",
        )

        self.assertIn("S0[识别(语义)]", src)
        self.assertIn("S1[生成'图表']", src)
        self.assertEqual(validate_mermaid(src), [])

    def test_invalid_xychart_is_error(self):
        src = "xychart-beta\n    title 月度活跃用户波动\n    x-axis 月份 [“1月”, “2月”]\n    line [1, 2]"
        issues = validate_mermaid(src)

        self.assertTrue(any(sev == "error" for sev, _message in issues))


if __name__ == "__main__":
    unittest.main()
