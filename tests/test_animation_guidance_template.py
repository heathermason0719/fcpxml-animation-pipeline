from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from scripts.intake_project import _is_animation_guidance


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "animation-script-template.docx"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _cell_text(cell: ET.Element) -> str:
    return "".join(node.text or "" for node in cell.findall(".//w:t", NS))


class AnimationGuidanceTemplateTests(unittest.TestCase):
    def test_bundled_template_filename_is_discoverable_as_animation_guidance(self) -> None:
        self.assertTrue(_is_animation_guidance(TEMPLATE))

    def test_bundled_template_preserves_the_optional_eight_column_form_contract(self) -> None:
        self.assertTrue(TEMPLATE.is_file(), "bundled animation guidance template is missing")
        with ZipFile(TEMPLATE) as package:
            document = ET.fromstring(package.read("word/document.xml"))

        tables = document.findall(".//w:tbl", NS)
        self.assertEqual(len(tables), 1)
        rows = tables[0].findall("w:tr", NS)
        self.assertEqual(len(rows), 4)

        expected_headers = [
            "动画项／镜号",
            "对应旁白原句",
            "开始触发词句（留空＝整段）",
            "结束触发词句（留空＝整段）",
            "希望表达的重点／观众感受",
            "必须出现的屏幕文字／内容",
            "可选动画想法／参考",
            "硬性约束／禁止项（可留空）",
        ]
        header_cells = rows[0].findall("w:tc", NS)
        self.assertEqual([_cell_text(cell) for cell in header_cells], expected_headers)
        self.assertIsNotNone(rows[0].find("w:trPr/w:tblHeader", NS))

        for row in rows[1:]:
            cells = row.findall("w:tc", NS)
            self.assertEqual(len(cells), 8)
            self.assertEqual([_cell_text(cell) for cell in cells], [""] * 8)

        page_size = document.find(".//w:sectPr/w:pgSz", NS)
        self.assertIsNotNone(page_size)
        assert page_size is not None
        width = int(page_size.attrib[f"{{{W_NS}}}w"])
        height = int(page_size.attrib[f"{{{W_NS}}}h"])
        self.assertGreater(width, height)

        all_text = "".join(node.text or "" for node in document.findall(".//w:t", NS))
        self.assertNotIn("音乐", all_text)
        self.assertNotIn("音效", all_text)


if __name__ == "__main__":
    unittest.main()
