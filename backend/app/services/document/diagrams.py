from __future__ import annotations

import os
from pathlib import Path


def _resolve_cjk_font_path() -> str | None:
    repo_root = Path(__file__).resolve().parents[4]
    candidates = [
        os.environ.get("IPRIGHT_CJK_FONT", ""),
        str(repo_root / "assets" / "fonts" / "IPRightCJK.ttf"),
        "/opt/ipright/assets/fonts/IPRightCJK.ttf",
        str(repo_root / "shared" / "workspace" / "fonts" / "IPRightCJK.ttf"),
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti SC.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]
    for font_path in candidates:
        if os.path.exists(font_path):
            return font_path
    return None


def _load_cjk_font(size: int, font_path: str):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        fallback_path = _resolve_cjk_font_path()
        if fallback_path and fallback_path != font_path:
            try:
                return ImageFont.truetype(fallback_path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap_text_lines(draw, max_width: int, text: str, font) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        trial = current + ch
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def _measure_lines(draw, lines: list[str], font, line_spacing: int) -> tuple[int, int]:
    max_width = 0
    total_height = 0
    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        max_width = max(max_width, bbox[2] - bbox[0])
        total_height += bbox[3] - bbox[1]
        if index < len(lines) - 1:
            total_height += line_spacing
    return max_width, total_height


def _draw_wrapped_text(draw, box, text: str, font, fill, line_spacing: int = 6, min_font_size: int = 11):
    x1, y1, x2, y2 = box
    max_width = x2 - x1 - 16
    max_height = y2 - y1 - 20
    size = getattr(font, "size", 16)
    lines = _wrap_text_lines(draw, max_width, text, font)
    _, total_height = _measure_lines(draw, lines, font, line_spacing)

    while total_height > max_height and size > min_font_size:
        size -= 1
        font_path = _resolve_cjk_font_path()
        if font_path:
            font = _load_cjk_font(size, font_path)
        lines = _wrap_text_lines(draw, max_width, text, font)
        _, total_height = _measure_lines(draw, lines, font, line_spacing)

    y = y1 + 10
    for line in lines:
        draw.text((x1 + 8, y), line, fill=fill, font=font)
        bbox = draw.textbbox((0, 0), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing


def _diagram_modules(profile: dict | None) -> list[str]:
    return [str(module.get("title", "")).strip() for module in (profile or {}).get("modules", []) if str(module.get("title", "")).strip()]


def _draw_box(draw, box, *, title: str, body: str, fill, outline, title_color, body_font, heading_font, body_color):
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=3)
    draw.text((box[0] + 24, box[1] + 22), title, fill=title_color, font=heading_font)
    _draw_wrapped_text(draw, (box[0] + 14, box[1] + 58, box[2] - 14, box[3] - 12), body, body_font, body_color)


def _build_diagram_spec(product_name: str, profile: dict | None = None) -> dict:
    profile = profile or {}
    preset_key = str(profile.get("preset_key", "")).strip()
    architecture_style = str((profile.get("project_dna") or {}).get("architecture_style", "")).strip()
    scene = str(profile.get("scene", "")).strip()
    modules = _diagram_modules(profile)
    module_phrase = "、".join(modules[:4]) or "登录首页、业务模块、统计视图和配置能力"

    if architecture_style == "dispatch_flow" or preset_key == "logistics":
        return {
            "palette": {
                "header": (12, 74, 110),
                "title_fg": (255, 255, 255),
                "primary": (15, 118, 110),
                "primary_fill": (236, 254, 255),
                "secondary": (217, 119, 6),
                "secondary_fill": (255, 247, 237),
                "accent": (55, 65, 81),
                "accent_fill": (243, 244, 246),
                "text": (34, 34, 34),
                "muted": (90, 90, 90),
            },
            "boxes": [
                {"box": (60, 118, 320, 248), "title": "业务接入层", "body": f"承载{product_name}的登录入口、调度首页和岗位导航，面向调度主管、车队专员与客服协同员。", "kind": "primary"},
                {"box": (390, 92, 1180, 288), "title": "调度驾驶舱", "body": f"围绕{scene or '运单编排与时效协同'}组织首页与核心模块，重点承载{module_phrase}等页面视图，并同步显示在途状态、异常提醒和待办任务。", "kind": "primary"},
                {"box": (60, 350, 420, 560), "title": "运力协同层", "body": "用于维护车辆、司机、可用运力和调度任务分配结果，支撑派车、改派、回场和运力回收。", "kind": "secondary"},
                {"box": (450, 350, 800, 560), "title": "线路监测层", "body": "用于汇总线路节点、在途轨迹、拥堵状态和绕行方案，为时效预测和异常处置提供依据。", "kind": "secondary"},
                {"box": (830, 350, 1180, 560), "title": "仓配与签收层", "body": "用于处理分拨协同、签收回单、影像归档和客户反馈回写，保证仓配节点与正式材料同步。", "kind": "accent"},
                {"box": (220, 626, 1020, 760), "title": "支撑服务层", "body": "负责截图采集、说明书编排、异常通知、导出打包与发布留痕，确保物流项目的页面结果、回单材料与交付文件保持一致。", "kind": "accent"},
            ],
            "arrows": [
                (320, 182, 390, 182),
                (545, 288, 255, 350),
                (785, 288, 625, 350),
                (1005, 288, 1005, 350),
                (250, 560, 360, 626),
                (625, 560, 625, 626),
                (1005, 560, 880, 626),
            ],
            "caption": f"图1：{product_name}围绕运单调度、运力协同、线路监测与签收回单形成闭环架构。",
        }

    if architecture_style == "risk_grid" or preset_key == "supply_chain_finance":
        return {
            "palette": {
                "header": (30, 64, 175),
                "title_fg": (255, 255, 255),
                "primary": (37, 99, 235),
                "primary_fill": (239, 246, 255),
                "secondary": (147, 51, 234),
                "secondary_fill": (245, 243, 255),
                "accent": (217, 119, 6),
                "accent_fill": (255, 247, 237),
                "text": (34, 34, 34),
                "muted": (90, 90, 90),
            },
            "boxes": [
                {"box": (140, 108, 1100, 232), "title": "接入与主体层", "body": f"承载{product_name}的登录入口、核心企业看板和授信主体检索，面向授信分析师、风控经理和资金运营专员。", "kind": "primary"},
                {"box": (70, 290, 560, 470), "title": "融资分析工作台", "body": f"围绕{scene or '授信分析与融资监控'}组织{module_phrase}等核心视图，集中处理融资申请、尽调意见和审批节点。", "kind": "secondary"},
                {"box": (680, 290, 1170, 470), "title": "风险监测与授信决策层", "body": "用于监控资金敞口、授信额度占用、预警等级与责任归属，支撑授信策略调整和风险处置闭环。", "kind": "secondary"},
                {"box": (70, 536, 560, 722), "title": "贸易背景与凭证层", "body": "用于核验订单、合同、发票、影像与补件状态，保证融资材料真实性、单据完备度和审计可追溯性。", "kind": "accent"},
                {"box": (680, 536, 1170, 722), "title": "资金与交付支撑层", "body": "负责截图采集、说明书生成、预警通知、导出发布与留痕归档，保证分析平台页面结果与正式材料保持一致。", "kind": "accent"},
            ],
            "arrows": [
                (620, 232, 315, 290),
                (620, 232, 925, 290),
                (315, 470, 315, 536),
                (925, 470, 925, 536),
                (560, 380, 680, 380),
            ],
            "caption": f"图1：{product_name}围绕授信主体、融资分析、风险监测与贸易背景核验形成项目专属架构。",
        }

    return {
        "palette": {
            "header": (24, 144, 255),
            "title_fg": (255, 255, 255),
            "primary": (24, 144, 255),
            "primary_fill": (233, 246, 255),
            "secondary": (82, 196, 26),
            "secondary_fill": (246, 255, 237),
            "accent": (250, 173, 20),
            "accent_fill": (255, 247, 230),
            "text": (34, 34, 34),
            "muted": (102, 102, 102),
        },
        "boxes": [
            {"box": (60, 120, 300, 245), "title": "用户访问层", "body": f"承载{product_name}的登录入口、首页导航和任务级业务入口，面向当前项目的核心岗位角色。", "kind": "primary"},
            {"box": (345, 100, 735, 305), "title": "页面展示层", "body": f"负责{module_phrase}等项目专属页面展示，依据当前任务主题生成统计卡片、筛选区、表格字段和说明板块。", "kind": "primary"},
            {"box": (790, 100, 1180, 325), "title": "业务处理层", "body": f"围绕{scene or '业务协同'}执行任务处理、状态流转、结果回写和服务编排，是当前产品功能闭环的核心区域。", "kind": "secondary"},
            {"box": (345, 390, 735, 605), "title": "数据组织层", "body": "用于保存页面业务数据、截图结果、导出记录和系统配置，保证不同角色在统一口径下查看与处理数据。", "kind": "accent"},
            {"box": (790, 390, 1180, 620), "title": "交付支撑层", "body": "负责截图采集、说明书编排、导出打包和交付发布，使项目页面、文档和下载材料形成一一对应关系。", "kind": "accent"},
        ],
        "arrows": [
            (300, 180, 345, 180),
            (735, 200, 790, 200),
            (880, 325, 650, 390),
            (1010, 325, 950, 390),
            (790, 555, 735, 555),
        ],
        "caption": f"图1：{product_name}围绕页面展示、业务处理、数据组织与交付支撑形成项目专属架构。",
    }


def generate_system_architecture_diagram(output_path: str, product_name: str, profile: dict | None = None) -> str:
    """
    Generate a system architecture diagram as a PNG image.
    Uses PIL/Pillow to draw boxes and arrows showing the system architecture.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise RuntimeError("Pillow 未安装，无法生成系统架构图图片")

    font_path = _resolve_cjk_font_path()
    if not font_path:
        raise RuntimeError("未找到可用的中文字体文件，无法生成系统架构图图片")

    img = Image.new("RGB", (1240, 820), "white")
    draw = ImageDraw.Draw(img)

    spec = _build_diagram_spec(product_name, profile)
    palette = spec["palette"]
    black = palette["text"]
    gray = palette["muted"]
    white = palette["title_fg"]

    font_title = _load_cjk_font(28, font_path)
    font_heading = _load_cjk_font(20, font_path)
    font_body = _load_cjk_font(15, font_path)
    font_small = _load_cjk_font(14, font_path)

    draw.rectangle([0, 0, 1240, 70], fill=palette["header"])
    title_text = f"{product_name}系统架构图"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_x = (1240 - (title_bbox[2] - title_bbox[0])) // 2
    draw.text((title_x, 18), title_text, fill=white, font=font_title)
    fill_map = {
        "primary": (palette["primary_fill"], palette["primary"], palette["primary"]),
        "secondary": (palette["secondary_fill"], palette["secondary"], palette["secondary"]),
        "accent": (palette["accent_fill"], palette["accent"], palette["accent"]),
    }
    for item in spec["boxes"]:
        fill, outline, title_color = fill_map[item["kind"]]
        _draw_box(
            draw,
            item["box"],
            title=item["title"],
            body=item["body"],
            fill=fill,
            outline=outline,
            title_color=title_color,
            body_font=font_body,
            heading_font=font_heading,
            body_color=black,
        )

    for x1, y1, x2, y2 in spec["arrows"]:
        _draw_arrow(draw, x1, y1, x2, y2, color=gray)

    draw.text((120, 768), spec["caption"], fill=gray, font=font_small)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def generate_workflow_diagram(output_path: str, product_name: str) -> str:
    """Deprecated: workflow diagrams are no longer part of the software manual."""
    return ""


def _draw_arrow(draw, x1, y1, x2, y2, color=(0, 0, 0)):
    draw.line([(x1, y1), (x2, y2)], fill=color, width=2)
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    length = 8
    ax1 = x2 - length * math.cos(angle - 0.4)
    ay1 = y2 - length * math.sin(angle - 0.4)
    ax2 = x2 - length * math.cos(angle + 0.4)
    ay2 = y2 - length * math.sin(angle + 0.4)
    draw.polygon([(x2, y2), (ax1, ay1), (ax2, ay2)], fill=color)
