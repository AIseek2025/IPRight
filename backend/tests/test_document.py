from __future__ import annotations

import json
import os
import tempfile

from app.services.document.manual import SoftwareManualGenerator
from app.services.document.codebook import SourceCodeBookGenerator


def test_manual_can_generate():
    gen = SoftwareManualGenerator(product_name="TestApp", version="V1.0")
    gen.generate_full(
        prd_summary={"core_modules": ["A", "B"]},
        screenshots_meta=[],
    )
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        gen.save(f.name)
        assert os.path.getsize(f.name) > 0
        os.unlink(f.name)


def test_manual_has_header():
    gen = SoftwareManualGenerator(product_name="TestApp", version="V1.0")
    gen.generate_full()
    for section in gen.doc.sections:
        assert section.header.paragraphs
        text = section.header.paragraphs[0].text
        assert "TestApp" in text


def test_manual_excludes_removed_sections_and_text():
    gen = SoftwareManualGenerator(product_name="TestApp", version="V1.0")
    gen.generate_full(
        screenshots_meta=[{
            "page_title": "登录页",
            "caption": "图1 登录页",
            "image_path": "",
            "elements": ["TestApp V1.0", "👥 用户管理"],
        }],
    )
    joined = "\n".join(p.text for p in gen.doc.paragraphs)
    assert "文档中的截图均来自软件真实运行界面" not in joined
    assert "开发设计流程" not in joined
    assert "开发设计流程图" not in joined
    assert "开发语言说明" in joined
    assert "技术选型说明" in joined
    assert "图1：TestApp系统架构图" not in joined
    assert "TestApp V1.0" in joined
    assert "👥 用户管理" not in joined


def test_manual_normalizes_spacing_and_ui_symbols():
    gen = SoftwareManualGenerator(product_name="智慧园区管理平台", version="V1.0")
    gen.generate_full(
        screenshots_meta=[{
            "page_title": "用户管理",
            "caption": "图1 用户管理",
            "image_path": "",
            "elements": ["智慧园区管理平台 V1.0", "👥 用户管理"],
        }],
    )
    joined = "\n".join(p.text for p in gen.doc.paragraphs)
    assert "智慧园区管理平台 面向企事业单位的信息化管理场景" not in joined
    assert "智慧园区管理平台 采用浏览器访问的软件架构" not in joined
    assert "智慧园区管理平台面向企事业单位的信息化管理场景" in joined
    assert "智慧园区管理平台采用浏览器访问的软件架构" in joined
    assert "本页面关键可见元素包括：智慧园区管理平台V1.0、用户管理。" in joined


def test_codebook_empty_workspace():
    gen = SourceCodeBookGenerator(product_name="TestApp", version="V1.0")
    with tempfile.TemporaryDirectory() as tmpdir:
        code_index = {
            "include_globs": ["**/*.py"],
            "exclude_globs": [],
            "preferred_order": [],
        }
        gen.generate(code_index, tmpdir)
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            gen.save(f.name)
            assert os.path.getsize(f.name) > 0
            os.unlink(f.name)


def test_codebook_pagination():
    gen = SourceCodeBookGenerator(product_name="TestApp", version="V1.0")
    lines = ["line " + str(i) for i in range(200)]
    pages = gen._paginate(lines)
    assert len(pages) > 0
    for page in pages:
        assert len(page) <= gen.LINES_PER_PAGE


def test_codebook_generate_full_document():
    gen = SourceCodeBookGenerator(product_name="TestApp", version="V1.0")
    with tempfile.TemporaryDirectory() as tmpdir:
        code_index = {
            "include_globs": ["**/*.py"],
            "exclude_globs": [],
            "preferred_order": [],
        }
        sample = os.path.join(tmpdir, "a.py")
        with open(sample, "w", encoding="utf-8") as handle:
            for i in range(4000):
                handle.write(f"print({i})\n")
        gen.generate(code_index, tmpdir)
        assert len(gen.doc.paragraphs) > 0
