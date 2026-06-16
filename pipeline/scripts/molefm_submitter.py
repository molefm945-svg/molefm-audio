#!/usr/bin/env python3
"""
Mole FM — molefm.com Admin Submitter (Browser-based, v2)
=========================================================
Uses Playwright to submit audio URLs to molefm.com's admin podcast panel.
The platform has no write API — all submissions go through the browser UI.

AUDITED FIELDS (from June 17 2026 deep audit):
  Admin Panel → /admin/radio/podcasts
  Form fields:
    1. EPISODE TITLE    (text)
    2. SERIES           (dropdown)
    3. CATEGORY         (dropdown)
    4. LANGUAGE         (dropdown)
    5. HOST             (dropdown)
    6. STATUS           (dropdown)
    7. TOPIC            (text)
    8. DESCRIPTION      (textarea)
    9. TRANSCRIPT       (textarea)
   10. SHOW NOTES       (textarea)
   11. AUDIO URL        (text)

Usage:
  python molefm_submitter.py newscast <url> <title> [duration_seconds]
  python molefm_submitter.py podcast  <url> <title> [duration_seconds]
"""

import sys
import json
import datetime
import subprocess
import os
import tempfile

MOLEFM_ADMIN = "https://www.molefm.com/admin/radio/podcasts"
ADMIN_USERNAME = "admin"
ADMIN_PIN = "1804$Admin"

SUBMISSION_LOG = "/home/user/workspace/molefm/logs/molefm_submissions.jsonl"


def _log_submission(audio_type, url, title, success, error=None):
    """Log submission result."""
    os.makedirs(os.path.dirname(SUBMISSION_LOG), exist_ok=True)
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "type": audio_type,
        "url": url,
        "title": title,
        "success": success,
        "error": error,
    }
    with open(SUBMISSION_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _build_playwright_script(audio_type, url, title, duration_seconds=None):
    """Build the Playwright submission script for the correct form fields."""

    # Map audio type to admin form values (from audit)
    if audio_type == "newscast":
        series = "Mole FM News Clock"
        category = "News Brief"
        language = "French"
        host = "Community News Host"
        status = "Published"
        topic = f"Actualités Haïti vérifiées — {title}"
        description = (
            "Bulletin horaire Mole FM — jusqu'à 6 histoires vérifiées "
            "provenant de 12 sources haïtiennes et internationales. "
            "Météo de 3 villes. Généré par le pipeline AI Mole FM."
        )
        show_notes = "Pipeline AI Mole FM — edge-tts Neural FR — vérification multi-sources"
    else:  # podcast
        series = "Mole Morning Power"
        category = "Analysis"
        language = "French"
        host = "Morning Motivator"
        status = "Published"
        dur_min = (duration_seconds or 1140) // 60
        dur_sec = (duration_seconds or 1140) % 60
        topic = f"Analyse approfondie des actualités haïtiennes — Format The Daily × BBC"
        description = (
            f"Émission quotidienne Mole FM avec Denise et Henri. "
            f"Durée : {dur_min}m{dur_sec:02d}s. "
            f"Analyse, contexte diaspora, et actualité vérifiée."
        )
        show_notes = "Pipeline AI Mole FM — 2 voix neurales (Denise + Henri) — format 18-22 min"

    return f"""
import asyncio, sys, json
from playwright.async_api import async_playwright

AUDIO_TYPE = "{audio_type}"
AUDIO_URL = "{url}"
TITLE = {json.dumps(title)}
SERIES = {json.dumps(series)}
CATEGORY = {json.dumps(category)}
LANGUAGE = {json.dumps(language)}
HOST = {json.dumps(host)}
STATUS = {json.dumps(status)}
TOPIC = {json.dumps(topic)}
DESCRIPTION = {json.dumps(description)}
SHOW_NOTES = {json.dumps(show_notes)}

async def submit():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        try:
            # Step 1: Navigate to admin
            print(f"  [Browser] Navigating to admin panel...")
            await page.goto("https://www.molefm.com/admin/radio", 
                           wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            # Step 2: Login — try multiple selector patterns
            print(f"  [Browser] Looking for login form...")
            username_selectors = [
                'input[name="username"]', 
                'input[type="text"]',
                'input[placeholder*="username" i]',
                'input[placeholder*="admin" i]',
                'input[id*="username" i]',
            ]
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[name="pin"]',
                'input[placeholder*="password" i]',
                'input[placeholder*="pin" i]',
                'input[placeholder*="code" i]',
            ]

            username_filled = False
            for sel in username_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.fill("{ADMIN_USERNAME}")
                        username_filled = True
                        print(f"  [Browser] Filled username with selector: {{sel}}")
                        break
                except Exception:
                    pass

            password_filled = False
            for sel in password_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.fill("{ADMIN_PIN}")
                        password_filled = True
                        print(f"  [Browser] Filled password with selector: {{sel}}")
                        break
                except Exception:
                    pass

            if username_filled or password_filled:
                # Submit login form
                submit_selectors = [
                    'button[type="submit"]',
                    'button:has-text("Sign in")',
                    'button:has-text("Login")',
                    'button:has-text("Konekte")',
                    'input[type="submit"]',
                ]
                for sel in submit_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.is_visible(timeout=1000):
                            await el.click()
                            await page.wait_for_timeout(2000)
                            print(f"  [Browser] Login submitted")
                            break
                    except Exception:
                        pass

            # Step 3: Navigate to podcasts admin tab
            print(f"  [Browser] Navigating to podcasts tab...")
            await page.goto("https://www.molefm.com/admin/radio/podcasts",
                           wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            current_url = page.url
            print(f"  [Browser] Current URL: {{current_url}}")

            # Step 4: Fill the episode form
            print(f"  [Browser] Filling episode form...")

            # Helper: fill a text input by multiple selectors
            async def fill_field(selectors, value, field_name):
                for sel in selectors:
                    try:
                        els = page.locator(sel)
                        count = await els.count()
                        for i in range(count):
                            el = els.nth(i)
                            if await el.is_visible(timeout=1000):
                                await el.fill(value)
                                print(f"    [OK] {{field_name}} filled")
                                return True
                    except Exception:
                        pass
                print(f"    [SKIP] {{field_name}} — no matching field found")
                return False

            async def select_option(selectors, value, field_name):
                for sel in selectors:
                    try:
                        els = page.locator(sel)
                        count = await els.count()
                        for i in range(count):
                            el = els.nth(i)
                            if await el.is_visible(timeout=1000):
                                # Try select_option first
                                try:
                                    await el.select_option(label=value, timeout=2000)
                                    print(f"    [OK] {{field_name}} selected: {{value}}")
                                    return True
                                except Exception:
                                    pass
                                # Try fill (for text inputs that act as selects)
                                try:
                                    await el.fill(value)
                                    print(f"    [OK] {{field_name}} filled: {{value}}")
                                    return True
                                except Exception:
                                    pass
                    except Exception:
                        pass
                print(f"    [SKIP] {{field_name}} — no matching field found")
                return False

            # Title
            await fill_field(
                ['input[placeholder*="title" i]', 'input[name*="title" i]', 
                 'input[id*="title" i]', 'label:has-text("EPISODE TITLE") + * input',
                 'input[placeholder*="episode" i]'],
                TITLE, "Episode Title"
            )

            # Audio URL — most critical field
            audio_url_filled = await fill_field(
                ['input[placeholder*="audio" i]', 'input[name*="audio" i]',
                 'input[id*="audio" i]', 'input[placeholder*="url" i]',
                 'input[name*="url" i]', 'input[id*="url" i]',
                 'label:has-text("AUDIO URL") + * input',
                 'label:has-text("AUDIO") ~ * input'],
                AUDIO_URL, "Audio URL"
            )

            # Series dropdown
            await select_option(
                ['select[name*="series" i]', 'select[id*="series" i]',
                 'label:has-text("SERIES") + select',
                 'label:has-text("SERIES") ~ select'],
                SERIES, "Series"
            )

            # Category dropdown
            await select_option(
                ['select[name*="category" i]', 'select[id*="category" i]',
                 'label:has-text("CATEGORY") + select',
                 'label:has-text("CATEGORY") ~ select'],
                CATEGORY, "Category"
            )

            # Language dropdown
            await select_option(
                ['select[name*="language" i]', 'select[id*="language" i]',
                 'label:has-text("LANGUAGE") + select',
                 'label:has-text("LANGUAGE") ~ select'],
                LANGUAGE, "Language"
            )

            # Status dropdown
            await select_option(
                ['select[name*="status" i]', 'select[id*="status" i]',
                 'label:has-text("STATUS") + select',
                 'label:has-text("STATUS") ~ select'],
                STATUS, "Status"
            )

            # Topic
            await fill_field(
                ['input[placeholder*="topic" i]', 'input[name*="topic" i]',
                 'textarea[placeholder*="topic" i]', 'textarea[name*="topic" i]',
                 'label:has-text("TOPIC") + * input', 'label:has-text("TOPIC") ~ * input',
                 'label:has-text("TOPIC") + textarea'],
                TOPIC, "Topic"
            )

            # Description
            await fill_field(
                ['textarea[placeholder*="description" i]', 'textarea[name*="description" i]',
                 'textarea[id*="description" i]',
                 'label:has-text("DESCRIPTION") + textarea',
                 'label:has-text("DESCRIPTION") ~ textarea'],
                DESCRIPTION, "Description"
            )

            # Show Notes
            await fill_field(
                ['textarea[placeholder*="show notes" i]', 'textarea[name*="show_notes" i]',
                 'label:has-text("SHOW NOTES") + textarea',
                 'label:has-text("SHOW NOTES") ~ textarea'],
                SHOW_NOTES, "Show Notes"
            )

            if not audio_url_filled:
                print("  [WARN] Audio URL field not found — submission may be incomplete")
                # Try once more with any remaining input that could be URL
                inputs = page.locator('input[type="text"], input[type="url"]')
                count = await inputs.count()
                print(f"  [Debug] Total text/url inputs on page: {{count}}")
                for i in range(count):
                    el = inputs.nth(i)
                    try:
                        placeholder = await el.get_attribute("placeholder") or ""
                        name = await el.get_attribute("name") or ""
                        id_ = await el.get_attribute("id") or ""
                        visible = await el.is_visible(timeout=500)
                        val = await el.input_value()
                        print(f"    input[{{i}}]: placeholder='{{placeholder}}' name='{{name}}' id='{{id_}}' visible={{visible}} value='{{val[:30]}}'")
                    except Exception:
                        pass

            # Step 5: Submit
            print(f"  [Browser] Looking for submit/save button...")
            submit_buttons = [
                'button:has-text("Save")', 'button:has-text("Publish")',
                'button:has-text("Submit")', 'button:has-text("Add Episode")',
                'button:has-text("Create")', 'button[type="submit"]',
                'button:has-text("Publish episode")', 'button:has-text("Save episode")',
            ]
            submitted = False
            for sel in submit_buttons:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=1000):
                        await el.click()
                        await page.wait_for_timeout(3000)
                        print(f"  [Browser] Clicked: {{sel}}")
                        submitted = True
                        break
                except Exception:
                    pass

            if not submitted:
                print("  [Browser] No submit button found — form may have auto-submitted or changed")

            # Step 6: Verify success
            await page.wait_for_timeout(2000)
            final_url = page.url
            page_text = await page.inner_text("body")

            success_signals = ["published", "saved", "created", "success", "episode added"]
            error_signals = ["error", "failed", "invalid", "required"]

            success = any(sig in page_text.lower() for sig in success_signals)
            error = any(sig in page_text.lower() for sig in error_signals)

            if success:
                print(f"  [Browser] ✓ Submission successful!")
                print(json.dumps({{"status": "success", "url": AUDIO_URL, "title": TITLE}}))
            elif error:
                print(f"  [Browser] ⚠ Possible error detected on page")
                print(json.dumps({{"status": "warning", "url": AUDIO_URL}}))
            else:
                print(f"  [Browser] Submission completed (status unclear)")
                print(json.dumps({{"status": "completed", "url": AUDIO_URL}}))

        except Exception as e:
            print(f"  [Browser] Error: {{e}}")
            # Fallback: print the URL so it can be submitted manually
            print(json.dumps({{"status": "error", "error": str(e), "url": AUDIO_URL, "manual_url": "https://www.molefm.com/admin/radio/podcasts"}}))
        finally:
            await browser.close()

asyncio.run(submit())
""".replace("{ADMIN_USERNAME}", ADMIN_USERNAME).replace("{ADMIN_PIN}", ADMIN_PIN)


def submit_via_playwright(audio_type, url, title, duration_seconds=None):
    """
    Submit a new episode to molefm.com via Playwright headless browser.
    Returns True on success, False on failure.
    """
    script = _build_playwright_script(audio_type, url, title, duration_seconds)

    # Write script to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        result = subprocess.run(
            ["python3", script_path],
            capture_output=True, text=True, timeout=90
        )
        print(result.stdout)
        if result.returncode == 0:
            # Parse last JSON line for status
            lines = [l for l in result.stdout.strip().splitlines() if l.startswith("{")]
            if lines:
                try:
                    data = json.loads(lines[-1])
                    success = data.get("status") in ("success", "completed")
                    _log_submission(audio_type, url, title, success)
                    return success
                except Exception:
                    pass
            _log_submission(audio_type, url, title, True)
            return True
        else:
            print(f"  [molefm.com] stderr: {result.stderr.strip()[:300]}")
            _log_submission(audio_type, url, title, False, result.stderr.strip()[:200])
            return False
    except subprocess.TimeoutExpired:
        print("  [molefm.com] Playwright timeout (90s)")
        _log_submission(audio_type, url, title, False, "timeout")
        return False
    except Exception as e:
        print(f"  [molefm.com] Exception: {e}")
        _log_submission(audio_type, url, title, False, str(e))
        return False
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


def submit_episode(audio_type, url, title, duration_seconds=None):
    """
    Public entry point. Try browser submission; always log the URL as fallback.
    """
    print(f"\n  [molefm.com] Submitting {audio_type}: {title[:60]}")
    print(f"  [molefm.com] URL: {url}")

    success = submit_via_playwright(audio_type, url, title, duration_seconds)

    if not success:
        print(f"  [molefm.com] Browser submission unsuccessful.")
        print(f"  [molefm.com] Manual submission URL: https://www.molefm.com/admin/radio/podcasts")
        print(f"  [molefm.com] Audio URL to paste: {url}")

    return success


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python molefm_submitter.py [newscast|podcast] <audio_url> <title> [duration_seconds]")
        sys.exit(1)

    audio_type = sys.argv[1]
    audio_url = sys.argv[2]
    title = sys.argv[3]
    duration = int(sys.argv[4]) if len(sys.argv) > 4 else None

    if audio_type not in ("newscast", "podcast"):
        print(f"Unknown type: {audio_type}. Use 'newscast' or 'podcast'")
        sys.exit(1)

    success = submit_episode(audio_type, audio_url, title, duration)
    sys.exit(0 if success else 1)
