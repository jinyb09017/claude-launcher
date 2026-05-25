from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:8765')
    page.wait_for_load_state('networkidle')

    all_tab = page.locator('[data-tab="all"]')
    all_tab.click()
    page.wait_for_timeout(1000)
    page.screenshot(path='/tmp/recon_all.png', full_page=True)

    cards = page.locator('.proj-card').all()
    print('proj-card count:', len(cards))

    # Try other selectors
    all_items = page.locator('.proj-row, .card, [class*="proj"]').all()
    print('proj* items:', len(all_items))

    # Dump partial HTML to understand structure
    html = page.locator('#all-list, #proj-list, .list, main').first.inner_html()
    print('list html (first 800):', html[:800])

    browser.close()
