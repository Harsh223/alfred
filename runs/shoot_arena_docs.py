"""Screenshots of /arena (dark + light, desktop + phone), the arena join result, and /api/docs (dark + light). App must be up on :8080."""
import asyncio, sys
from playwright.async_api import async_playwright
B = "http://127.0.0.1:8080"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = "runs/screens/"


async def shot(br, path, name, theme, w=1440, h=900, full=True, wait=600, after=None):
    ctx = await br.new_context(viewport={"width": w, "height": h}, color_scheme=theme, device_scale_factor=1 if w > 600 else 2)
    pg = await ctx.new_page()
    await pg.add_init_script(f"try{{localStorage.setItem('alfred-theme','{theme}')}}catch(e){{}}")
    await pg.goto(B + path); await pg.wait_for_timeout(wait)
    if after:
        await after(pg)
    await pg.screenshot(path=f"{OUT}{name}.png", full_page=full); await ctx.close()


async def open_op(pg):
    await pg.wait_for_selector(".opblock", timeout=20000)
    await pg.click("#operations-Brain-ask_v1_ask_post .opblock-summary-control")
    await pg.wait_for_timeout(500)


async def main():
    which = sys.argv[1:] or ["arena", "docs"]
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, headless=True)
        if "arena" in which:
            for t in ("dark", "light"):
                await shot(br, "/arena", f"arena_{t}", t)
                await shot(br, "/arena", f"arena_{t}_phone", t, w=390, h=844)
        if "docs" in which:
            for t in ("dark", "light"):
                await shot(br, "/api/docs", f"api_docs_{t}", t, wait=2500, after=open_op)
            await shot(br, "/api/docs", "api_docs_dark_phone", "dark", w=390, h=844, wait=2500)
        await br.close()




async def joined():
    """Join page (keys shown once) + breach form, dark + light. Registers a throwaway team; remove it afterwards with DELETE /v1/arena/teams/{team}."""
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, headless=True)
        for t in ("dark", "light"):
            ctx = await br.new_context(viewport={"width": 1440, "height": 900}, color_scheme=t)
            pg = await ctx.new_page(); await pg.add_init_script(f"try{{localStorage.setItem('alfred-theme','{t}')}}catch(e){{}}")
            await pg.goto(B + "/arena"); await pg.fill("#team", f"Screenshot Crew {t}"); await pg.click(".a-joinf button")
            await pg.wait_for_timeout(700); await pg.screenshot(path=f"{OUT}arena_joined_{t}.png", full_page=True)
            await pg.goto(B + "/arena"); await pg.evaluate("document.querySelector('form[action=\"/arena/play\"]')")
            await pg.goto(B + "/arena/breach"); await pg.wait_for_timeout(300)
            await ctx.close()
        await br.close()


if __name__ == "__main__":
    asyncio.run(joined() if sys.argv[1:] == ["joined"] else main())
