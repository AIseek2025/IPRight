from __future__ import annotations

import os
import re
from docx import Document
from docx.shared import Pt

from app.services.document.base import WordTemplateBase


def _sanitize_source_line(line: str) -> str:
    def _replace_hex(match: re.Match[str]) -> str:
        value = int(match.group(1), 16)
        if value < 32 and value not in (9, 10, 13):
            return "\uFFFD"
        return match.group(0)

    line = re.sub(r"\\x([0-9A-Fa-f]{2})", _replace_hex, line)
    return "".join(
        ch if (ord(ch) >= 32 or ch in "\t\r\n") else "\uFFFD"
        for ch in line
    )


class SourceCodeBookGenerator(WordTemplateBase):
    LINES_PER_PAGE = 64
    BINARY_EXTENSIONS = {
        ".ttf", ".ttc", ".otf", ".woff", ".woff2",
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        ".pdf", ".doc", ".docx", ".zip", ".gz", ".tar",
        ".ico", ".mp3", ".mp4", ".avi", ".mov",
    }

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
        exclude_globs = code_index.get("exclude_globs", []) or []
        preferred_order = code_index.get("preferred_order", [])

        all_lines: list[str] = []
        files_read = set()

        for pattern in preferred_order:
            matched = self._resolve_pattern(pattern, workspace_path, exclude_globs)
            for fp in matched:
                if fp not in files_read:
                    files_read.add(fp)
                    all_lines.extend(self._read_file(fp, workspace_path))

        for pattern in include_globs:
            matched = self._resolve_pattern(pattern, workspace_path, exclude_globs)
            for fp in matched:
                if fp not in files_read:
                    files_read.add(fp)
                    all_lines.extend(self._read_file(fp, workspace_path))

        return all_lines

    def _resolve_pattern(
        self,
        pattern: str,
        workspace_path: str,
        exclude_globs: list[str] | None = None,
    ) -> list[str]:
        import fnmatch
        import glob

        excludes = list(exclude_globs or [])
        full_pattern = os.path.join(workspace_path, pattern)
        results = []
        for p in glob.glob(full_pattern, recursive=True):
            if not os.path.isfile(p):
                continue
            rel = os.path.relpath(p, workspace_path)
            normalized = rel.replace(os.sep, "/")
            if any(
                fnmatch.fnmatch(normalized, ex) or fnmatch.fnmatch(rel, ex)
                for ex in excludes
            ):
                continue
            results.append(rel)
        return results

    def _read_file(self, rel_path: str, workspace_path: str) -> list[str]:
        full_path = os.path.join(workspace_path, rel_path)
        lines: list[str] = []
        if not os.path.exists(full_path):
            return lines
        lines.append(f"===== FILE: {rel_path} =====")
        if os.path.splitext(rel_path)[1].lower() in self.BINARY_EXTENSIONS:
            lines.append(f"// [跳过二进制文件: {rel_path}]")
            return lines
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    sanitized = _sanitize_source_line(line.rstrip("\n").rstrip("\r"))
                    lines.append(sanitized)
        except Exception:
            lines.append(f"// [无法读取文件: {rel_path}]")
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
                self.add_code_block(line, font_size=7.5)
            if index < len(selected_pages) - 1:
                self.doc.add_page_break()

        return self.doc
