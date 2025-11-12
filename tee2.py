import os, json, time, pathlib
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_URL     = "https://foreupsoftware.com/index.php/booking/20954#/"
LOGIN_URL    = BASE_URL + "login"
ACCOUNT_URL  = BASE_URL + "account"

USER_EMAIL    = os.getenv("FOREUP_EMAIL", "andrewmeng14@gmail.com")
USER_PASSWORD = os.getenv("FOREUP_PASSWORD", "danliu0501A$")

PLAYERS = 4
CARTS = False          # No cart as requested
HOLES_18 = True
LATEST_MINUTES = 2000  # accept any time, pick earliest

CLICK_TIMEOUT_MS = 3500
NAV_TIMEOUT_MS   = 18000
FIND_TIMEOUT_MS  = 5000
MAX_POLLS        = 6
POLL_DELAY_SEC   = 2

OUTDIR = "tee_bot_artifacts"
USER_DATA_DIR = ".pw-user"
pathlib.Path(OUTDIR).mkdir(exist_ok=True)

def ts():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# ====== NEW: compute closest Sunday once at import ======

def _next_sunday_from_today():
    """Closest upcoming Sunday, including today if today is Sunday."""
    today = datetime.now().date()
    # Monday = 0, Sunday = 6
    days_ahead = (6 - today.weekday()) % 7
    return today + timedelta(days=days_ahead)

TARGET_DATE      = _next_sunday_from_today()
TARGET_DATE_STR  = TARGET_DATE.strftime("%m-%d-%Y")
TARGET_DAY_STR   = str(TARGET_DATE.day)

# ===============================================

def parse_time_to_minutes(label):
    s = label.strip().lower()
    is_pm = "pm" in s
    s = s.replace("am","").replace("pm","").strip()
    if ":" not in s:
        return 9999
    h, m = s.split(":")
    h = int(h); m = int(m)
    if is_pm and h != 12: h += 12
    if (not is_pm) and h == 12: h = 0
    return h*60 + m

# ---------- helpers ----------

def _section(page, label):
    xp = "(//*[self::div or self::section][.//text()[normalize-space()='%s']])[1]" % label
    el = page.locator(f"xpath={xp}").first
    try: el.scroll_into_view_if_needed(timeout=1200)
    except Exception: pass
    return el

def _click_value_in_section(page, section_label, value_text):
    sec = _section(page, section_label)
    selectors = [
        f".//button[normalize-space()='{value_text}']",
        f".//a[normalize-space()='{value_text}']",
        f".//div[normalize-space()='{value_text}']",
        f".//*[contains(@class,'btn') and normalize-space()='{value_text}']",
        f".//*[contains(@class,'button') and normalize-space()='{value_text}']",
    ]
    for rel in selectors:
        try:
            btn = sec.locator(f"xpath={rel}").first
            if not btn.count():
                continue
            try: btn.scroll_into_view_if_needed(timeout=800)
            except Exception: pass
            try:
                btn.click(timeout=1200)
            except Exception:
                try:
                    btn.evaluate("e => e.click()")
                except Exception:
                    continue
            return True
        except Exception:
            continue
    return False

def click_online_teetimes(page):
    page.goto(BASE_URL, timeout=NAV_TIMEOUT_MS)
    page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
    try:
        page.get_by_role("button", name="Online Tee Times").click(timeout=5000)
    except Exception:
        page.locator("button:has-text('Online Tee Times'), a:has-text('Online Tee Times')").first.click(timeout=5000)
    page.wait_for_timeout(400)

def set_date(page):
    # CHANGED: use TARGET_DATE_STR and TARGET_DAY_STR instead of hardcoded date
    try:
        date_input = page.locator("input[placeholder='Date']").first
        date_input.click()
        date_input.fill(TARGET_DATE_STR)
        page.keyboard.press("Enter")
    except Exception:
        try:
            page.locator(f"//td[normalize-space()='{TARGET_DAY_STR}']").first.click()
        except Exception:
            pass

def force_filters(page):
    set_date(page)
    _click_value_in_section(page, "Players", "4")
    _click_value_in_section(page, "Time of Day", "Midday")
    if HOLES_18:
        _click_value_in_section(page, "Holes", "18")
    page.wait_for_timeout(250)
    page.screenshot(path=f"{OUTDIR}/filters_forced_{ts()}.png")

def refresh_grid_without_reload(page):
    _click_value_in_section(page, "Time of Day", "All")
    page.wait_for_timeout(150)
    _click_value_in_section(page, "Time of Day", "Midday")
    page.wait_for_timeout(250)

def find_earliest(page):
    tiles = page.locator("//div[contains(@class,'tee') or contains(@class,'time') or contains(@class,'card')]")
    n = tiles.count()
    best = None
    for i in range(n):
        t = tiles.nth(i)
        if not t.is_visible():
            continue
        try:
            txt = t.inner_text(timeout=300)
        except Exception:
            continue
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        if not lines:
            continue
        token = lines[0].split()[0]
        mins = parse_time_to_minutes(token)
        if mins < LATEST_MINUTES:
            if best is None or mins < best["minutes"]:
                best = {"index": i, "minutes": mins, "label": token}
    return best

# ---------- modal open ----------

def _wait_modal(page):
    selectors = [
        "role=dialog",
        "xpath=//div[contains(@class,'modal') and contains(@style,'display')]",
        "xpath=//div[contains(@class,'modal') and not(contains(@style,'none'))]",
        "button:has-text('Book Time')",
        "xpath=//div[contains(.,'held for 5 minutes')]",
    ]
    for sel in selectors:
        try:
            page.locator(sel).first.wait_for(timeout=1200)
            return True
        except Exception:
            continue
    return False

def _strong_js_click(page, locator):
    locator.evaluate("""
      el => {
        el.scrollIntoView({block: 'center', inline: 'center'});
        const r = el.getBoundingClientRect();
        const fire = (type) => el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:r.left+r.width/2,clientY:r.top+Math.min(24, r.height/3)}));
        ['pointerover','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
      }
    """)

def open_modal(page, idx):
    tiles = page.locator("//div[contains(@class,'tee') or contains(@class,'time') or contains(@class,'card')]")
    tile = tiles.nth(idx)

    # Try inner controls first
    for xp in [
        ".//button[contains(.,'Book') or contains(.,'Select')]",
        ".//a[contains(.,'Book') or contains(.,'Select')]",
        ".//*[contains(@class,'btn') and (contains(.,'Book') or contains(.,'Select'))]",
        ".//*[contains(@class,'time') or contains(@class,'title')][1]",
    ]:
        try:
            el = tile.locator(f"xpath={xp}").first
            if el.count() and el.is_visible():
                try:
                    el.click(timeout=900)
                except Exception:
                    _strong_js_click(page, el)
                if _wait_modal(page):
                    page.screenshot(path=f"{OUTDIR}/modal_open_{ts()}.png")
                    return
        except Exception:
            continue

    # Center click fallback
    try:
        bb = tile.bounding_box()
        if bb:
            cx = bb["x"] + bb["width"]/2
            cy = bb["y"] + min(24, bb["height"]/3)
            page.mouse.click(cx, cy, delay=15)
            if _wait_modal(page):
                page.screenshot(path=f"{OUTDIR}/modal_open_{ts()}.png")
                return
            page.mouse.dblclick(cx, cy, delay=15)
            if _wait_modal(page):
                page.screenshot(path=f"{OUTDIR}/modal_open_{ts()}.png")
                return
    except Exception:
        pass

    # JS synth events on the tile
    try:
        _strong_js_click(page, tile)
        if _wait_modal(page):
            page.screenshot(path=f"{OUTDIR}/modal_open_{ts()}.png")
            return
    except Exception:
        pass

    # Keyboard fallback
    try:
        tile.focus()
        page.keyboard.press("Enter")
        if _wait_modal(page):
            page.screenshot(path=f"{OUTDIR}/modal_open_{ts()}.png")
            return
        page.keyboard.press("Space")
        if _wait_modal(page):
            page.screenshot(path=f"{OUTDIR}/modal_open_{ts()}.png")
            return
    except Exception:
        pass

    page.screenshot(path=f"{OUTDIR}/modal_failed_{ts()}.png")
    raise RuntimeError("Failed to open booking modal")

# ---------- booking inside modal ----------

def _modal_root(page):
    # pick the topmost visible modal/dialog
    for sel in [
        "role=dialog",
        "xpath=//div[contains(@class,'modal') and not(contains(@style,'none'))]",
        "xpath=(//div[contains(@class,'modal')])[last()]",
    ]:
        m = page.locator(sel).first
        if m.count():
            return m
    return page  # fallback

def modal_click_text(modal, text):
    # clicks a button/link/div with matching text within the modal
    for sel in [
        f"xpath=.//button[normalize-space()='{text}']",
        f"xpath=.//a[normalize-space()='{text}']",
        f"xpath=.//div[normalize-space()='{text}']",
        f"xpath=.//*[contains(@class,'btn') and normalize-space()='{text}']",
    ]:
        el = modal.locator(sel).first
        if el.count() and el.is_visible():
            try:
                el.click(timeout=1200)
            except Exception:
                try:
                    el.evaluate("e => e.click()")
                except Exception:
                    continue
            return True
    return False

def book_modal(page):
    modal = _modal_root(page)

    # Players = 4 in modal
    try:
        for label in ["Players", "Player"]:
            sec = modal.locator(f"xpath=(.//*[self::div or self::section][.//text()[normalize-space()='{label}']])[1]").first
            if sec.count():
                for sel in [
                    "xpath=.//button[normalize-space()='4']",
                    "xpath=.//a[normalize-space()='4']",
                    "xpath=.//div[normalize-space()='4']",
                ]:
                    el = sec.locator(sel).first
                    if el.count():
                        try:
                            el.click(timeout=1000)
                            raise StopIteration
                        except Exception:
                            try:
                                el.evaluate("e => e.click()")
                                raise StopIteration
                            except Exception:
                                pass
    except StopIteration:
        pass

    # Cart = No
    if not CARTS:
        if not modal_click_text(modal, "No"):
            try:
                modal.locator("xpath=.//button[contains(.,'No')]").first.click(timeout=1000)
            except Exception:
                pass

    # Check any agree/terms toggles
    for sel in [
        "xpath=.//input[@type='checkbox']",
        "xpath=.//label[contains(.,'agree')]",
        "xpath=.//label[contains(.,'terms')]",
    ]:
        try:
            el = modal.locator(sel).first
            if el.count() and el.is_visible():
                try:
                    if el.evaluate("e => e.tagName.toLowerCase()==='input' ? !e.checked : false"):
                        el.check(timeout=800)
                    else:
                        el.click(timeout=800)
                except Exception:
                    try:
                        el.evaluate("e => e.click()")
                    except Exception:
                        pass
        except Exception:
            continue

    # Click green Book Time
    clicked = False
    for sel in [
        "xpath=.//button[contains(@class,'green') and contains(.,'Book Time')]",
        "xpath=.//button[contains(.,'Book Time')]",
        "xpath=.//a[contains(.,'Book Time')]",
        "xpath=.//div[contains(.,'Book Time') and (contains(@class,'btn') or contains(@class,'button'))]",
        "button:has-text('Book Time')",
    ]:
        try:
            el = modal.locator(sel).first
            if el.count() and el.is_visible():
                try:
                    el.click(timeout=1500)
                except Exception:
                    try:
                        el.evaluate("e => e.click()")
                    except Exception:
                        continue
                clicked = True
                break
        except Exception:
            continue

    page.screenshot(path=f"{OUTDIR}/after_book_click_{ts()}.png")
    if not clicked:
        raise RuntimeError("Book Time button not clicked")

# ---------- auth and verify ----------

def saw_login_toast(page) -> bool:
    try:
        toast = page.locator("xpath=//div[contains(@class,'alert') or contains(@class,'toast')]").first
        if toast.count():
            txt = toast.inner_text(timeout=400).lower()
            if "must be logged in" in txt or "logged in to access" in txt:
                return True
    except Exception:
        pass
    return False

def ensure_auth_or_relogin(page):
    unauth = saw_login_toast(page) or page.locator("text=Log In").first.count() > 0
    if unauth:
        login(page)
        click_online_teetimes(page)
        force_filters(page)

def verify_account(page):
    page.goto(ACCOUNT_URL, timeout=NAV_TIMEOUT_MS)
    body = page.locator("body").inner_text()
    return "Reserve a time now." not in body

# ---------- original login ----------

def login(page):
    page.goto(LOGIN_URL, timeout=NAV_TIMEOUT_MS)
    page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
    try:
        user_box = page.get_by_placeholder("Username")
        pass_box = page.get_by_placeholder("Password")
        user_box.wait_for(timeout=5000)
        pass_box.wait_for(timeout=5000)
        user_box.fill(USER_EMAIL)
        pass_box.fill(USER_PASSWORD)
    except Exception:
        try:
            user_box = page.locator("input[name='username'], input#username, input[type='text'][placeholder='Username']").first
            pass_box = page.locator("input[name='password'], input#password, input[type='password'][placeholder='Password']").first
            user_box.wait_for(timeout=5000)
            pass_box.wait_for(timeout=5000)
            user_box.fill(USER_EMAIL)
            pass_box.fill(USER_PASSWORD)
        except Exception:
            for fr in page.frames:
                try:
                    u = fr.locator("input[placeholder='Username'], input[name='username']").first
                    p = fr.locator("input[placeholder='Password'], input[name='password']").first
                    u.wait_for(timeout=3000); p.wait_for(timeout=3000)
                    u.fill(USER_EMAIL); p.fill(USER_PASSWORD)
                    break
                except Exception:
                    continue
    try:
        page.get_by_role("button", name="SIGN IN").click(timeout=4000)
    except Exception:
        try:
            page.locator("button:has-text('SIGN IN'), input[type='submit']").first.click(timeout=4000)
        except Exception:
            pass
    page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    page.screenshot(path=f"{OUTDIR}/after_login_{ts()}.png")

# ---------- main ----------

def run():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=os.path.abspath(USER_DATA_DIR),
            headless=False,
            viewport={"width":1440,"height":900}
        )
        context.set_default_timeout(7000)
        page = context.new_page()

        login(page)
        click_online_teetimes(page)
        force_filters(page)

        chosen = None
        for _ in range(MAX_POLLS):
            ensure_auth_or_relogin(page)
            chosen = find_earliest(page)
            if chosen:
                break
            refresh_grid_without_reload(page)
            time.sleep(POLL_DELAY_SEC)

        if not chosen:
            print("No tee times")
            context.close()
            return

        open_modal(page, chosen["index"])

        # Booking with one safe retry on failure
        for attempt in range(2):
            try:
                ensure_auth_or_relogin(page)
                book_modal(page)
                time.sleep(1.0)
                ok = verify_account(page)
                if ok:
                    print("Reservation booked")
                    break
                else:
                    if attempt == 0:
                        # try once more: reopen tee sheet and reapply filters
                        click_online_teetimes(page)
                        force_filters(page)
                        open_modal(page, chosen["index"])
                    else:
                        print("Booking failed")
            except Exception as e:
                if attempt == 0:
                    click_online_teetimes(page)
                    force_filters(page)
                    open_modal(page, chosen["index"])
                else:
                    print(f"Booking failed: {e}")

        context.close()

if __name__ == "__main__":
    run()
