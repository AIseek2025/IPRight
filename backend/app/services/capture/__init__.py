from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_ROUTE_MARKER_ALIASES = {
    "statistics": ["统计", "分析", "报表", "看板"],
    "analytics": ["分析", "洞察", "报表", "趋势"],
    "reports": ["报表", "分析", "统计"],
}


@lru_cache(maxsize=1)
def _embedded_capture_font_css() -> str:
    candidate_paths = [
        Path(__file__).resolve().parents[4] / "assets" / "fonts" / "IPRightCJK.ttf",
        Path("/opt/ipright/assets/fonts/IPRightCJK.ttf"),
    ]
    for font_path in candidate_paths:
        try:
            if not font_path.is_file():
                continue
            font_bytes = font_path.read_bytes()
            font_base64 = base64.b64encode(font_bytes).decode("ascii")
            return (
                "@font-face {"
                "  font-family: 'IPRight CJK';"
                "  src: url(data:font/ttf;base64,"
                + font_base64
                + ") format('truetype');"
                "  font-weight: 400;"
                "  font-style: normal;"
                "  font-display: swap;"
                "}"
            )
        except Exception:
            continue
    return ""


@dataclass
class ScreenshotResult:
    scenario_id: str
    page_title: str
    route: str
    image_path: str
    caption: str = ""
    elements: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None


class PlaywrightCapture:
    """Auto-capture screenshots of a running web app based on capture_manifest."""

    def __init__(self, base_url: str, output_dir: str, headless: bool = True):
        self.base_url = base_url.rstrip("/")
        self.output_dir = output_dir
        self.headless = headless
        os.makedirs(output_dir, exist_ok=True)

    async def capture_scenarios(
        self,
        capture_manifest: dict,
        demo_accounts: list[dict] | None = None,
    ) -> list[ScreenshotResult]:
        results: list[ScreenshotResult] = []
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("Playwright not installed. Using stub capture.")
            return self._stub_capture(capture_manifest)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-zygote",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1680, "height": 1280},
                locale="zh-CN",
                device_scale_factor=1.25,
            )

            scenarios = capture_manifest.get("scenarios", [])
            sorted_scenarios = sorted(scenarios, key=lambda s: s.get("priority", 0))

            for scenario in sorted_scenarios:
                result = await self._capture_one(scenario, context, demo_accounts)
                results.append(result)

            await browser.close()

        return results

    async def _capture_one(
        self,
        scenario: dict,
        context,
        demo_accounts: list[dict] | None,
    ) -> ScreenshotResult:
        scenario_id = scenario.get("id", "unknown")
        route = scenario.get("route", "/")
        title = scenario.get("title", scenario_id)
        actions: list[dict] = scenario.get("actions", [])
        requires_auth = scenario.get("requires_auth", False)

        url = f"{self.base_url}{route}"
        filename = f"{scenario_id}.png"
        image_path = os.path.join(self.output_dir, filename)
        page = await context.new_page()
        expected_markers = self._expected_markers(title, route)

        try:
            account = demo_accounts[0] if demo_accounts else {}
            if requires_auth and demo_accounts:
                await self._do_login(page, account)

            await self._open_ready_page(page, url)
            if requires_auth and route != "/login":
                await self._recover_auth_if_needed(
                    page,
                    url,
                    route=route,
                    title=title,
                    expected_markers=expected_markers,
                    account=account,
                )

            for action in actions:
                await self._execute_action(page, action)

            await self._stabilize_page(page, route=route, title=title, expected_markers=expected_markers)
            await self._capture_with_retry(
                page,
                image_path,
                url=url,
                route=route,
                title=title,
                expected_markers=expected_markers,
            )

            try:
                labels = await page.evaluate("""() => {
                    const els = document.querySelectorAll('button, a, input, th, h1, h2, h3, h4, label');
                    return Array.from(els).map(e => e.textContent?.trim()).filter(Boolean).slice(0, 20);
                }""")
            except Exception:
                labels = []

            return ScreenshotResult(
                scenario_id=scenario_id,
                page_title=title,
                route=route,
                image_path=image_path,
                caption=f"图: {title}",
                elements=labels or [],
                success=True,
            )
        except Exception as e:
            logger.error(f"Capture failed for {scenario_id}: {e}")
            self._cleanup_failed_capture(image_path)
            return ScreenshotResult(
                scenario_id=scenario_id,
                page_title=title,
                route=route,
                image_path="",
                success=False,
                error=str(e),
            )
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def _open_ready_page(self, page, url: str) -> None:
        await self._goto_with_retry(page, url)
        await self._ensure_capture_css(page)
        await self._stabilize_page(page)

    async def _ensure_capture_css(self, page) -> None:
        try:
            await page.emulate_media(media="screen")
        except Exception:
            pass
        try:
            await page.add_style_tag(
                content=_embedded_capture_font_css()
                + """
                html, body {
                  writing-mode: horizontal-tb !important;
                  text-orientation: mixed !important;
                  font-family: "IPRight CJK", "Noto Sans SC", "Noto Sans CJK SC",
                    "PingFang SC", "Microsoft YaHei", sans-serif !important;
                  -webkit-font-smoothing: antialiased !important;
                  text-rendering: optimizeLegibility !important;
                }
                * {
                  text-orientation: mixed !important;
                  writing-mode: horizontal-tb !important;
                  font-family: "IPRight CJK", "Noto Sans SC", "Noto Sans CJK SC",
                    "PingFang SC", "Microsoft YaHei", sans-serif !important;
                }
                #root, main, [role="main"] {
                  min-height: 100vh !important;
                }
                input, button, textarea, select, option, table, thead, tbody, tr, th, td,
                span, div, p, label, h1, h2, h3, h4, h5, h6, a {
                  font-family: "IPRight CJK", "Noto Sans SC", "Noto Sans CJK SC",
                    "PingFang SC", "Microsoft YaHei", sans-serif !important;
                }
                nav, aside, .sidebar, [class*="sidebar"], [class*="nav"] {
                  min-width: 280px !important;
                }
                nav *, aside *, .sidebar *, [class*="sidebar"] *, [class*="nav"] * {
                  writing-mode: horizontal-tb !important;
                  white-space: normal !important;
                  word-break: keep-all !important;
                  overflow-wrap: break-word !important;
                }
                img, canvas, svg {
                  max-width: 100% !important;
                }
                """
            )
        except Exception:
            pass

    async def _wait_for_fonts(self, page) -> None:
        try:
            await page.evaluate(
                """async () => {
                    if (!document.fonts || !document.fonts.ready) {
                        return;
                    }
                    try {
                        await Promise.race([
                            document.fonts.ready,
                            new Promise((resolve) => setTimeout(resolve, 4000)),
                        ]);
                        await Promise.race([
                            document.fonts.load('14px "IPRight CJK"'),
                            new Promise((resolve) => setTimeout(resolve, 2500)),
                        ]);
                    } catch (_) {
                    }
                }"""
            )
        except Exception:
            pass

    async def _goto_with_retry(self, page, url: str) -> None:
        last_error: Exception | None = None
        strategies = [
            {"wait_until": "domcontentloaded", "timeout": 30000},
            {"wait_until": "commit", "timeout": 12000},
        ]
        for strategy in strategies:
            try:
                await page.goto(url, wait_until=strategy["wait_until"], timeout=strategy["timeout"])
                return
            except Exception as exc:
                last_error = exc
                await page.wait_for_timeout(800)
        if last_error is not None:
            raise last_error

    async def _force_demo_auth(self, page, account: dict) -> None:
        username = account.get("username", "admin")
        await page.evaluate(
            """(payload) => {
                const username = String(payload?.username || 'admin');
                const user = JSON.stringify({ username, role: 'admin' });
                const pairs = [
                    ['ipright_demo_auth', 'true'],
                    ['token', 'demo-token'],
                    ['user', user],
                    ['ipright_api_token', 'demo-token'],
                ];
                for (const [key, value] of pairs) {
                    try { localStorage.setItem(key, value); } catch (_) {}
                    try { sessionStorage.setItem(key, value); } catch (_) {}
                }
                try {
                    window.dispatchEvent(new StorageEvent('storage', { key: 'ipright_demo_auth', newValue: 'true' }));
                } catch (_) {}
            }""",
            {"username": username},
        )

    async def _recover_auth_if_needed(
        self,
        page,
        url: str,
        *,
        route: str,
        title: str,
        expected_markers: list[str] | None,
        account: dict,
    ) -> None:
        info = await self._read_content_info(page, title=title, expected_markers=expected_markers)
        if not info or not self._looks_like_login_info(info):
            return

        await self._force_demo_auth(page, account)
        try:
            await page.click('button[type="submit"], button:has-text("登录"), button:has-text("登錄")', timeout=1200)
            await page.wait_for_timeout(800)
        except Exception:
            pass
        await self._goto_with_retry(page, url)
        await self._ensure_capture_css(page)
        await self._stabilize_page(page, route=route, title=title, expected_markers=expected_markers)

    def _expected_markers(self, title: str | None, route: str) -> list[str]:
        normalized_title = (title or "").replace("筛选结果", "").strip()
        route_key = str(route or "").strip("/").split("/")[-1]
        if route == "/login":
            markers = ["登录", "登录系统", "用户名", "密码", "平台入口概览"]
            if normalized_title:
                markers.insert(0, normalized_title)
            return markers
        if route == "/dashboard":
            markers = ["系统首页", "调度总览", "工作台", "概览", "Dashboard"]
            if normalized_title:
                markers.insert(0, normalized_title)
            return markers
        markers: list[str] = []
        if normalized_title:
            markers.append(normalized_title)
        markers.extend(_ROUTE_MARKER_ALIASES.get(route_key, []))
        deduped: list[str] = []
        for marker in markers:
            value = str(marker or "").strip()
            if value and value not in deduped:
                deduped.append(value)
        return deduped

    def _cleanup_failed_capture(self, image_path: str) -> None:
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass

    async def _stabilize_page(
        self,
        page,
        route: str = "",
        title: str | None = None,
        expected_markers: list[str] | None = None,
    ) -> None:
        await self._wait_for_fonts(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=2500)
        except Exception:
            pass

        for _ in range(8):
            if await self._has_meaningful_content(page, route=route, title=title, expected_markers=expected_markers):
                break
            await page.wait_for_timeout(500)

        await page.wait_for_timeout(700)
        await self._wait_for_fonts(page)

    async def _has_meaningful_content(
        self,
        page,
        route: str = "",
        title: str | None = None,
        expected_markers: list[str] | None = None,
    ) -> bool:
        info = await self._read_content_info(page, title=title, expected_markers=expected_markers)
        if info is None:
            return False
        return self._is_meaningful_content_info(info, route=route, expected_markers=expected_markers)

    async def _read_content_info(self, page, title: str | None = None, expected_markers: list[str] | None = None) -> dict | None:
        try:
            return await page.evaluate(
                """(payload) => {
                    const expectedTitle = payload?.expectedTitle || '';
                    const expectedMarkers = Array.isArray(payload?.expectedMarkers) ? payload.expectedMarkers : [];
                    const body = document.body;
                    const root = document.querySelector('#root') || body;
                    const main = root?.querySelector('main, [role="main"]') || root || body;
                    const text = ((root?.innerText || body?.innerText || '') + '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    const mainText = ((main?.innerText || text || '') + '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    const blocks = root
                        ? root.querySelectorAll('main, section, article, table, ul, ol, form, nav, h1, h2, h3, button, [role="button"], [class*="card"], [class*="table"], [class*="panel"]').length
                        : 0;
                    const mainBlocks = main
                        ? main.querySelectorAll('section, article, table, ul, ol, form, h1, h2, h3, button, [role="button"], [class*="card"], [class*="table"], [class*="panel"]').length
                        : blocks;
                    const headings = Array.from(root?.querySelectorAll('h1, h2, h3') || [])
                        .map((el) => (el.textContent || '').trim())
                        .filter(Boolean);
                    const mainHeadings = Array.from(main?.querySelectorAll('h1, h2, h3') || [])
                        .map((el) => (el.textContent || '').trim())
                        .filter(Boolean);
                    const inputs = root ? root.querySelectorAll('input').length : 0;
                    const buttons = root ? root.querySelectorAll('button, [role="button"]').length : 0;
                    const mainInputs = main ? main.querySelectorAll('input').length : inputs;
                    const mainButtons = main ? main.querySelectorAll('button, [role="button"]').length : buttons;
                    const height = Math.max(
                        document.documentElement?.scrollHeight || 0,
                        body?.scrollHeight || 0,
                        root?.scrollHeight || 0,
                    );
                    return {
                        textLength: text.length,
                        blocks,
                        headings,
                        inputs,
                        buttons,
                        mainTextLength: mainText.length,
                        mainBlocks,
                        mainHeadings,
                        mainInputs,
                        mainButtons,
                        height,
                        readyState: document.readyState,
                        hasExpectedTitle: expectedTitle
                            ? headings.some((item) => item.includes(expectedTitle))
                            : true,
                        hasExpectedMarker: expectedMarkers.length
                            ? expectedMarkers.some((item) => text.includes(item) || headings.some((heading) => heading.includes(item)))
                            : true,
                        hasMainExpectedTitle: expectedTitle
                            ? mainHeadings.some((item) => item.includes(expectedTitle))
                            : true,
                        hasMainExpectedMarker: expectedMarkers.length
                            ? expectedMarkers.some((item) => mainText.includes(item) || mainHeadings.some((heading) => heading.includes(item)))
                            : true,
                        hasLoginSignals: /登录|用户名|密码/.test(mainText) || mainHeadings.some((item) => /登录|用户名|密码/.test(item)),
                    };
                }""",
                {"expectedTitle": title or "", "expectedMarkers": expected_markers or []},
            )
        except Exception:
            return None

    def _looks_like_login_info(self, info: dict) -> bool:
        return bool(info.get("hasLoginSignals")) and int(info.get("mainInputs", 0) or 0) >= 2 and int(info.get("mainButtons", 0) or 0) >= 1

    def _is_meaningful_content_info(self, info: dict, *, route: str = "", expected_markers: list[str] | None = None) -> bool:
        if info.get("readyState") not in {"interactive", "complete"}:
            return False

        text_length = int(info.get("textLength", 0) or 0)
        blocks = int(info.get("blocks", 0) or 0)
        inputs = int(info.get("inputs", 0) or 0)
        buttons = int(info.get("buttons", 0) or 0)
        headings = info.get("headings") or []
        main_text_length = int(info.get("mainTextLength", 0) or 0)
        main_blocks = int(info.get("mainBlocks", 0) or 0)
        main_inputs = int(info.get("mainInputs", 0) or 0)
        main_buttons = int(info.get("mainButtons", 0) or 0)
        main_headings = info.get("mainHeadings") or []
        height = int(info.get("height", 0) or 0)
        has_expected_title = bool(info.get("hasExpectedTitle"))
        has_expected_marker = bool(info.get("hasExpectedMarker"))
        has_main_expected_title = bool(info.get("hasMainExpectedTitle"))
        has_main_expected_marker = bool(info.get("hasMainExpectedMarker"))
        looks_like_login = self._looks_like_login_info(info)

        if route == "/login":
            if has_expected_marker and main_inputs >= 2 and main_buttons >= 1:
                return True
            if has_expected_title and main_text_length >= 24:
                return True
            if main_inputs >= 2 and main_buttons >= 1 and main_text_length >= 16:
                return True
            if text_length >= 80 and (blocks >= 2 or len(headings) >= 1 or buttons >= 2):
                return True
            return False

        if looks_like_login and not (has_main_expected_marker or has_main_expected_title):
            return False
        if has_main_expected_title and main_text_length >= 24:
            return True
        if has_main_expected_marker and (main_text_length >= 40 or main_blocks >= 2 or len(main_headings) >= 1):
            return True
        if has_expected_marker and has_main_expected_marker and text_length >= 60:
            return True
        if text_length >= 140 and main_text_length >= 80 and main_blocks >= 3 and not looks_like_login:
            return True
        return blocks >= 4 and height >= 420

    def _summarize_content_info(self, info: dict | None) -> str:
        if not info:
            return "content_probe=unavailable"
        headings = [str(item).strip() for item in (info.get("headings") or []) if str(item).strip()]
        preview = " | ".join(headings[:2]) if headings else "-"
        return (
            "content_probe="
            f"ready={info.get('readyState')},"
            f"text={info.get('textLength')},"
            f"blocks={info.get('blocks')},"
            f"inputs={info.get('inputs')},"
            f"buttons={info.get('buttons')},"
            f"height={info.get('height')},"
            f"marker={info.get('hasExpectedMarker')},"
            f"title={info.get('hasExpectedTitle')},"
            f"headings={preview}"
        )

    async def _capture_with_retry(
        self,
        page,
        image_path: str,
        *,
        url: str,
        route: str,
        title: str,
        expected_markers: list[str] | None = None,
    ) -> None:
        last_error: Exception | None = None
        last_info: dict | None = None
        for attempt in range(3):
            try:
                await self._wait_for_fonts(page)
                await page.screenshot(path=image_path, full_page=True)
                if await self._is_usable_capture(page, image_path, route=route, title=title, expected_markers=expected_markers):
                    return
                last_info = await self._read_content_info(page, title=title, expected_markers=expected_markers)
                await page.wait_for_timeout(700)
                await page.reload(wait_until="domcontentloaded", timeout=30000)
                await self._ensure_capture_css(page)
                await self._stabilize_page(page, route=route, title=title, expected_markers=expected_markers)
            except Exception as exc:
                last_error = exc
                last_info = await self._read_content_info(page, title=title, expected_markers=expected_markers)
                await page.wait_for_timeout(700)
                if attempt < 2:
                    await self._goto_with_retry(page, url)
                    await self._ensure_capture_css(page)
                    await self._stabilize_page(page, route=route, title=title, expected_markers=expected_markers)
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError(
            f"Screenshot for {title} appears blank or mismatched after retries; "
            f"{self._summarize_content_info(last_info)}"
        )

    async def _is_usable_capture(
        self,
        page,
        image_path: str,
        *,
        route: str,
        title: str,
        expected_markers: list[str] | None = None,
    ) -> bool:
        if not os.path.exists(image_path):
            return False

        file_size = os.path.getsize(image_path)
        meaningful = await self._has_meaningful_content(page, route=route, title=title, expected_markers=expected_markers)
        if meaningful:
            return file_size >= 800
        return False

    async def _do_login(self, page, account: dict) -> None:
        username = account.get("username", "admin")
        password = account.get("password", "admin123")
        try:
            await self._goto_with_retry(page, f"{self.base_url}/login")
            await self._stabilize_page(page, route="/login", title="登录")
            try:
                await page.fill('input[name="username"], input[placeholder*="用户名"], input[placeholder*="账号"]', username, timeout=3000)
            except Exception:
                pass
            try:
                await page.fill('input[name="password"], input[type="password"]', password, timeout=3000)
            except Exception:
                pass
            try:
                await page.click('button[type="submit"], button:has-text("登录"), button:has-text("登錄")', timeout=3000)
                await page.wait_for_timeout(1500)
            except Exception:
                pass
            await self._force_demo_auth(page, account)
        except Exception as e:
            logger.warning(f"Login attempt issue: {e}")

    def _input_selectors(self, target: str) -> list[str]:
        target = str(target or "").strip()
        selectors: list[str] = []
        if target:
            selectors.extend(
                [
                    f'input[name="{target}"]',
                    f'input[placeholder*="{target}"]',
                    f'input[aria-label*="{target}"]',
                    f'input[data-testid*="{target}"]',
                    f'textarea[name="{target}"]',
                    f'textarea[placeholder*="{target}"]',
                    f'textarea[aria-label*="{target}"]',
                    f'[role="searchbox"][aria-label*="{target}"]',
                ]
            )

        if target in {"搜索", "查询", "筛选"}:
            selectors.extend(
                [
                    'input[type="search"]',
                    '[role="searchbox"]',
                    'input[placeholder*="搜索"]',
                    'input[placeholder*="查询"]',
                    'input[placeholder*="筛选"]',
                    'input[placeholder*="关键字"]',
                    'input[placeholder*="关键词"]',
                    'input[placeholder*="编号"]',
                    'input[placeholder*="名称"]',
                    'textarea[placeholder*="搜索"]',
                ]
            )

        unique: list[str] = []
        for selector in selectors:
            if selector not in unique:
                unique.append(selector)
        return unique

    async def _fill_input_field(self, page, target: str, value: str) -> bool:
        value = str(value or "")
        for selector in self._input_selectors(target):
            try:
                await page.fill(selector, value, timeout=2500)
                return True
            except Exception:
                continue

        try:
            filled = await page.evaluate(
                """(payload) => {
                    const target = String(payload?.target || '').trim();
                    const value = String(payload?.value || '');
                    const isSearchLike = ['搜索', '查询', '筛选'].includes(target);
                    const candidates = Array.from(document.querySelectorAll(
                        'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([disabled]), ' +
                        'textarea:not([disabled]), [role="searchbox"], [contenteditable="true"]'
                    ));
                    const visible = candidates.filter((el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                    });
                    const scored = visible.map((el) => {
                        const attrs = [
                            el.getAttribute('name') || '',
                            el.getAttribute('placeholder') || '',
                            el.getAttribute('aria-label') || '',
                            el.getAttribute('data-testid') || '',
                            el.textContent || '',
                        ].join(' ');
                        let score = 0;
                        if (target && attrs.includes(target)) score += 4;
                        if ((el.getAttribute('type') || '').toLowerCase() === 'search') score += 3;
                        if ((el.getAttribute('role') || '').toLowerCase() === 'searchbox') score += 3;
                        if (isSearchLike && /搜索|查询|筛选|关键字|关键词|编号|名称/.test(attrs)) score += 2;
                        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') score += 1;
                        return { el, score };
                    }).sort((a, b) => b.score - a.score);
                    const winner = scored[0]?.el;
                    if (!winner) return false;
                    winner.focus();
                    if ('value' in winner) {
                        winner.value = value;
                    } else {
                        winner.textContent = value;
                    }
                    winner.dispatchEvent(new Event('input', { bubbles: true }));
                    winner.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }""",
                {"target": target, "value": value},
            )
            return bool(filled)
        except Exception:
            return False

    async def _trigger_search_submit(self, page, target: str) -> None:
        if str(target or "").strip() not in {"搜索", "查询", "筛选"}:
            return
        for selector in [
            'button:has-text("查询")',
            'button:has-text("查询列表")',
            'button:has-text("搜索")',
            'button:has-text("筛选")',
            '[role="button"]:has-text("查询")',
        ]:
            try:
                await page.click(selector, timeout=1200)
                return
            except Exception:
                continue

    async def _execute_action(self, page, action) -> None:
        if isinstance(action, str):
            action = {"action": action}

        action_type = action.get("action", "")
        target = action.get("target", "")
        value = action.get("value", "")
        optional = bool(action.get("optional"))

        try:
            if action_type == "login_as_admin":
                pass
            elif action_type == "click_menu":
                await page.click(f'text="{target}"', timeout=3000)
            elif action_type == "click_button":
                await page.click(f'button:has-text("{target}")', timeout=3000)
            elif action_type == "fill_input":
                filled = await self._fill_input_field(page, target, value)
                if not filled:
                    if optional:
                        return
                    raise RuntimeError(f"Unable to locate input field for target: {target}")
                await self._trigger_search_submit(page, target)
            elif action_type == "wait_for_text":
                await page.wait_for_selector(f'text="{target}"', timeout=5000)
            await page.wait_for_timeout(500)
            await self._stabilize_page(page)
        except Exception as e:
            if optional:
                logger.info(f"Optional action {action_type} / {target} skipped: {e}")
                return
            logger.warning(f"Action {action_type} / {target} failed: {e}")

    def _stub_capture(self, capture_manifest: dict) -> list[ScreenshotResult]:
        results = []
        for scenario in capture_manifest.get("scenarios", []):
            results.append(ScreenshotResult(
                scenario_id=scenario.get("id", "unknown"),
                page_title=scenario.get("title", "untitled"),
                route=scenario.get("route", "/"),
                image_path="",
                caption=f"图: {scenario.get('title', '')}",
                success=False,
                error="Playwright not installed - stub mode",
            ))
        return results
