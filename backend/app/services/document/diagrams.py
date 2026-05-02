from __future__ import annotations

import os
from pathlib import Path


def _load_cjk_font(size: int):
    from PIL import ImageFont

    candidates = [
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
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
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
        font = _load_cjk_font(size)
        lines = _wrap_text_lines(draw, max_width, text, font)
        _, total_height = _measure_lines(draw, lines, font, line_spacing)

    y = y1 + 10
    for line in lines:
        draw.text((x1 + 8, y), line, fill=fill, font=font)
        bbox = draw.textbbox((0, 0), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing


def generate_system_architecture_diagram(output_path: str, product_name: str) -> str:
    """
    Generate a system architecture diagram as a PNG image.
    Uses PIL/Pillow to draw boxes and arrows showing the system architecture.
    Falls back to a text description if PIL is not available.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return _generate_text_diagram(output_path, product_name, "architecture")

    img = Image.new("RGB", (1240, 820), "white")
    draw = ImageDraw.Draw(img)

    blue = (24, 144, 255)
    light_blue = (233, 246, 255)
    green = (82, 196, 26)
    light_green = (246, 255, 237)
    orange = (250, 173, 20)
    light_orange = (255, 247, 230)
    gray = (102, 102, 102)
    black = (34, 34, 34)
    white = (255, 255, 255)

    font_title = _load_cjk_font(28)
    font_heading = _load_cjk_font(20)
    font_body = _load_cjk_font(15)
    font_small = _load_cjk_font(14)

    draw.rectangle([0, 0, 1240, 70], fill=blue)
    title_text = f"{product_name}系统架构图"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_x = (1240 - (title_bbox[2] - title_bbox[0])) // 2
    draw.text((title_x, 18), title_text, fill=white, font=font_title)

    browser_box = (60, 120, 310, 245)
    frontend_box = (360, 100, 760, 305)
    backend_box = (830, 100, 1180, 325)
    data_box = (360, 390, 740, 605)
    service_box = (830, 390, 1180, 620)

    for box, fill, outline in [
        (browser_box, white, blue),
        (frontend_box, light_blue, blue),
        (backend_box, light_green, green),
        (data_box, white, orange),
        (service_box, light_orange, orange),
    ]:
        draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=3)

    draw.text((130, 150), "用户访问层", fill=blue, font=font_heading)
    _draw_wrapped_text(draw, (85, 180, 285, 232), "浏览器访问入口、登录页面、首页导航和各业务页面入口", font_body, black)

    draw.text((505, 132), "页面展示层", fill=blue, font=font_heading)
    _draw_wrapped_text(draw, (395, 170, 725, 285), "负责登录页、系统首页、用户管理、设备管理、报表统计、告警查看、系统设置等页面展示，并承载列表、按钮、输入项、统计卡片等交互元素。", font_body, black)

    draw.text((945, 132), "业务处理层", fill=green, font=font_heading)
    _draw_wrapped_text(draw, (860, 170, 1150, 305), "负责用户请求处理、业务校验、数据查询、结果返回和统一接口管理，是系统功能的核心处理区域。", font_body, black)

    draw.text((500, 420), "数据存储层", fill=orange, font=font_heading)
    _draw_wrapped_text(draw, (390, 460, 710, 585), "负责用户、设备、报表、告警、系统配置等业务数据的保存与读取，为页面展示和业务处理提供数据支撑。", font_body, black)

    draw.text((935, 420), "支撑服务层", fill=orange, font=font_heading)
    _draw_wrapped_text(draw, (860, 460, 1150, 600), "负责导出说明书、导出源代码文档、截图采集、状态记录及其它支撑性服务，保障软件交付和管理功能可持续运行。", font_body, black)

    _draw_arrow(draw, browser_box[2], 180, frontend_box[0], 180, color=blue)
    _draw_arrow(draw, frontend_box[2], 200, backend_box[0], 200, color=green)
    _draw_arrow(draw, backend_box[0] + 90, backend_box[3], data_box[2] - 70, data_box[1], color=orange)
    _draw_arrow(draw, backend_box[0] + 220, backend_box[3], service_box[0] + 140, service_box[1], color=orange)
    _draw_arrow(draw, service_box[0], 555, data_box[2], 555, color=gray)

    draw.text((270, 710), "图1：系统架构图展示了页面展示层、业务处理层、数据存储层与支撑服务层之间的关系。", fill=gray, font=font_small)

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


def _generate_text_diagram(output_path: str, product_name: str, diag_type: str) -> str:
    """Fallback: generate text-based diagram as a .txt file."""
    txt_path = output_path.replace(".png", ".txt")
    if diag_type == "architecture":
        content = f"""系统架构图 - {product_name} V1.0

┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  用户浏览器   │ ──> │  React+Vite前端   │ ──> │   FastAPI后端        │
│  Chrome/Edge │     │  Ant Design UI   │     │   REST API + SSE    │
└─────────────┘     └──────────────────┘     └──────┬───────┬──────┘
                                                     │       │
                                              ┌──────┘       └──────┐
                                              ▼                      ▼
                                     ┌────────────┐      ┌──────────────────┐
                                     │ PostgreSQL │      │ Celery Workers   │
                                     │ / SQLite   │      │ 8阶段流水线       │
                                     └────────────┘      │ DeepSeek LLM     │
                                                         └──────────────────┘
"""
    else:
        content = f"""流程图 - {product_name} V1.0

关键词输入 ──> PRD生成 ──> 应用开发 ──> 运行启动 ──> 自动截图 ──> 说明书Word ──> 源码Word ──> 下载交付
   │            │           │           │           │             │            │           │
   ▼            ▼           ▼           ▼           ▼             ▼            ▼           ▼
  用户         DeepSeek    React+     uvicorn    Playwright   flash起草    55行/页     导出记录
  输入         v4-pro     FastAPI    + Vite      5页截图     pro终审    60页上限    +下载URL
"""
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(content)
    return txt_path
