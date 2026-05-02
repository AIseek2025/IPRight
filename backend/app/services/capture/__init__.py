from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            scenarios = capture_manifest.get("scenarios", [])
            sorted_scenarios = sorted(scenarios, key=lambda s: s.get("priority", 0))

            for scenario in sorted_scenarios:
                result = await self._capture_one(scenario, page, demo_accounts)
                results.append(result)

            await browser.close()

        return results

    async def _capture_one(
        self,
        scenario: dict,
        page,
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

        try:
            if requires_auth and demo_accounts:
                account = demo_accounts[0]
                await self._do_login(page, account)

            await page.goto(url, wait_until="networkidle", timeout=15000)

            for action in actions:
                await self._execute_action(page, action)

            await page.wait_for_timeout(1000)
            await page.screenshot(path=image_path, full_page=True)

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
            return ScreenshotResult(
                scenario_id=scenario_id,
                page_title=title,
                route=route,
                image_path="",
                success=False,
                error=str(e),
            )

    async def _do_login(self, page, account: dict) -> None:
        username = account.get("username", "admin")
        password = account.get("password", "admin123")
        try:
            await page.goto(f"{self.base_url}/login", wait_until="networkidle", timeout=10000)
            await page.wait_for_timeout(500)
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
                await page.wait_for_timeout(2000)
            except Exception:
                pass
            # Inject localStorage flag for persistent auth across page navigations
            try:
                await page.evaluate("localStorage.setItem('ipright_demo_auth', 'true')")
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Login attempt issue: {e}")

    async def _execute_action(self, page, action) -> None:
        if isinstance(action, str):
            action = {"action": action}

        action_type = action.get("action", "")
        target = action.get("target", "")
        value = action.get("value", "")

        try:
            if action_type == "login_as_admin":
                pass
            elif action_type == "click_menu":
                await page.click(f'text="{target}"', timeout=3000)
            elif action_type == "click_button":
                await page.click(f'button:has-text("{target}")', timeout=3000)
            elif action_type == "fill_input":
                await page.fill(f'input[name="{target}"], input[placeholder*="{target}"]', value, timeout=3000)
            elif action_type == "wait_for_text":
                await page.wait_for_selector(f'text="{target}"', timeout=5000)
            await page.wait_for_timeout(500)
        except Exception as e:
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
