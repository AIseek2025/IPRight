from __future__ import annotations

import re

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml


class WordTemplateBase:
    def __init__(self, doc: Document | None = None):
        self.doc = doc or Document()
        self._setup_page()

    def _setup_page(self) -> None:
        for section in self.doc.sections:
            section.page_width = Cm(21.0)
            section.page_height = Cm(29.7)
            section.top_margin = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin = Cm(2.0)
            section.right_margin = Cm(2.0)
        self._setup_styles()

    def _setup_styles(self) -> None:
        normal = self.doc.styles["Normal"]
        normal.font.name = "宋体"
        normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        normal.font.size = Pt(10.5)

    def _apply_run_font(
        self,
        run,
        *,
        font_name: str = "宋体",
        font_size: int | float = 10.5,
        bold: bool = False,
        italic: bool = False,
    ) -> None:
        run.font.name = font_name
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
        run.font.size = Pt(font_size)
        run.bold = bold
        run.italic = italic

    def _normalize_doc_text(self, text: str) -> str:
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", text)
        text = re.sub(r"([\u4e00-\u9fff])\s+(V\d)", r"\1\2", text)
        text = re.sub(r"(V\d(?:\.\d+)*)\s+([\u4e00-\u9fff])", r"\1\2", text)
        text = re.sub(r"([，。；：！？、】【（）])\s+([\u4e00-\u9fff])", r"\1\2", text)
        text = re.sub(r"([\u4e00-\u9fff])\s+([，。；：！？、】【（）])", r"\1\2", text)
        return text

    def set_header(self, text: str) -> None:
        text = self._normalize_doc_text(text)
        for section in self.doc.sections:
            header = section.header
            if not header.paragraphs:
                header.add_paragraph()
            header.paragraphs[0].text = text
            header.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in header.paragraphs[0].runs:
                self._apply_run_font(run, font_name="宋体", font_size=9)

    def add_page_number(self) -> None:
        for section in self.doc.sections:
            footer = section.footer
            footer.is_linked_to_previous = False
            p = footer.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = p.add_run()
            fld_char1 = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>')
            run._r.append(fld_char1)
            instr = parse_xml(f'<w:instrText {nsdecls("w")} xml:space="preserve"> PAGE </w:instrText>')
            run._r.append(instr)
            fld_char2 = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>')
            run._r.append(fld_char2)
            self._apply_run_font(run, font_name="宋体", font_size=9)

    def add_title(self, text: str, level: int = 0) -> None:
        text = self._normalize_doc_text(text)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 0 else WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(text)
        if level == 0:
            self._apply_run_font(run, font_name="黑体", font_size=18, bold=True)
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(18)
        elif level == 1:
            self._apply_run_font(run, font_name="黑体", font_size=15, bold=True)
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(10)
        else:
            self._apply_run_font(run, font_name="黑体", font_size=12, bold=True)
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.2

    def add_paragraph(self, text: str, bold: bool = False, font_size: int = 10, font_name: str = "宋体") -> None:
        text = self._normalize_doc_text(text)
        p = self.doc.add_paragraph()
        run = p.add_run(text)
        self._apply_run_font(run, font_name=font_name, font_size=font_size, bold=bold)
        pf = p.paragraph_format
        pf.first_line_indent = Cm(0.74)
        pf.space_before = Pt(0)
        pf.space_after = Pt(6)
        pf.line_spacing = 1.35
        return p

    def add_image(self, image_path: str, width_inches: float = 5.5) -> None:
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(image_path, width=Inches(width_inches))

    def add_caption(self, text: str) -> None:
        text = self._normalize_doc_text(text)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        self._apply_run_font(run, font_name="宋体", font_size=9, italic=False)
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(8)
        p.paragraph_format.line_spacing = 1.1

    def add_code_block(self, code_text: str, font_size: int = 10) -> None:
        p = self.doc.add_paragraph()
        run = p.add_run(code_text)
        self._apply_run_font(run, font_name="Consolas", font_size=font_size)
        pf = p.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.first_line_indent = Cm(0)
        pf.line_spacing = Pt(12)

    def save(self, path: str) -> None:
        self.doc.save(path)
