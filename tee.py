import os, json, time, pathlib, re, shutil
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_URL     = "https://foreupsoftware.com/index.php/booking/20954#/"
LOGIN_URL    = BASE_URL + "login"
ACCOUNT_URL  = BASE_URL + "account"

USER_EMAIL    = os.getenv("FOREUP_EMAIL", "charlesn100@gmail.com")
USER_PASSWORD = os.getenv("FOREUP_PASSWORD", "YgB1h%Cumw9g*6Oa")

PLAYERS = 4
CARTS = False
HOLES_18 = True
LATEST_MINUTES = 2000

MORNING_CUTOFF_MIN = 11 * 60  # 11:00 AM

CLICK_TIMEOUT_MS = 3500
NAV_TIMEOUT_MS   = 18000
FIND_TIMEOUT_MS  = 9000
MAX_POLLS        = 6
POLL_DELAY_SEC   = 2

OUTDIR = "tee_bot_artifacts"
USER_DATA_DIR = ".pw-user"
pathlib.Path(OUTDIR).mkdir(exist_ok=True)

TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\s*(am|pm)\b", re.IGNORECASE)

def ts():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def _next_sunday_from_today():
    today = datetime.now().date()
    days_ahead = (6 - today.weekday()) % 7
    return today + timedelta(days=days_ahead)

TARGET_DATE      = _next_sunday_from_today()
TARGET_DATE_STR  = TARGET_DATE.strftime("%m-%d-%Y")
TARGET_DAY_STR   = str(TARGET_DATE.day)

def parse_time_to_minutes(label):
    s = label.strip().lower()
    is_pm = "pm" in s
    s = s.replace("am", "").replace("pm", "").strip()
    if ":" not in s:
        return 9999
    h, m = s.split(":")
    h = int(h); m = int(m)
    if is_pm and h != 12:
        h += 12
    if (not is_pm) and h == 12:
        h = 0
    return h * 60 + m

def normalize_time_label(raw_text):
    m = TIME_RE.search(raw_text or "")
    if not m:
        return None
    return f"{m.group(1)}{m.group(2).lower()}"

# ---------- profile lock handling ----------

def ensure_profile_not_locked(user_data_dir: str):
    p = pathlib.Path(user_data_dir)
    if not p.exists():
        return
    for name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lf = p / name
        try:
            if lf.exists():
                lf.unlink()
        except Exception:
            pass

# ---------- helpers ----------

def _section(page, label):
    xp = "(//*[self::div or self::section][.//text()[normalize-space()='%s']])[1]" % label
    el = page.locator(f"xpath={xp}").first
    try:
        el.scroll_into_view_if_needed(timeout=1200)
    except Exception:
        pass
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
            try:
                btn.scroll_into_view_if_needed(timeout=800)
            except Exception:
                pass
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
    _click_value_in_section(page, "Time of Day", "All")
    if HOLES_18:
        _click_value_in_section(page, "Holes", "18")
    page.wait_for_timeout(250)
    page.screenshot(path=f"{OUTDIR}/filters_forced_{ts()}.png")

def refresh_grid_without_reload(page):
    _click_value_in_section(page, "Time of Day", "Midday")
    page.wait_for_timeout(150)
    _click_value_in_section(page, "Time of Day", "All")
    page.wait_for_timeout(250)

# ---------- grid readiness + time discovery ----------

def wait_for_grid_ready(page, timeout_ms=15000):
    start = time.time()
    loading_sel = "xpath=//*[contains(normalize-space(),'Loading Tee times')]"
    while (time.time() - start) * 1000 < timeout_ms:
        try:
            loading = page.locator(loading_sel).first
            if loading.count() and loading.is_visible():
                page.wait_for_timeout(250)
                continue
        except Exception:
            pass
        try:
            nodes = page.locator(
                "xpath=//*[contains(.,':') and ("
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'am') or "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pm')"
                ")]"
            )
            if nodes.count() > 0:
                return
        except Exception:
            pass
        page.wait_for_timeout(250)

def list_times_in_grid(page):
    wait_for_grid_ready(page, timeout_ms=15000)

    # THIS matches your DOM: <div class="time time-tile"> ... 4:20pm ...
    tiles = page.locator("css=div.time.time-tile")
    try:
        n = tiles.count()
    except Exception:
        return []

    found = []
    seen = set()

    for i in range(n):
        t = tiles.nth(i)
        try:
            if not t.is_visible():
                continue
        except Exception:
            continue

        try:
            txt = t.inner_text(timeout=700)
        except Exception:
            continue

        label = normalize_time_label(txt)
        if not label:
            continue

        mins = parse_time_to_minutes(label)
        key = (label, mins)
        if key in seen:
            continue
        seen.add(key)

        found.append({"index": i, "minutes": mins, "label": label})

    found.sort(key=lambda x: x["minutes"])
    return found

def print_times(times):
    if not times:
        print("Tee times seen: none")
        return
    print("Tee times seen:")
    for t in times:
        print(f"  - {t['label']}")

def print_morning_status(times):
    if not times:
        return
    has_morning = any(t["minutes"] < MORNING_CUTOFF_MIN for t in times)
    if not has_morning:
        print("No morning tee times available")

def choose_earliest(times):
    if not times:
        return None
    return times[0]

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
            page.locator(sel).first.wait_for(timeout=2500)
            return True
        except Exception:
            continue
    return False

def open_modal(page, idx, label):
    """
    Your DOM shows the clickable card is:
      <div class="time time-tile"> ... <div class="booking-start-time-label">4:20pm</div> ...
    So click div.time.time-tile filtered by label.
    """
    label = (label or "").strip()
    print(f"Clicking card for {label}")

    card = page.locator("css=div.time.time-tile").filter(has_text=label).first
    if not card.count():
        raise RuntimeError(f"Could not find card for {label}")

    card.scroll_into_view_if_needed(timeout=2000)
    page.wait_for_timeout(200)

    # ForeUp sometimes needs a real hover + click
    try:
        card.hover(timeout=1500)
    except Exception:
        pass

    # Try normal click first
    try:
        card.click(timeout=3000)
    except Exception:
        # Fallback: click by coordinates in the middle of the card
        bb = card.bounding_box()
        if not bb:
            raise
        x = bb["x"] + bb["width"] / 2
        y = bb["y"] + bb["height"] / 2
        page.mouse.move(x, y)
        page.wait_for_timeout(80)
        page.mouse.click(x, y, delay=25)

    if not _wait_modal(page):
        page.screenshot(path=f"{OUTDIR}/modal_failed_{ts()}.png")
        raise RuntimeError("Failed to open booking modal")

    page.screenshot(path=f"{OUTDIR}/modal_open_{ts()}.png")

# ---------- booking inside modal ----------

def _modal_root(page):
    for sel in [
        "role=dialog",
        "xpath=//div[contains(@class,'modal') and not(contains(@style,'none'))]",
        "xpath=(//div[contains(@class,'modal')])[last()]",
    ]:
        m = page.locator(sel).first
        if m.count():
            return m
    return page

def modal_click_text(modal, text):
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

    try:
        for label in ["Players", "Player"]:
            sec = modal.locator(
                f"xpath=(.//*[self::div or self::section][.//text()[normalize-space()='{label}']])[1]"
            ).first
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

    if not CARTS:
        if not modal_click_text(modal, "No"):
            try:
                modal.locator("xpath=.//button[contains(.,'No')]").first.click(timeout=1000)
            except Exception:
                pass

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

# ---------- login ----------

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
            user_box = page.locator(
                "input[name='username'], input#username, input[type='text'][placeholder='Username']"
            ).first
            pass_box = page.locator(
                "input[name='password'], input#password, input[type='password'][placeholder='Password']"
            ).first
            user_box.wait_for(timeout=5000)
            pass_box.wait_for(timeout=5000)
            user_box.fill(USER_EMAIL)
            pass_box.fill(USER_PASSWORD)
        except Exception:
            for fr in page.frames:
                try:
                    u = fr.locator("input[placeholder='Username'], input[name='username']").first
                    p = fr.locator("input[placeholder='Password'], input[name='password']").first
                    u.wait_for(timeout=3000)
                    p.wait_for(timeout=3000)
                    u.fill(USER_EMAIL)
                    p.fill(USER_PASSWORD)
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
        ensure_profile_not_locked(USER_DATA_DIR)

        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=os.path.abspath(USER_DATA_DIR),
                headless=False,
                viewport={"width": 1440, "height": 900}
            )
        except Exception:
            fresh = f"{USER_DATA_DIR}-{ts()}"
            pathlib.Path(fresh).mkdir(exist_ok=True)
            print(f"Profile was locked, using fresh profile: {fresh}")
            context = p.chromium.launch_persistent_context(
                user_data_dir=os.path.abspath(fresh),
                headless=False,
                viewport={"width": 1440, "height": 900}
            )

        context.set_default_timeout(7000)
        page = context.new_page()

        login(page)
        click_online_teetimes(page)
        force_filters(page)

        chosen = None
        last_times = []

        for poll_i in range(MAX_POLLS):
            ensure_auth_or_relogin(page)

            times = list_times_in_grid(page)
            last_times = times

            print(f"Poll {poll_i + 1}/{MAX_POLLS}")
            print_times(times)
            print_morning_status(times)

            chosen = choose_earliest(times)
            if chosen:
                break

            refresh_grid_without_reload(page)
            time.sleep(POLL_DELAY_SEC)

        if not chosen:
            if last_times:
                print_times(last_times)
                print_morning_status(last_times)
            print("No tee times")
            context.close()
            return

        print(f"Choosing: {chosen['label']}")

        open_modal(page, chosen["index"], chosen["label"])

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
                        click_online_teetimes(page)
                        force_filters(page)
                        open_modal(page, chosen["index"], chosen["label"])
                    else:
                        print("Booking failed")
            except Exception as e:
                if attempt == 0:
                    click_online_teetimes(page)
                    force_filters(page)
                    open_modal(page, chosen["index"], chosen["label"])
                else:
                    print(f"Booking failed: {e}")

        context.close()

if __name__ == "__main__":
    run()
