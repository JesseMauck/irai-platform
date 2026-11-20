"""Browser end-to-end test (Playwright). Needs the backend on :8000 and frontend on :3000.
Run:  python e2e/test_e2e.py [base_url] [screenshot_dir]"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
OUT = sys.argv[2] if len(sys.argv) > 2 else "e2e-screenshots"
PAGES = ["/", "/monitor/adr", "/monitor/adr/TM", "/monitor/etf", "/monitor/fundamental", "/ticker/NVDA", "/research",
         "/research/reading-the-adr-basis", "/screeners", "/community", "/trades", "/leaderboards", "/learn",
         "/pricing", "/methodology", "/valuebot"]


def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.on("console", lambda m: m.type == "error" and errors.append(f"{pg.url}: {m.text}"))
        pg.on("pageerror", lambda e: errors.append(f"{pg.url}: {e}"))
        for path in PAGES:
            pg.goto(BASE + path, wait_until="networkidle")
            pg.wait_for_timeout(600)
            pg.screenshot(path=f"{OUT}/{path.strip('/').replace('/', '_') or 'home'}.png", full_page=path == "/")
            print("ok", path)

        # live ticker search: ⌘K → type → Enter → ticker page populates
        pg.goto(BASE + "/", wait_until="networkidle")
        pg.keyboard.press("Control+k")
        pg.wait_for_selector("input[placeholder^='Any ticker']")
        pg.keyboard.type("MSFT")
        pg.wait_for_timeout(500)
        pg.keyboard.press("Enter")
        pg.wait_for_function("location.pathname === '/ticker/MSFT'")
        pg.wait_for_selector("text=Key statistics")
        assert "MSFT" in pg.inner_text("h1")
        print("ok ticker search → /ticker/MSFT")

        # sign in, run a ValueBot valuation end to end
        pg.goto(BASE + "/login")
        pg.fill("input[type=email]", "essential@irai-demo.com")
        pg.fill("input[type=password]", "irai-demo-2026")
        pg.click("button[type=submit]")
        pg.wait_for_function("location.pathname === '/account'")
        pg.wait_for_selector("text=Subscription")
        pg.fill("input[placeholder='Add ticker']", "AAPL")
        pg.click("text=Add")
        pg.wait_for_selector("a[href='/ticker/AAPL']")
        pg.screenshot(path=f"{OUT}/account.png")
        print("ok login + watchlist")

        pg.goto(BASE + "/valuebot?ticker=DEMO", wait_until="networkidle")
        pg.wait_for_selector("text=Suggested method")
        pg.click("text=Run valuation")
        pg.wait_for_function("/^\\/valuebot\\/2/.test(location.pathname)")
        t0 = time.time()
        pg.wait_for_selector("text=Value / share", timeout=180_000)
        pg.wait_for_timeout(800)
        pg.screenshot(path=f"{OUT}/valuebot_report.png", full_page=True)
        print(f"ok valuebot run ({time.time() - t0:.0f}s)")

        # trade post captures live price
        pg.goto(BASE + "/trades", wait_until="networkidle")
        pg.fill("input[placeholder='Long ticker']", "TM")
        pg.fill("input[placeholder='Short leg (optional)']", "7203.T")
        pg.fill("input[placeholder^='Thesis']", "ADR premium above basis; expect convergence at the Tokyo open.")
        pg.click("text=Publish at live price")
        pg.wait_for_selector("text=Close at live price")
        print("ok trade post")
        b.close()
    real = [e for e in errors if "401" not in e and "402" not in e and "Failed to load resource" not in e]
    if real:
        print("CONSOLE ERRORS:\n" + "\n".join(real))
        sys.exit(1)
    print("E2E PASSED")


if __name__ == "__main__":
    main()
