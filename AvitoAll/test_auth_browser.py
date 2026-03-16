"""
Avito Auth via Browser (Playwright)
Uses real browser to bypass anti-bot detection
"""
from playwright.sync_api import sync_playwright
import json
import time

def login_via_browser(phone: str, password: str, headless: bool = False):
    """
    Login to Avito via browser automation.

    Args:
        phone: Phone number (+7...)
        password: Password
        headless: Run browser in headless mode
    """
    print("=" * 60)
    print("Avito Browser Auth")
    print("=" * 60)

    with sync_playwright() as p:
        # Launch browser
        print("\n[*] Launching browser...")
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--lang=ru-RU",
            ]
        )

        # Create context with Russian locale
        context = browser.new_context(
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        # Enable request/response logging
        captured_data = {
            "cookies": [],
            "auth_response": None,
            "session": None,
        }

        def handle_response(response):
            url = response.url
            if "/api/" in url and "auth" in url.lower():
                print(f"\n[API] {response.request.method} {url} -> {response.status}")
                try:
                    data = response.json()
                    if data.get("status") == "ok" and "session" in str(data):
                        print("[+] Auth response captured!")
                        captured_data["auth_response"] = data
                        captured_data["session"] = data.get("result", {}).get("session")
                except:
                    pass

        page = context.new_page()
        page.on("response", handle_response)

        try:
            # Go to login page
            print("[*] Opening Avito login page...")
            page.goto("https://www.avito.ru/profile/login", wait_until="networkidle")
            time.sleep(2)

            # Check if already logged in
            if "profile" in page.url and "login" not in page.url:
                print("[+] Already logged in!")
            else:
                # Find and fill phone input
                print("[*] Looking for login form...")

                # Wait for the form
                page.wait_for_selector("input", timeout=10000)

                # Try to find phone input
                phone_input = page.query_selector("input[type='tel']") or \
                              page.query_selector("input[name='login']") or \
                              page.query_selector("input[placeholder*='Телефон']") or \
                              page.query_selector("input[placeholder*='телефон']")

                if phone_input:
                    print(f"[*] Entering phone: {phone[:7]}***")
                    phone_input.fill(phone)
                    time.sleep(0.5)
                else:
                    print("[-] Phone input not found, trying alternative selectors...")
                    # Take screenshot for debugging
                    page.screenshot(path="debug_login_page.png")
                    print("[*] Screenshot saved to debug_login_page.png")

                    # List all inputs
                    inputs = page.query_selector_all("input")
                    print(f"[*] Found {len(inputs)} input fields:")
                    for i, inp in enumerate(inputs):
                        inp_type = inp.get_attribute("type") or "text"
                        inp_name = inp.get_attribute("name") or ""
                        inp_placeholder = inp.get_attribute("placeholder") or ""
                        print(f"    [{i}] type={inp_type}, name={inp_name}, placeholder={inp_placeholder}")

                    # Try first visible input
                    if inputs:
                        inputs[0].fill(phone)
                        time.sleep(0.5)

                # Find password input
                password_input = page.query_selector("input[type='password']") or \
                                 page.query_selector("input[name='password']")

                if password_input:
                    print("[*] Entering password: ***")
                    password_input.fill(password)
                    time.sleep(0.5)

                # Find and click submit button
                submit_btn = page.query_selector("button[type='submit']") or \
                             page.query_selector("button:has-text('Войти')") or \
                             page.query_selector("button:has-text('войти')")

                if submit_btn:
                    print("[*] Clicking submit...")
                    submit_btn.click()
                else:
                    print("[-] Submit button not found")
                    page.screenshot(path="debug_no_submit.png")

                # Wait for navigation/response
                print("[*] Waiting for response...")
                time.sleep(5)

                # Check for SMS code input
                sms_input = page.query_selector("input[placeholder*='код']") or \
                            page.query_selector("input[placeholder*='SMS']")

                if sms_input:
                    print("\n[!] SMS CODE REQUIRED")
                    sms_code = input("Enter SMS code: ").strip()
                    sms_input.fill(sms_code)

                    # Find confirm button
                    confirm_btn = page.query_selector("button[type='submit']") or \
                                  page.query_selector("button:has-text('Подтвердить')")
                    if confirm_btn:
                        confirm_btn.click()
                        time.sleep(3)

            # Get cookies
            cookies = context.cookies()
            captured_data["cookies"] = cookies

            # Find session cookie
            for cookie in cookies:
                if cookie["name"] == "sessid":
                    captured_data["session"] = cookie["value"]
                    print(f"\n[+] Session cookie found: {cookie['value'][:50]}...")

            # Take final screenshot
            page.screenshot(path="final_state.png")
            print("[*] Final screenshot saved to final_state.png")

            # Save captured data
            if captured_data["session"] or captured_data["auth_response"]:
                with open("browser_auth_session.json", "w") as f:
                    json.dump(captured_data, f, indent=2, default=str)
                print("\n[+] Session saved to browser_auth_session.json")

            # Keep browser open for manual inspection
            print("\n[*] Browser will stay open. Press Enter to close...")
            input()

        except Exception as e:
            print(f"\n[-] Error: {e}")
            import traceback
            traceback.print_exc()
            page.screenshot(path="error_state.png")
            print("[*] Error screenshot saved to error_state.png")

        finally:
            browser.close()


if __name__ == "__main__":
    login_via_browser("+79997253777", "31415926Mips", headless=False)
