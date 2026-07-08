import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from parsers.hwp_parser import _looks_readable_text, _parse_hwp_binary, _try_rhwp


class TestHwpParserRhwpFallback(unittest.TestCase):
    @patch("parsers.hwp_parser.subprocess.run")
    def test_try_rhwp_uses_node_text_worker(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="문서 test 본문\n", stderr="")

        text = _try_rhwp(Path("/tmp/sample.hwp"))

        self.assertEqual(text, "문서 test 본문")
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "node")
        self.assertTrue(args[1].endswith("backend/workers/hwp_text_extract.mjs"))
        self.assertEqual(args[2], "/tmp/sample.hwp")

    @patch("parsers.hwp_parser._try_pyhwp", return_value="")
    @patch("parsers.hwp_parser._try_rhwp", return_value="이것은 테스트 문서입니다 Test")
    @patch("parsers.hwp_parser._try_olefile", return_value="깨진 ole 텍스트")
    def test_parse_hwp_binary_prefers_rhwp_before_olefile(self, mock_ole, _mock_rhwp, _mock_pyhwp):
        text, meta = _parse_hwp_binary(Path("/tmp/sample.hwp"))

        self.assertIn("테스트 문서", text)
        self.assertEqual(meta["method"], "rhwp")
        mock_ole.assert_not_called()

    def test_readability_filter_rejects_garbled_ole_text(self):
        self.assertFalse(_looks_readable_text("扳恨扔桠慠̀䙦؆䘆䮆㡓ㅷ㠰㢳グꐱ"))
        self.assertTrue(_looks_readable_text("이것은 테스트 문서입니다 Test"))


if __name__ == "__main__":
    unittest.main()
