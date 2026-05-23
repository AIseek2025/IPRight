from __future__ import annotations

import hashlib
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


def _seed_index(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    return int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16) % modulo


def _hex_to_rgb(value: str | None, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) != 6:
        return fallback
    try:
        return tuple(int(raw[idx : idx + 2], 16) for idx in (0, 2, 4))
    except ValueError:
        return fallback


def _mix_rgb(color: tuple[int, int, int], target: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(int(channel + (target[idx] - channel) * ratio) for idx, channel in enumerate(color))


def _short_group_title(group: list[str], fallback: str) -> str:
    labels = [item for item in group if item]
    if not labels:
        return fallback
    if len(labels) == 1:
        return labels[0]
    joined = " / ".join(labels[:2])
    return joined if len(joined) <= 22 else f"{labels[0]}等模块"


def _diagram_palette(profile: dict, product_name: str) -> dict:
    seed = str(profile.get("design_seed") or product_name)
    visual_profile = profile.get("visual_profile") or {}
    fallback_headers = [
        (24, 144, 255),
        (17, 94, 89),
        (124, 58, 237),
        (180, 83, 9),
        (190, 24, 93),
    ]
    fallback_accents = [
        (37, 99, 235),
        (22, 163, 74),
        (124, 58, 237),
        (234, 88, 12),
        (225, 29, 72),
    ]
    header = _hex_to_rgb(visual_profile.get("nav_background"), fallback_headers[_seed_index(f"{seed}|header", len(fallback_headers))])
    accent = _hex_to_rgb(visual_profile.get("accent"), fallback_accents[_seed_index(f"{seed}|accent", len(fallback_accents))])
    strong = _hex_to_rgb(visual_profile.get("strong"), _mix_rgb(accent, (0, 0, 0), 0.2))
    soft = _hex_to_rgb(visual_profile.get("soft"), _mix_rgb(accent, (255, 255, 255), 0.88))
    panel = _hex_to_rgb(visual_profile.get("panel_background"), (255, 255, 255))
    border = _hex_to_rgb(visual_profile.get("panel_border"), _mix_rgb(header, (255, 255, 255), 0.78))
    return {
        "header": header,
        "title_fg": _hex_to_rgb(visual_profile.get("nav_text"), (255, 255, 255)),
        "primary": accent,
        "primary_fill": _mix_rgb(soft, (255, 255, 255), 0.35),
        "secondary": strong,
        "secondary_fill": _mix_rgb(panel, accent, 0.08),
        "accent": _mix_rgb(header, accent, 0.45),
        "accent_fill": _mix_rgb(panel, header, 0.1),
        "text": (34, 34, 34),
        "muted": (90, 90, 90),
        "panel_border": border,
    }


def _diagram_layouts() -> dict[str, dict]:
    return {
        "matrix": {
            "boxes": [
                (120, 98, 1120, 224),
                (70, 288, 560, 476),
                (680, 288, 1170, 476),
                (120, 540, 560, 724),
                (680, 540, 1120, 724),
            ],
            "arrows": [
                (620, 224, 315, 288),
                (620, 224, 925, 288),
                (315, 476, 315, 540),
                (925, 476, 925, 540),
                (560, 382, 680, 382),
            ],
        },
        "ladder": {
            "boxes": [
                (60, 118, 340, 252),
                (410, 92, 1180, 260),
                (60, 336, 430, 548),
                (470, 336, 840, 548),
                (880, 336, 1180, 700),
            ],
            "arrows": [
                (340, 186, 410, 176),
                (545, 260, 245, 336),
                (785, 260, 655, 336),
                (1010, 260, 1030, 336),
                (430, 548, 880, 548),
                (840, 442, 880, 442),
            ],
        },
        "gallery": {
            "boxes": [
                (100, 98, 1140, 214),
                (60, 270, 380, 486),
                (460, 270, 780, 486),
                (860, 270, 1180, 486),
                (190, 560, 1050, 732),
            ],
            "arrows": [
                (300, 214, 220, 270),
                (620, 214, 620, 270),
                (940, 214, 1020, 270),
                (220, 486, 360, 560),
                (620, 486, 620, 560),
                (1020, 486, 880, 560),
            ],
        },
    }


def _draw_box(draw, box, *, title: str, body: str, fill, outline, title_color, body_font, heading_font, body_color):
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=3)
    draw.text((box[0] + 24, box[1] + 22), title, fill=title_color, font=heading_font)
    _draw_wrapped_text(draw, (box[0] + 14, box[1] + 58, box[2] - 14, box[3] - 12), body, body_font, body_color)


def _build_diagram_spec(product_name: str, profile: dict | None = None) -> dict:
    profile = profile or {}
    architecture_style = str((profile.get("project_dna") or {}).get("architecture_style", "")).strip()
    scene = str(profile.get("scene", "")).strip()
    modules = _diagram_modules(profile)
    roles = [str(item).strip() for item in profile.get("user_roles", []) if str(item).strip()]
    core_entities = [str(item).strip() for item in profile.get("core_entities", []) if str(item).strip()]
    module_phrase = "、".join(modules[:4]) or "登录首页、业务模块、统计视图和配置能力"
    seed = str(profile.get("design_seed") or f"{product_name}|{scene}|{architecture_style}")
    palette = _diagram_palette(profile, product_name)
    grouped_modules = [modules[idx : idx + 2] for idx in range(0, min(len(modules), 6), 2)]
    while len(grouped_modules) < 3:
        grouped_modules.append([])
    scene_label = scene or "当前业务协同"
    entity_label = "、".join(core_entities[:3]) or "业务对象、状态结果和审计记录"
    role_label = "、".join(roles[:3]) or "管理员、业务主管、业务专员"

    style_caption = {
        "dispatch_flow": "形成以调度协同和执行闭环为核心的项目专属架构。",
        "risk_grid": "形成以分析评估、规则处置和材料沉淀为核心的项目专属架构。",
        "control_tower": "形成以监测总览、任务协同和结果留痕为核心的项目专属架构。",
    }.get(architecture_style, "形成以页面处理、业务协同和交付发布为核心的项目专属架构。")

    contents = [
        {
            "title": "访问与任务入口",
            "body": f"承载{product_name}的登录入口、首页导航和任务工作入口，面向{role_label}等核心角色组织访问路径。",
            "kind": "primary",
        },
        {
            "title": _short_group_title(grouped_modules[0], "首页与核心总览"),
            "body": f"围绕{scene_label}组织首页与核心模块入口，重点承载{_short_group_title(grouped_modules[0], module_phrase)}相关视图与工作动作。",
            "kind": "primary",
        },
        {
            "title": _short_group_title(grouped_modules[1], "业务处理与规则协同"),
            "body": f"负责处理{_short_group_title(grouped_modules[1], module_phrase)}等业务场景，承接状态流转、结果回写和规则编排。",
            "kind": "secondary",
        },
        {
            "title": _short_group_title(grouped_modules[2], "数据与结果沉淀"),
            "body": f"围绕{entity_label}等核心对象组织数据口径、记录留痕和结果沉淀，保证页面显示与导出材料一致。",
            "kind": "accent",
        },
        {
            "title": "交付与发布支撑",
            "body": "负责截图采集、说明书编排、源码文档生成、导出打包和发布留痕，使页面、文档和下载材料保持一一对应。",
            "kind": "accent",
        },
    ]

    layouts = _diagram_layouts()
    if architecture_style == "dispatch_flow":
        layout_key = "ladder"
    elif architecture_style == "risk_grid":
        layout_key = "matrix"
    else:
        layout_key = list(layouts.keys())[_seed_index(seed, len(layouts))]
    layout = layouts[layout_key]

    return {
        "palette": palette,
        "boxes": [
            {
                "box": layout["boxes"][idx],
                "title": contents[idx]["title"],
                "body": contents[idx]["body"],
                "kind": contents[idx]["kind"],
            }
            for idx in range(len(contents))
        ],
        "arrows": layout["arrows"],
        "caption": f"图1：{product_name}{style_caption}",
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
