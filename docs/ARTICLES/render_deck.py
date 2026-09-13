import asyncio
import os
from playwright.async_api import async_playwright

async def render():
    base_dir = "/home/pedrogriff/people-agent-mesh/docs/ARTICLES"
    html_file = os.path.join(base_dir, "architecting-enterprise-multi-agent-governance-deck.html")
    pdf_file = os.path.join(base_dir, "architecting-enterprise-multi-agent-governance-deck.pdf")
    slides_dir = os.path.join(base_dir, "slides")
    os.makedirs(slides_dir, exist_ok=True)

    print(f"Loading {html_file}...")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # Viewport with high device scale factor for crystal-clear retina rendering
        page = await browser.new_page(
            viewport={"width": 1200, "height": 1600},
            device_scale_factor=2
        )
        await page.goto(f"file://{html_file}")
        # Wait for web fonts (Plus Jakarta Sans, JetBrains Mono) to load
        await page.wait_for_timeout(2500)

        # 1. Screenshot each slide to PNG
        slides = await page.query_selector_all(".slide-wrapper")
        print(f"Found {len(slides)} slides.")
        for i, s in enumerate(slides):
            out_png = os.path.join(slides_dir, f"slide_{i+1:02d}.png")
            await s.screenshot(path=out_png)
            print(f"Saved {out_png}")

        # 2. Export pixel-perfect 1080x1350 PDF
        print("Generating PDF...")
        await page.pdf(
            path=pdf_file,
            width="1080px",
            height="1350px",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            prefer_css_page_size=True
        )
        print(f"Exported PDF successfully to {pdf_file}!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(render())
