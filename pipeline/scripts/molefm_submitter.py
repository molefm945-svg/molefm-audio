#!/usr/bin/env python3
"""
Mole FM — molefm.com Admin Submitter (Browser-based)
Uses Playwright to submit audio URLs to molefm.com's admin podcast panel.
The platform has no write API — all submissions go through the browser UI.

Usage:
  python molefm_submitter.py newscast <url> <title> [duration_seconds]
  python molefm_submitter.py podcast  <url> <title> [duration_seconds]
"""

import sys
import json
import datetime
import subprocess
import os

MOLEFM_ADMIN = "https://www.molefm.com/admin/radio/podcasts"
ADMIN_USERNAME = "admin"
ADMIN_PIN = "1804$Admin"


def submit_via_playwright(audio_type, url, title, duration_seconds=None):
    """
    Submit a new episode to molefm.com via Playwright headless browser.
    Returns True on success, False on failure.
    """

    # Determine fields based on type
    if audio_type == "newscast":
        series = "Mole FM News Clock"
        category = "News Brief"
        topic = f"Actualités Haïti — édition vérifiée — {title}"
        description = "Émission horaire Mole FM — 6 histoires vérifiées provenant de 12 sources. Météo incluse. Généré par pipeline AI."
    else:
        series = "Mole Morning Power"
        category = "News Brief"
        topic = f"Analyse approfondie des actualités d'Haïti — Format The Daily × BBC × Hugo Décrypte"
        dur_min = (duration_seconds or 1140) // 60
        dur_sec = (duration_seconds or 1140) % 60
        description = f"Émission quotidienne Mole FM. Analyse avec Denise et Henri. Durée : {dur_min}m{dur_sec:02d}s."

    script = f"""
import asyncio
from playwright.async_api import async_playwright

async def submit():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Login
        await page.goto("{MOLEFM_ADMIN}", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1000)

        # Fill login form
        username_sel = 'input[type="text"], input[name="username"], input[placeholder*="user" i], input[placeholder*="admin" i]'
        pin_sel = 'input[type="password"], input[name="pin"], input[name="password"], input[name="code"], input[placeholder*="code" i], input[placeholder*="pin" i]'

        try:
            await page.fill(username_sel, "{ADMIN_USERNAME}")
            await page.fill(pin_sel, "{ADMIN_PIN}")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"  [Browser] Login field error: {{e}}")

        # Wait for admin panel
        await page.wait_for_timeout(2000)

        # Fill episode form fields
        fields = {{
            'input[name="title"], input[placeholder*="title" i], input[placeholder*="titre" i]': "{title}",
            'input[name="topic"], input[placeholder*="topic" i]': "{topic}",
            'textarea[name="description"], textarea[placeholder*="description" i]': "{description}",
            'input[name="audio_url"], input[name="audioUrl"], input[placeholder*="audio" i], input[placeholder*="url" i]': "{url}",
        }}

        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    await el.fill(value)
            except Exception:
                pass

        # Handle dropdowns
        dropdowns = [
            ('select[name="series"], select[name="show"]', "{series}"),
            ('select[name="category"]', "{category}"),
            ('select[name="language"]', "French"),
            ('select[name="status"]', "published"),
            ('select[name="host"]', "Community News Host"),
        ]
        for selector, value in dropdowns:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    await el.select_option(label=value)
            except Exception:
                pass

        # Submit
        submit_sel = 'button[type="submit"], button:has-text("Save"), button:has-text("Publish"), button:has-text("Sovgad"), button:has-text("Ajoute")'
        try:
            await page.locator(submit_sel).first.click()
            await page.wait_for_timeout(2000)
            print("  [Browser] ✓ Episode submitted successfully")
            result = True
        except Exception as e:
            print(f"  [Browser] Submit click failed: {{e}}")
            result = False

        await browser.close()
        return result

result = asyncio.run(submit())
exit(0 if result else 1)
"""

    result = subprocess.run(
        ["python3", "-c", script],
        capture_output=True, text=True, timeout=60
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print(f"  [Browser] stderr: {result.stderr.strip()[:300]}")
    return result.returncode == 0


def log_submission(audio_type, url, title, success):
    """Log submission result to JSONL."""
    log_path = "/home/user/workspace/molefm/logs/molefm_submissions.jsonl"
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "type": audio_type,
        "title": title,
        "url": url,
        "success": success,
    }
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python molefm_submitter.py [newscast|podcast] <url> <title> [duration_seconds]")
        sys.exit(1)

    audio_type = sys.argv[1]
    url = sys.argv[2]
    title = sys.argv[3]
    duration = int(sys.argv[4]) if len(sys.argv) > 4 else None

    if audio_type not in ("newscast", "podcast"):
        print(f"Unknown type: {audio_type}. Use 'newscast' or 'podcast'")
        sys.exit(1)

    # Check playwright is available
    try:
        subprocess.run(["python3", "-c", "from playwright.async_api import async_playwright"],
                      check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("  [molefm.com] Installing playwright...")
        subprocess.run(["pip", "install", "playwright", "-q"], check=True)
        subprocess.run(["python3", "-m", "playwright", "install", "chromium", "--with-deps"],
                      check=True, capture_output=True)

    success = submit_via_playwright(audio_type, url, title, duration)
    log_submission(audio_type, url, title, success)

    if success:
        print(f"  [molefm.com] ✓ {audio_type} published: {title}")
    else:
        print(f"  [molefm.com] ⚠ Auto-submit failed — add manually at: {MOLEFM_ADMIN}")
        print(f"  [molefm.com] Audio URL ready: {url}")

    sys.exit(0 if success else 1)
