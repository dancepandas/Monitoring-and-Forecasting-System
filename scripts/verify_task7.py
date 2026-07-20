from playwright.sync_api import sync_playwright
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://localhost:5173/"
OUT = ROOT / ".superpowers" / "sdd" / "task-7-screenshots"
OUT.mkdir(parents=True, exist_ok=True)

console_logs = []
page_errors = []
request_errors = []

def save_logs(tag):
    with open(OUT / f"{tag}-console.json", "w", encoding="utf-8") as f:
        json.dump({
            "console": console_logs,
            "page_errors": page_errors,
            "request_errors": request_errors,
        }, f, ensure_ascii=False, indent=2)


def wait_for_console_text(page, needle, timeout=60):
    """Wait until a console log containing `needle` appears."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for entry in console_logs:
            if needle in entry.get("text", ""):
                return entry
        time.sleep(0.5)
    raise TimeoutError(f"Console log containing '{needle}' not found within {timeout}s")


def run():
    global console_logs, page_errors, request_errors
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="msedge",
            args=["--ignore-certificate-errors", "--use-gl=swiftshader"]
        )
        context = browser.new_context(viewport={"width": 1600, "height": 900}, ignore_https_errors=True)
        page = context.new_page()

        page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("requestfailed", lambda req: request_errors.append(f"{req.url}: {req.failure_error_text}"))
        page.on("request", lambda req: print(f"   REQUEST: {req.method} {req.url}"))

        print("[1] Open login page")
        page.goto(f"{URL}login")
        page.screenshot(path=str(OUT / "01-login.png"), full_page=False)

        print("[2] Login with admin/admin123")
        page.fill("#login-username", "admin")
        page.fill("#login-password", "admin123")
        page.click("button.btn.primary")
        page.wait_for_url(f"{URL}", wait_until="networkidle")
        page.screenshot(path=str(OUT / "02-overview.png"), full_page=False)

        print("[3] Wait for 3D terrain canvas and model ready")
        page.wait_for_selector("canvas", timeout=30000)
        ready_entry = wait_for_console_text(page, "模型+站点就绪", timeout=60)
        print("   Ready log:", ready_entry)
        time.sleep(2)
        page.screenshot(path=str(OUT / "03-terrain-loaded.png"), full_page=False)

        print("[4] Inspect station marker readiness")
        # The log text contains the station count, e.g. "站点 4"
        station_count = 0
        try:
            station_count = int(ready_entry["text"].split("站点")[-1].strip())
        except Exception:
            pass
        print(f"   Station count from log: {station_count}")

        print("[5] Hover/click center of canvas where station cluster is visible")
        canvas = page.locator("canvas")
        box = canvas.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(cx, cy)
        time.sleep(0.5)
        page.mouse.click(cx, cy)
        time.sleep(1.5)
        page.screenshot(path=str(OUT / "04-after-click.png"), full_page=False)

        print("[6] Check whether StationDrawer opened on station click")
        drawer_visible = page.locator(".station-drawer").is_visible(timeout=3000)
        print(f"   StationDrawer visible after station click: {drawer_visible}")

        print("[6b] Click a warning item to verify StationDrawer opens")
        # Close drawer opened by station click so warning item is clickable
        page.click(".drawer-close")
        time.sleep(0.5)
        warning_items = page.locator(".hud-risk-item")
        if warning_items.count() > 0:
            warning_items.nth(0).click()
            time.sleep(0.8)
            drawer_visible_warn = page.locator(".station-drawer").is_visible(timeout=3000)
            print(f"   StationDrawer visible after warning click: {drawer_visible_warn}")
            page.screenshot(path=str(OUT / "04b-drawer-open.png"), full_page=False)
            # Close drawer
            page.click(".drawer-close")
            time.sleep(0.5)
        else:
            print("   No warning items to click")

        print("[7] Resize window and verify canvas still fills viewport")
        page.set_viewport_size({"width": 1200, "height": 800})
        time.sleep(1.5)
        page.screenshot(path=str(OUT / "05-resized.png"), full_page=False)
        page.set_viewport_size({"width": 1600, "height": 900})

        print("[8] Mock /api/data/latest with warning/danger levels")
        def handle_route(route, request):
            url = request.url
            if "data/latest" in url:
                fake = {
                    "data": [
                        {"station_code": "00125", "water_level": 999.0, "virtual_flow": 120, "warning_level": 100, "danger_level": 200},
                        {"station_code": "00230", "water_level": 150.0, "virtual_flow": 80, "warning_level": 100, "danger_level": 200},
                        {"station_code": "00231", "water_level": 80.0, "virtual_flow": 60, "warning_level": 100, "danger_level": 200},
                        {"station_code": "00234", "water_level": 50.0, "virtual_flow": 40, "warning_level": 100, "danger_level": 200},
                    ]
                }
                print(f"   INTERCEPTED {url}, returning mock data")
                route.fulfill(status=200, content_type="application/json", body=json.dumps(fake))
            else:
                route.continue_()

        page.route(lambda url: "data/latest" in url, handle_route)
        page.reload(wait_until="networkidle")
        page.wait_for_selector("canvas", timeout=30000)
        wait_for_console_text(page, "模型+站点就绪", timeout=60)

        print("[8b] Zoom in on station cluster for alert color inspection")
        canvas = page.locator("canvas")
        box = canvas.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(cx, cy)
        for _ in range(6):
            page.mouse.wheel(0, -300)
            time.sleep(0.2)
        time.sleep(2)
        page.screenshot(path=str(OUT / "06-alert-mock.png"), full_page=False)
        time.sleep(2)
        page.screenshot(path=str(OUT / "06b-alert-mock-later.png"), full_page=False)

        save_logs("final")
        print("[9] Verification complete; logs and screenshots saved to", OUT)
        browser.close()


if __name__ == "__main__":
    run()
