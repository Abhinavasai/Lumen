"""
Browser-based auto-apply using Playwright with the user's real Chrome profile.

Uses launch_persistent_context with channel="chrome" to open the user's actual
Chrome profile — cookies, extensions, Google login, and reCAPTCHA trust history
are all preserved. Chrome is auto-killed before launch (only one process can
hold the profile lock) and re-opened afterward.
"""

import os
import re
import shutil
import sys
import time
import random
import subprocess
import imaplib
from datetime import datetime, timedelta
from email.header import decode_header
import email as email_lib

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

CANDIDATE = {
    "first_name": os.getenv("CANDIDATE_FIRST_NAME", ""),
    "last_name": os.getenv("CANDIDATE_LAST_NAME", ""),
    "full_name": "",
    "email": os.getenv("CANDIDATE_EMAIL", ""),
    "phone": os.getenv("CANDIDATE_PHONE", ""),
    "linkedin": os.getenv("CANDIDATE_LINKEDIN", ""),
    "github": os.getenv("CANDIDATE_GITHUB", ""),
    "website": os.getenv("CANDIDATE_WEBSITE", ""),
    "location": os.getenv("CANDIDATE_LOCATION", ""),
    "current_company": os.getenv("CANDIDATE_COMPANY", ""),
    "current_title": os.getenv("CANDIDATE_TITLE", ""),
}
CANDIDATE["full_name"] = f"{CANDIDATE['first_name']} {CANDIDATE['last_name']}"

GMAIL_USER = os.getenv("GMAIL_USER", CANDIDATE["email"])
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

CHROME_USER_DATA = os.getenv(
    "CHROME_USER_DATA",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
)
CHROME_APPLY_DATA = os.path.expandvars(r"%LOCALAPPDATA%\ChromeAutoApply")

PROFILE_PATH = os.path.join(BASE_DIR, "profile.txt")
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")


# ─────────────────────────────────────────────────────────────────────────
#  AI answer generation for custom screening questions
# ─────────────────────────────────────────────────────────────────────────

def _get_ai_client():
    """Build an OpenAI/Azure client reusing the project's config.
    Returns (client, model, provider) where provider is 'openai' or 'azure'."""
    try:
        from openai import OpenAI, AzureOpenAI
    except ImportError:
        return None, None, None

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        return OpenAI(api_key=openai_key), "gpt-4o", "openai"

    try:
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        az = cfg.get("azure_openai", {})
        endpoint = az.get("endpoint")
        deployment = az.get("deployment")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if endpoint and deployment and api_key:
            return (
                AzureOpenAI(
                    azure_endpoint=endpoint,
                    api_key=api_key,
                    api_version="2025-03-01-preview",
                ),
                deployment,
                "azure",
            )
    except Exception:
        pass
    return None, None, None


def _load_profile() -> str:
    if os.path.isfile(PROFILE_PATH):
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return f.read()
    return ""


def _answer_question(question: str, job_url: str = "") -> str | None:
    """Use AI to generate a short, first-person answer to a screening question."""
    client, model, provider = _get_ai_client()
    if not client:
        return None

    profile = _load_profile()
    system_msg = (
        "You are filling out a job application on behalf of a candidate. "
        "Answer the screening question in first person, as the candidate. "
        "Be concise (2-4 sentences for open-ended questions, 1 sentence for simple ones). "
        "Sound natural and genuine — not generic or overly polished. "
        "Draw from the candidate's actual experience when relevant. "
        "Return ONLY the answer text — no quotes, no preamble."
    )
    user_msg = f"CANDIDATE PROFILE:\n{profile}\n\n"
    if job_url:
        user_msg += f"JOB URL: {job_url}\n\n"
    user_msg += f"QUESTION: {question}\n\nANSWER:"

    try:
        if provider == "azure":
            resp = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            )
            answer = (resp.output_text or "").strip()
        else:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=200,
                temperature=0.7,
            )
            answer = resp.choices[0].message.content.strip()

        answer = answer.removeprefix('"').removesuffix('"')
        answer = answer.encode("ascii", "replace").decode("ascii")
        return answer if answer else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────
#  Stealth JS — masks Playwright automation markers so sites see a real
#  Chrome browser instead of a bot.
# ─────────────────────────────────────────────────────────────────────────

STEALTH_JS = """
() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });

    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ],
    });

    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });

    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );

    window.chrome = { runtime: {} };
}
"""


# ─────────────────────────────────────────────────────────────────────────
#  Gmail OTP
# ─────────────────────────────────────────────────────────────────────────

def _fetch_otp_from_gmail(sender_hint: str = "", max_wait: int = 90) -> str | None:
    if not GMAIL_APP_PASSWORD:
        return None
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    except Exception:
        return None

    cutoff = datetime.utcnow() - timedelta(minutes=3)
    date_str = cutoff.strftime("%d-%b-%Y")

    for _ in range(max_wait // 10):
        try:
            imap.select("INBOX")
            _, msg_ids = imap.search(None, f'(SINCE "{date_str}" UNSEEN)')
            if not msg_ids[0]:
                time.sleep(10)
                continue
            for msg_id in reversed(msg_ids[0].split()):
                _, msg_data = imap.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                from_addr = msg.get("From", "").lower()
                raw_subject = msg.get("Subject", "")
                subject = ""
                if raw_subject:
                    decoded = decode_header(raw_subject)
                    subject = "".join(
                        p.decode(e or "utf-8") if isinstance(p, bytes) else p
                        for p, e in decoded
                    )
                if sender_hint and sender_hint.lower() not in from_addr and sender_hint.lower() not in subject.lower():
                    continue
                body = _get_email_body(msg)
                code = _extract_code(body)
                if code:
                    imap.store(msg_id, "+FLAGS", "\\Seen")
                    imap.logout()
                    return code
            time.sleep(10)
        except Exception:
            time.sleep(10)
    try:
        imap.logout()
    except Exception:
        pass
    return None


def _get_email_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload:
                    text = payload.decode("utf-8", errors="replace")
                    if ct == "text/html":
                        from bs4 import BeautifulSoup
                        return BeautifulSoup(text, "html.parser").get_text(" ")
                    return text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")
    return ""


def _extract_code(text: str) -> str | None:
    for pattern in [
        r"(?:verification|confirm|code|pin|otp)[:\s]*(\d{4,8})",
        r"(\d{4,8})\s*(?:is your|verification|code|confirm)",
        r"\b(\d{6})\b",
    ]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


# ─────────────────────────────────────────────────────────────────────────
#  Human-like helpers
# ─────────────────────────────────────────────────────────────────────────

def _pause(lo=0.5, hi=1.5):
    time.sleep(random.uniform(lo, hi))


def _human_move(page, target_loc):
    """Move mouse to the target element with realistic intermediate steps."""
    try:
        box = target_loc.bounding_box()
        if not box:
            return
        tx = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
        ty = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
        steps = random.randint(5, 12)
        page.mouse.move(tx, ty, steps=steps)
        _pause(0.05, 0.15)
    except Exception:
        pass


def _human_scroll(page, distance=300):
    """Scroll down naturally like a human reading the page."""
    for _ in range(random.randint(2, 4)):
        page.mouse.wheel(0, random.randint(100, distance))
        _pause(0.3, 0.8)


def _human_type(locator, text: str):
    """Click into field, clear it, then type character by character with
    variable inter-key delays to mimic a real person."""
    locator.click()
    _pause(0.2, 0.4)
    locator.fill("")
    for ch in text:
        locator.type(ch, delay=0)
        time.sleep(random.uniform(0.04, 0.12))
    _pause(0.2, 0.5)


CDP_PORT = int(os.getenv("CDP_PORT", "9222"))


def _cdp_available() -> bool:
    """Check if Chrome is listening on the CDP debugging port."""
    import urllib.request
    try:
        req = urllib.request.urlopen(
            f"http://localhost:{CDP_PORT}/json/version", timeout=2
        )
        req.close()
        return True
    except Exception:
        return False


CHROME_EXE = os.getenv(
    "CHROME_EXE",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)


def _kill_chrome() -> bool:
    """Kill all Chrome processes so we can take over the profile lock."""
    if sys.platform == "win32":
        r = subprocess.run(
            ["taskkill", "/F", "/IM", "chrome.exe"],
            capture_output=True, timeout=10,
        )
        killed = r.returncode == 0
    else:
        r = subprocess.run(["pkill", "-f", "chrome"], capture_output=True, timeout=10)
        killed = r.returncode == 0
    if killed:
        time.sleep(2)
    return killed


def _relaunch_chrome():
    """Reopen Chrome normally so the user can browse."""
    if os.path.exists(CHROME_EXE):
        subprocess.Popen(f'start "" "{CHROME_EXE}"', shell=True)


def _sync_profile(log):
    """Copy essential files from the real Chrome profile to the auto-apply
    profile directory. Must be called while Chrome is NOT running."""
    src = CHROME_USER_DATA
    dst = CHROME_APPLY_DATA

    os.makedirs(os.path.join(dst, "Default"), exist_ok=True)

    essentials = [
        "Local State",
        os.path.join("Default", "Cookies"),
        os.path.join("Default", "Cookies-journal"),
        os.path.join("Default", "Preferences"),
        os.path.join("Default", "Secure Preferences"),
        os.path.join("Default", "Web Data"),
        os.path.join("Default", "Web Data-journal"),
        os.path.join("Default", "Login Data"),
        os.path.join("Default", "Login Data-journal"),
    ]

    copied = 0
    for fname in essentials:
        src_path = os.path.join(src, fname)
        dst_path = os.path.join(dst, fname)
        if os.path.isfile(src_path):
            try:
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
                copied += 1
            except Exception:
                pass

    ls_src = os.path.join(src, "Default", "Local Storage")
    ls_dst = os.path.join(dst, "Default", "Local Storage")
    if os.path.isdir(ls_src):
        try:
            if os.path.exists(ls_dst):
                shutil.rmtree(ls_dst, ignore_errors=True)
            shutil.copytree(ls_src, ls_dst)
            copied += 1
        except Exception:
            pass

    log(f"Synced {copied} profile items to auto-apply profile")


def _ensure_cdp_chrome(log) -> bool:
    """Ensure Chrome is running with CDP on the debug port.
    Kills Chrome, syncs profile to a non-default dir (Chrome 150 requires
    this for remote debugging), then relaunches with CDP enabled."""
    if _cdp_available():
        return True

    log("Restarting Chrome with debug port for auto-apply...")
    _kill_chrome()

    if not os.path.exists(CHROME_EXE):
        log(f"Chrome not found at {CHROME_EXE}")
        return False

    _sync_profile(log)

    cmd = (
        f'start "" "{CHROME_EXE}"'
        f' --user-data-dir="{CHROME_APPLY_DATA}"'
        f" --remote-debugging-port={CDP_PORT}"
        f" --remote-allow-origins=*"
        f" --disable-blink-features=AutomationControlled"
        f" --no-first-run"
    )
    subprocess.Popen(cmd, shell=True)

    for i in range(20):
        time.sleep(1)
        if _cdp_available():
            log(f"Chrome CDP ready on port {CDP_PORT}")
            return True
        if i == 5:
            log("Waiting for Chrome CDP port...")

    log("Chrome started but CDP port did not open")
    return False


def _get_field_label(page, locator) -> str:
    """Get the label text for a form field by checking label[for], aria-label, and placeholder."""
    try:
        iid = locator.get_attribute("id") or ""
        if iid:
            lbl = page.locator(f"label[for='{iid}']")
            if lbl.count():
                return lbl.first.inner_text().strip()
        aria = locator.get_attribute("aria-label") or ""
        if aria:
            return aria
        return locator.get_attribute("placeholder") or ""
    except Exception:
        return ""


def _get_question_text(page, field_locator) -> str:
    """Find the question text associated with a form field by checking parent
    container for label/legend/heading text."""
    try:
        return field_locator.evaluate("""el => {
            // Walk up to find the field's container (Ashby wraps each in a div)
            let container = el.closest('[class*="field"], [class*="question"], [data-testid]');
            if (!container) {
                container = el.parentElement?.parentElement || el.parentElement;
            }
            if (!container) return '';

            // Look for label, legend, or bold/heading text in the container
            const candidates = container.querySelectorAll('label, legend, h3, h4, p, span');
            for (const c of candidates) {
                const txt = c.textContent.trim();
                if (txt.length > 10 && txt.length < 500 && txt !== el.value) {
                    return txt;
                }
            }
            return '';
        }""")
    except Exception:
        return _get_field_label(page, field_locator)


def _fill_field(page, selector_or_loc, value: str, label: str, log):
    """Fill a field only if it's currently empty."""
    try:
        loc = selector_or_loc if hasattr(selector_or_loc, 'count') else page.locator(selector_or_loc)
        if not loc.count():
            return False
        current = loc.first.input_value()
        if current.strip():
            log(f"  '{label}' already has value: '{current[:30]}'")
            return True
        _human_type(loc.first, value)
        log(f"  Filled '{label}'")
        return True
    except Exception as e:
        log(f"  Could not fill '{label}': {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────
#  ASHBY browser apply
# ─────────────────────────────────────────────────────────────────────────

def _apply_ashby_browser(page, url: str, resume_path: str,
                         cover_letter_path: str, progress_cb=None):
    def log(msg):
        if progress_cb:
            progress_cb(msg)
        print(f"  [ashby] {msg}")

    log("Opening job page...")
    page.goto(url, wait_until="networkidle", timeout=30000)
    _pause(2.0, 3.5)
    log(f"Page: {page.url}")

    # Navigate to /application form if not already there
    if "/application" not in page.url:
        apply_btn = page.locator("button:has-text('Apply')").first
        try:
            if apply_btn.is_visible(timeout=5000):
                _pause(0.8, 2.0)
                apply_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                _pause(2.5, 4.0)
                log(f"Form page: {page.url}")
        except Exception as e:
            log(f"Apply button issue: {e}")
    else:
        log("Already on form page")
        _pause(2.0, 3.0)

    # Wait for inputs to render
    try:
        page.wait_for_selector("input:visible", timeout=10000)
    except Exception:
        log("Warning: No inputs after 10s wait")

    # Simulate reading the page before filling — scroll down and back up
    log("Reading form...")
    _human_scroll(page, 250)
    _pause(1.0, 2.0)
    page.mouse.wheel(0, -200)
    _pause(0.5, 1.0)

    # Fill the form
    log("Filling form fields...")

    # Name — try Ashby system field first, then label-based fallback
    name_filled = False
    name_loc = page.locator("#_systemfield_name")
    if name_loc.count():
        _human_move(page, name_loc.first)
        name_filled = _fill_field(page, name_loc, CANDIDATE["full_name"], "Name", log)
    if not name_filled:
        for inp in page.locator("input:visible").all():
            iid = inp.get_attribute("id") or ""
            lbl_text = _get_field_label(page, inp).lower()
            iname = (inp.get_attribute("name") or "").lower()
            placeholder = (inp.get_attribute("placeholder") or "").lower()
            if any(k in s for k in ("name", "full name") for s in (lbl_text, iname, iid.lower(), placeholder)):
                if "company" not in lbl_text and "last" not in lbl_text:
                    _human_move(page, inp)
                    name_filled = _fill_field(page, inp, CANDIDATE["full_name"], "Name (fallback)", log)
                    if name_filled:
                        break
    _pause(0.6, 1.2)

    # Email — try Ashby system field first, then label-based fallback
    email_filled = False
    email_loc = page.locator("#_systemfield_email")
    if email_loc.count():
        _human_move(page, email_loc.first)
        email_filled = _fill_field(page, email_loc, CANDIDATE["email"], "Email", log)
    if not email_filled:
        for inp in page.locator("input:visible").all():
            itype = inp.get_attribute("type") or "text"
            lbl_text = _get_field_label(page, inp).lower()
            iname = (inp.get_attribute("name") or "").lower()
            if itype == "email" or "email" in lbl_text or "email" in iname:
                _human_move(page, inp)
                email_filled = _fill_field(page, inp, CANDIDATE["email"], "Email (fallback)", log)
                if email_filled:
                    break
    _pause(0.6, 1.2)

    # Phone
    phone_inp = page.locator("input[type='tel']:visible").first
    if phone_inp.count():
        _human_move(page, phone_inp)
        _fill_field(page, phone_inp, CANDIDATE["phone"], "Phone", log)
        _pause(0.6, 1.2)

    # URL fields (LinkedIn, GitHub, etc.)
    url_inputs = page.locator("input[type='url']:visible").all()
    for ui in url_inputs:
        lbl_text = _get_field_label(page, ui).lower()
        iid = (ui.get_attribute("id") or "").lower()
        if "linkedin" in lbl_text or "linkedin" in iid:
            _fill_field(page, ui, CANDIDATE["linkedin"], "LinkedIn", log)
        elif "github" in lbl_text or "github" in iid:
            _fill_field(page, ui, CANDIDATE["github"], "GitHub", log)
        elif "website" in lbl_text or "portfolio" in lbl_text:
            _fill_field(page, ui, CANDIDATE["website"] or CANDIDATE["github"], "Website", log)
        elif not ui.input_value().strip():
            _fill_field(page, ui, CANDIDATE["linkedin"], "URL field", log)
        _pause(0.4, 0.9)

    # Resume upload
    log("Uploading resume...")
    resume_uploaded = False
    resume_input = page.locator("input[type='file']#_systemfield_resume")
    if resume_input.count():
        try:
            resume_input.set_input_files(resume_path)
            log(f"  Uploaded: {os.path.basename(resume_path)}")
            resume_uploaded = True
            _pause(1.5, 3.0)
        except Exception as e:
            log(f"  Upload error: {e}")

    if not resume_uploaded:
        for fi in page.locator("input[type='file']").all():
            try:
                fi.set_input_files(resume_path)
                log("  Uploaded via fallback file input")
                resume_uploaded = True
                _pause(1.5, 3.0)
                break
            except Exception:
                pass

    if not resume_uploaded:
        log("  WARNING: No file input found for resume")

    # Sponsorship — click "No"
    try:
        labels = page.locator("label:visible, legend:visible, div:visible").all()
        for lbl in labels:
            txt = lbl.inner_text().lower()
            if "sponsor" in txt and len(txt) < 200:
                parent = lbl.locator("xpath=ancestor::div[position()<=5]").last
                no_btn = parent.locator("button:has-text('No')")
                if no_btn.count():
                    _pause(0.5, 1.0)
                    no_btn.first.click()
                    log("  Clicked 'No' for sponsorship")
                    break
    except Exception as e:
        log(f"  Sponsorship error: {e}")

    # Location autocomplete
    try:
        loc_input = page.locator("input[placeholder='Start typing...']:visible").first
        if loc_input.count() and not loc_input.input_value().strip():
            _pause(0.5, 1.0)
            _human_type(loc_input, CANDIDATE["location"])
            _pause(1.5, 2.5)
            suggestion = page.locator("[role='option']:visible").first
            if suggestion.is_visible(timeout=3000):
                suggestion.click()
                log("  Selected location from dropdown")
            else:
                loc_input.press("Enter")
                log("  Typed location (no dropdown)")
            _pause(0.5, 1.0)
    except Exception as e:
        log(f"  Location error: {e}")

    # AI-powered answers for custom screening questions (textareas + empty inputs)
    _STANDARD_IDS = {"_systemfield_name", "_systemfield_email", "_systemfield_resume"}
    _SKIP_TYPES = {"file", "hidden", "tel", "url", "checkbox", "radio", "submit", "button"}

    custom_fields = []
    for elem in page.locator("textarea:visible, input:visible").all():
        tag_name = elem.evaluate("el => el.tagName.toLowerCase()")
        itype = elem.get_attribute("type") or "text"
        iid = elem.get_attribute("id") or ""

        if iid in _STANDARD_IDS or itype in _SKIP_TYPES:
            continue

        try:
            current = elem.input_value()
            if current and current.strip():
                continue
        except Exception:
            continue

        question = _get_question_text(page, elem)
        if not question:
            question = _get_field_label(page, elem)
        if question and len(question) > 3:
            custom_fields.append((elem, question, tag_name, itype))

    if custom_fields:
        log(f"Found {len(custom_fields)} custom question(s) — generating AI answers...")
        for elem, question, tag_name, itype in custom_fields:
            if itype == "number":
                answer = _answer_question(
                    f"{question}\n\nIMPORTANT: Reply with ONLY a single number (integer). No text.", url
                )
                if answer:
                    import re as _re
                    nums = _re.findall(r"\d+", answer)
                    answer = nums[0] if nums else "2"
            elif itype == "date":
                answer = _answer_question(
                    f"{question}\n\nIMPORTANT: Reply with ONLY a date in MM/DD/YYYY format.", url
                )
            else:
                answer = _answer_question(question, url)

            if answer:
                _pause(0.5, 1.0)
                _human_move(page, elem)
                elem.click()
                _pause(0.3, 0.6)
                elem.fill(answer)
                _pause(0.8, 1.5)
                log(f"  AI answered [{itype}]: '{question[:50]}' -> '{answer[:60]}'")
            else:
                log(f"  Could not generate answer for: '{question[:60]}'")

    # Print form state
    log("--- Form state ---")
    for inp in page.locator("input:visible, textarea:visible").all():
        itype = inp.get_attribute("type") or "text"
        if itype in ("file", "hidden"):
            continue
        iid = inp.get_attribute("id") or "(no id)"
        try:
            val = inp.input_value()
        except Exception:
            val = ""
        tag = "OK" if val.strip() else "EMPTY"
        extra = ""
        if not val.strip():
            lbl = _get_question_text(page, inp) or _get_field_label(page, inp)
            extra = f" [{itype}] label='{lbl[:40]}'" if lbl else f" [{itype}]"
        log(f"  [{tag}] {iid}: '{val[:50]}'{extra}")

    # reCAPTCHA
    has_recaptcha = False
    recaptcha_frame = None
    try:
        recaptcha_frame = page.frame_locator("iframe[src*='recaptcha']")
        checkbox = recaptcha_frame.locator(".recaptcha-checkbox-border")
        if checkbox.is_visible(timeout=2000):
            has_recaptcha = True
            log("reCAPTCHA detected — PLEASE SOLVE IT in the browser")
    except Exception:
        pass

    if has_recaptcha:
        for i in range(180):
            try:
                checked = recaptcha_frame.locator(
                    ".recaptcha-checkbox-checked, [aria-checked='true']"
                )
                if checked.is_visible(timeout=500):
                    log("reCAPTCHA solved!")
                    _pause(1.0, 2.0)
                    break
            except Exception:
                pass
            if i % 15 == 0 and i > 0:
                log(f"  Waiting for reCAPTCHA... ({i}s)")
            page.wait_for_timeout(1000)
        else:
            log("reCAPTCHA not solved after 3 min")
            return False, "reCAPTCHA not solved — submit manually in the browser"

    # Submit
    pre_submit_url = page.url
    submit_btn = page.locator("button:has-text('Submit Application'):visible").first
    if not submit_btn.count():
        submit_btn = page.locator("button:has-text('Submit'):visible").first

    if submit_btn.is_visible(timeout=3000):
        _pause(1.0, 2.5)
        log("Clicking Submit...")
        submit_btn.click()
        page.wait_for_timeout(8000)
    else:
        log("No submit button — please submit manually")
        return False, "Submit button not found — check the browser"

    # OTP handling
    try:
        verify_el = page.locator(
            "text=/verify your email|verification code|check your email|enter.*code/i"
        ).first
        if verify_el.is_visible(timeout=3000):
            log("Email verification requested — checking Gmail...")
            code = _fetch_otp_from_gmail(sender_hint="ashby", max_wait=90)
            if code:
                log(f"Got OTP: {code}")
                otp_input = page.locator(
                    "input[type='text']:visible, input[type='number']:visible"
                ).first
                if otp_input.count():
                    _human_type(otp_input, code)
                    _pause(0.5, 1.0)
                    confirm_btn = page.locator(
                        "button:has-text('Verify'):visible, button:has-text('Confirm'):visible"
                    ).first
                    if confirm_btn.is_visible(timeout=2000):
                        confirm_btn.click()
                    page.wait_for_timeout(5000)
            else:
                log("No OTP found — please enter it manually")
                page.wait_for_timeout(60000)
    except Exception:
        pass

    # Detect success or failure
    post_url = page.url
    body_text = page.locator("body").inner_text().lower()

    # Check for explicit rejection first
    rejection_phrases = [
        "flagged as possible spam", "flagged as spam",
        "couldn't submit your application",
        "could not submit", "application was rejected",
    ]
    is_rejected = any(p in body_text for p in rejection_phrases)
    if is_rejected:
        log("Application was REJECTED (flagged as spam)")
        return False, "Application flagged as spam by Ashby — try closing Chrome and retrying (uses your real profile)"

    confirmation_phrases = [
        "application received", "thank you for applying",
        "thanks for applying", "we received your application",
        "application has been submitted", "successfully submitted",
        "thanks for your interest", "your application has been received",
    ]
    has_confirmation = any(p in body_text for p in confirmation_phrases)
    url_changed = post_url != pre_submit_url

    submit_gone = False
    try:
        submit_gone = not submit_btn.is_visible(timeout=1000)
    except Exception:
        submit_gone = True

    if has_confirmation:
        log("Application submitted successfully!")
        return True, "Submitted successfully via browser"
    elif url_changed and submit_gone:
        log("Page navigated after submit — likely successful")
        return True, "Submitted via browser (page navigated)"
    elif submit_gone:
        log("Submit button gone — likely successful")
        return True, "Submitted via browser (form closed)"
    else:
        log("Submit button still visible — check the browser")
        return False, "Form still visible after submit — check the browser"


# ─────────────────────────────────────────────────────────────────────────
#  GENERIC browser apply
# ─────────────────────────────────────────────────────────────────────────

def _apply_generic_browser(page, url: str, resume_path: str,
                           cover_letter_path: str, progress_cb=None):
    def log(msg):
        if progress_cb:
            progress_cb(msg)
        print(f"  [browser] {msg}")

    page.goto(url, wait_until="networkidle", timeout=30000)
    _pause(2.0, 4.0)
    log("Page loaded")

    apply_btn = page.locator(
        "button:has-text('Apply'), a:has-text('Apply')"
    ).first
    if apply_btn.is_visible(timeout=3000):
        _pause(0.5, 1.5)
        apply_btn.click()
        page.wait_for_load_state("networkidle", timeout=15000)
        _pause(2.0, 4.0)
        log("Clicked Apply")

    _FIELD_MAP = {
        "name": CANDIDATE["full_name"], "full name": CANDIDATE["full_name"],
        "first name": CANDIDATE["first_name"], "last name": CANDIDATE["last_name"],
        "email": CANDIDATE["email"], "phone": CANDIDATE["phone"],
        "linkedin": CANDIDATE["linkedin"], "github": CANDIDATE["github"],
        "location": CANDIDATE["location"], "city": CANDIDATE["location"],
    }

    inputs = page.locator("input:visible, textarea:visible").all()
    log(f"Found {len(inputs)} fields")

    for inp in inputs:
        itype = inp.get_attribute("type") or "text"
        if itype in ("hidden", "submit", "button", "checkbox", "radio", "file"):
            continue
        if inp.input_value().strip():
            continue

        label = ""
        iid = inp.get_attribute("id") or ""
        if iid:
            lbl = page.locator(f"label[for='{iid}']")
            if lbl.count():
                label = lbl.first.inner_text().strip()
        if not label:
            label = inp.get_attribute("aria-label") or inp.get_attribute("placeholder") or ""
        if not label:
            continue

        label_lower = label.lower()
        value = None
        if itype == "email" or "email" in label_lower:
            value = CANDIDATE["email"]
        elif itype == "tel" or "phone" in label_lower:
            value = CANDIDATE["phone"]
        elif itype == "url" or "linkedin" in label_lower:
            value = CANDIDATE["linkedin"]
        else:
            for key, val in _FIELD_MAP.items():
                if key in label_lower:
                    value = val
                    break

        if value:
            _human_type(inp, value)
            _pause(0.4, 0.9)
            log(f"  Filled '{label}'")

    for fi in page.locator("input[type='file']").all():
        fi.set_input_files(resume_path)
        log("Uploaded resume")

    log("Form filled — review and submit in the browser")
    return True, "Browser form filled — review and submit manually"


# ─────────────────────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────────────────────

_PLATFORM_HANDLERS = {
    "ashby": _apply_ashby_browser,
    "workable": _apply_generic_browser,
}


def browser_apply(url: str, resume_path: str, cover_letter_path: str = "",
                  platform: str = "", progress_cb=None) -> dict:
    from auto_apply import detect_platform

    if not platform:
        platform = detect_platform(url)
    if not platform:
        return {"ok": False, "platform": "", "message": "Unknown platform"}
    if not os.path.exists(resume_path):
        return {"ok": False, "platform": platform, "message": f"Resume not found: {resume_path}"}

    handler = _PLATFORM_HANDLERS.get(platform, _apply_generic_browser)

    def log(msg):
        if progress_cb:
            progress_cb(msg)
        print(f"[browser_apply] {msg}")

    try:
        from playwright.sync_api import sync_playwright

        cdp_ready = _ensure_cdp_chrome(log)

        with sync_playwright() as p:
            via_cdp = False
            browser_obj = None

            if cdp_ready:
                try:
                    browser_obj = p.chromium.connect_over_cdp(
                        f"http://localhost:{CDP_PORT}"
                    )
                    context = browser_obj.contexts[0]
                    page = context.new_page()
                    page.add_init_script(STEALTH_JS)
                    via_cdp = True
                    log("Connected to your Chrome via CDP — opening new tab")
                except Exception as cdp_err:
                    log(f"CDP connect failed ({cdp_err}) — falling back to profile launch")

            if not via_cdp:
                _kill_chrome()
                _sync_profile(log)
                log(f"Launching Chrome with your profile for {platform}")
                context = p.chromium.launch_persistent_context(
                    CHROME_APPLY_DATA,
                    channel="chrome",
                    headless=False,
                    slow_mo=50,
                    viewport={"width": 1280, "height": 920},
                    locale="en-US",
                    ignore_default_args=["--enable-automation"],
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )
                context.add_init_script(STEALTH_JS)
                page = context.new_page()

            ok, message = handler(page, url, resume_path, cover_letter_path, progress_cb)

            if ok:
                log("Success — tab stays open 15s")
                page.wait_for_timeout(15000)
            else:
                log("Issue detected — tab stays open 2 min for manual action")
                page.wait_for_timeout(120000)

            page.close()

            if via_cdp:
                browser_obj.disconnect()
            else:
                context.close()
                _relaunch_chrome()

        return {"ok": ok, "platform": platform, "message": message}

    except ImportError:
        return {
            "ok": False, "platform": platform,
            "message": "Playwright not installed. Run: pip install playwright && python -m playwright install chromium",
        }
    except Exception as e:
        log(f"Error: {e}")
        return {"ok": False, "platform": platform, "message": f"Browser error: {str(e)}"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Browser-based auto-apply")
    parser.add_argument("url", help="Job posting URL")
    parser.add_argument("resume", help="Path to resume PDF")
    parser.add_argument("--cover-letter", default="", help="Path to cover letter")
    parser.add_argument("--platform", default="", help="Force platform detection")
    args = parser.parse_args()

    result = browser_apply(args.url, args.resume, args.cover_letter, args.platform)
    print(f"\nResult: {'SUCCESS' if result['ok'] else 'FAILED'}")
    print(f"Platform: {result['platform']}")
    print(f"Message: {result['message']}")
