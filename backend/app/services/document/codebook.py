from __future__ import annotations

import os
from docx import Document
from docx.shared import Pt

from app.services.document.base import WordTemplateBase


class SourceCodeBookGenerator(WordTemplateBase):
    LINES_PER_PAGE = 55

    def __init__(
        self,
        product_name: str,
        version: str,
        doc: Document | None = None,
    ):
        super().__init__(doc)
        self.product_name = product_name
        self.version = version

    def _read_code_files(self, code_index: dict, workspace_path: str) -> list[str]:
        include_globs = code_index.get("include_globs", [])
        preferred_order = code_index.get("preferred_order", [])

        all_lines: list[str] = []
        files_read = set()

        for pattern in preferred_order:
            matched = self._resolve_pattern(pattern, workspace_path, include_globs)
            for fp in matched:
                if fp not in files_read:
                    files_read.add(fp)
                    all_lines.extend(self._read_file(fp, workspace_path))

        for pattern in include_globs:
            matched = self._resolve_pattern(pattern, workspace_path, include_globs)
            for fp in matched:
                if fp not in files_read:
                    files_read.add(fp)
                    all_lines.extend(self._read_file(fp, workspace_path))

        return all_lines

    def _resolve_pattern(self, pattern: str, workspace_path: str, includes: list[str]) -> list[str]:
        import fnmatch
        import glob

        full_pattern = os.path.join(workspace_path, pattern)
        results = []
        for p in glob.glob(full_pattern, recursive=True):
            if os.path.isfile(p):
                results.append(os.path.relpath(p, workspace_path))
        return results

    def _read_file(self, rel_path: str, workspace_path: str) -> list[str]:
        full_path = os.path.join(workspace_path, rel_path)
        lines: list[str] = []
        if not os.path.exists(full_path):
            return lines
        lines.append(f"===== FILE: {rel_path} =====")
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    lines.append(line.rstrip("\n").rstrip("\r"))
        except Exception:
            lines.append(f"// [无法读取文件: {rel_path}]")
        lines.append("")
        return lines

    def _paginate(self, all_lines: list[str]) -> list[list[str]]:
        pages: list[list[str]] = []
        current_page: list[str] = []
        for line in all_lines:
            current_page.append(line)
            if len(current_page) >= self.LINES_PER_PAGE:
                pages.append(current_page)
                current_page = []
        if current_page:
            pages.append(current_page)
        return pages

    def generate(self, code_index: dict, workspace_path: str) -> Document:
        header_text = f"{self.product_name}{self.version} 源代码"
        self.set_header(header_text)
        self.add_page_number()

        all_lines = self._read_code_files(code_index, workspace_path)
        if not all_lines:
            self.add_paragraph("（未找到源代码文件）")
            return self.doc

        selected_pages = self._paginate(all_lines)

        for index, page_lines in enumerate(selected_pages):
            for line in page_lines:
                self.add_code_block(line, font_size=9)
            if index < len(selected_pages) - 1:
                self.doc.add_page_break()

        return self.doc
