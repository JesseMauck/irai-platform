"""Browser end-to-end test (Playwright). Needs the backend on :8000 and frontend on :3000.
Run:  python e2e/test_e2e.py [base_url] [screenshot_dir]"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
OUT = sys.argv[2] if len(sys.argv) > 2 else "e2e-screenshots"
PAGES = ["/", "/monitor/adr", "/monitor/adr/TM", "/monitor/etf", "/monitor/fundamental", "/monitor/pairs", "/ticker/NVDA",
         "/research", "/research/reading-the-adr-basis", "/screeners", "/community", "/trades", "/leaderboards", "/learn",
         "/pricing", "/methodology", "/valuebot", "/lab", "/forgot", "/login", "/signup"]


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
        pg.click("text=Market size")  # Refine step: market sizing drives revenue growth
        boxes = pg.locator("text=Total market today").locator("input")
        boxes.fill("60")
        pg.locator("text=Year-10 market share").locator("input").fill("15")
        pg.locator("text=Market growth").locator("input").fill("8")
        pg.click("text=Run valuation")
        pg.wait_for_function("/^\\/valuebot\\/2/.test(location.pathname)")
        t0 = time.time()
        pg.wait_for_selector("text=Value / share", timeout=180_000)
        pg.wait_for_timeout(800)
        pg.screenshot(path=f"{OUT}/valuebot_report.png", full_page=True)
        print(f"ok valuebot run with market sizing ({time.time() - t0:.0f}s)")
        assert "market" in pg.inner_text("body").lower()

        # Strategy Lab backtest (StockSharp port)
        pg.goto(BASE + "/lab?symbol=AAPL", wait_until="networkidle")
        pg.click("text=Run backtest")
        pg.wait_for_selector("text=Equity vs buy-and-hold", timeout=30_000)
        pg.screenshot(path=f"{OUT}/lab.png", full_page=True)
        print("ok strategy lab backtest")

        # custom screen (Essential)
        pg.goto(BASE + "/screeners", wait_until="networkidle")
        pg.locator("text=RV percentile ≥").locator("input").fill("50")
        pg.click("text=Preview")
        pg.wait_for_selector("text=Saved screens")
        print("ok custom screen preview")

        # trade post captures live price
        pg.goto(BASE + "/trades", wait_until="networkidle")
        pg.fill("input[placeholder='Long ticker']", "TM")
        pg.fill("input[placeholder='Short leg (optional)']", "7203.T")
        pg.fill("input[placeholder^='Thesis']", "ADR premium above basis; expect convergence at the Tokyo open.")
        pg.click("text=Publish at live price")
        pg.wait_for_selector("text=Close at live price")
        print("ok trade post")

        # admin console
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ad = ctx.new_page()
        ad.on("pageerror", lambda e: errors.append(f"{ad.url}: {e}"))
        ad.goto(BASE + "/login")
        ad.fill("input[type=email]", "admin@irai-demo.com")
        ad.fill("input[type=password]", "irai-demo-2026")
        ad.click("button[type=submit]")
        ad.wait_for_function("location.pathname === '/account'")
        ad.goto(BASE + "/admin", wait_until="networkidle")
        ad.wait_for_selector("text=Members by plan")
        for tab in ("Users", "Articles", "Coverage", "Moderation"):
            ad.click(f"button:has-text('{tab}')")
            ad.wait_for_timeout(400)
        ad.screenshot(path=f"{OUT}/admin.png")
        ad.goto(BASE + "/monitor/pairs", wait_until="networkidle")
        ad.wait_for_selector("main >> text=Cheap for quality")  # (the header menu also mentions score spreads, hidden)
        print("ok admin console + pair ideas (Pro)")
        b.close()
    real = [e for e in errors if "401" not in e and "402" not in e and "Failed to load resource" not in e]
    if real:
        print("CONSOLE ERRORS:\n" + "\n".join(real))
        sys.exit(1)
    print("E2E PASSED")


if __name__ == "__main__":
    main()
