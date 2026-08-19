#!/usr/bin/env python3
"""
Token-based multi-account Discord runner with human-like interactions.

- Reads tokens.txt (one entry per line: token:channel_id)
- Uses persistent Chrome profiles in PROFILES_DIR
- Injects token via multiple strategies with read-back verification
- Simulates human-like mouse movement and typing when sending chat messages
"""
import os
import time
import logging
import hashlib
import random
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Load config
load_dotenv()
GUILD_ID = os.getenv("GUILD_ID") or ""
PROFILES_DIR = os.getenv("PROFILES_DIR") or "profiles"
TOKENS_FILE = os.getenv("TOKENS_FILE") or "tokens.txt"
CONCURRENCY = int(os.getenv("CONCURRENCY") or "1")  # default 1 for safety
LOG_FILE = os.getenv("LOG_FILE") or "multi_token_runner.log"

# Commands and behavior
COMMANDS = [
    "hello everyone",
    "how's it going?",
    "this is a test message"
]
COMMAND_INTERVAL = int(os.getenv("COMMAND_INTERVAL") or "20")
ROUNDS_PER_ACCOUNT = int(os.getenv("ROUNDS_PER_ACCOUNT") or "3")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[
    logging.FileHandler(LOG_FILE),
    logging.StreamHandler()
])
logger = logging.getLogger(__name__)


def short_id(token: str) -> str:
    return hashlib.sha1(token.encode("utf-8")).hexdigest()[:10]


class HumanLikeDiscord:
    def __init__(self, profile_dir: str):
        self.profile_dir = profile_dir
        self.driver = None
        self._start_browser()

    def _start_browser(self):
        opts = Options()
        opts.add_argument("--window-size=1200,900")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        if self.profile_dir:
            os.makedirs(self.profile_dir, exist_ok=True)
            opts.add_argument(f"--user-data-dir={os.path.abspath(self.profile_dir)}")
        svc = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=svc, options=opts)
        self.driver.set_page_load_timeout(60)
        time.sleep(1)

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

    def _attempt_cdp_add_script(self, script_src: str) -> bool:
        try:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script_src})
            logger.debug("CDP addScriptToEvaluateOnNewDocument succeeded")
            return True
        except Exception as e:
            logger.debug(f"CDP addScriptToEvaluateOnNewDocument failed: {e}")
            return False

    def _attempt_runtime_eval(self, script_src: str) -> bool:
        try:
            self.driver.execute_cdp_cmd("Runtime.evaluate", {"expression": script_src, "awaitPromise": False})
            logger.debug("CDP Runtime.evaluate succeeded")
            return True
        except Exception as e:
            logger.debug(f"CDP Runtime.evaluate failed: {e}")
            return False

    def _read_local_storage_token(self):
        try:
            return self.driver.execute_script("return window.localStorage.getItem('token')")
        except Exception as e:
            logger.debug(f"read_local_storage_token error: {e}")
            return None

    def inject_token(self, token: str, max_retries: int = 2) -> bool:
        """
        Attempt token injection via multiple methods with retries and verify by reading back localStorage.
        Returns True on likely success.
        """
        # Prepare strings
        safe_for_js = token.replace("\\", "\\\\").replace('"', '\\"')
        # Value we will set in localStorage (the stored value should include surrounding quotes)
        js_value_literal = f'\\"{safe_for_js}\\"'  # used inside JS string literal
        script = f'window.localStorage.setItem("token", "{js_value_literal}");'
        expected_stored = f'"{token}"'  # what getItem('token') should return

        for attempt in range(1, max_retries + 1):
            logger.info(f"Token injection attempt {attempt}/{max_retries}")

            # 1) Try addScriptToEvaluateOnNewDocument
            added = self._attempt_cdp_add_script(script)

            # Navigate so a newly-added script runs on page load
            try:
                self.driver.get("https://discord.com/channels/@me")
            except Exception as e:
                logger.debug(f"Navigation attempt error: {e}")

            time.sleep(2.0 + random.random() * 2.0)

            # After navigation, read back localStorage to check if the token was set
            read_back = self._read_local_storage_token()
            logger.debug(f"Read-back after CDP add attempt: {read_back}")
            if read_back == expected_stored:
                logger.info("Token verified in localStorage after CDP addScript")
                return True

            # 2) Try Runtime.evaluate via CDP (executes immediately in page context)
            ok = self._attempt_runtime_eval(script)
            time.sleep(1.0 + random.random())
            read_back = self._read_local_storage_token()
            logger.debug(f"Read-back after Runtime.evaluate attempt: {read_back}")
            if read_back == expected_stored:
                logger.info("Token verified in localStorage after Runtime.evaluate")
                return True

            # 3) Fallback: execute_script directly
            try:
                self.driver.execute_script(script)
                logger.debug("execute_script injection attempted")
            except Exception as e:
                logger.debug(f"execute_script injection failed: {e}")

            # Wait and read back
            time.sleep(1.2 + random.random() * 1.5)
            read_back = self._read_local_storage_token()
            logger.debug(f"Read-back after execute_script attempt: {read_back}")
            if read_back == expected_stored:
                logger.info("Token verified in localStorage after execute_script")
                return True

            # If not matched, try reload and check again (handles race conditions)
            try:
                self.driver.refresh()
            except Exception:
                pass
            time.sleep(2.0 + random.random() * 2.0)
            read_back = self._read_local_storage_token()
            logger.debug(f"Read-back after refresh: {read_back}")
            if read_back == expected_stored:
                logger.info("Token verified after refresh")
                return True

            # Small delay before next attempt
            time.sleep(1.5 + random.random() * 2.0)

        logger.error("All injection attempts failed")
        return False

    def wait_for_login(self, timeout: int = 30) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                url = self.driver.current_url
                if "discord.com" in url and "/login" not in url and "/register" not in url:
                    try:
                        self.driver.find_element(By.XPATH, "//div[@role='textbox' and @contenteditable='true']")
                        logger.info("Login detected by message box presence")
                        return True
                    except:
                        try:
                            self.driver.find_element(By.CSS_SELECTOR, "[data-list-id='guildsnav']")
                            logger.info("Login detected by guilds nav presence")
                            return True
                        except:
                            if "/channels/" in url:
                                return True
            except Exception:
                pass
            time.sleep(1.0)
        logger.warning("Login not detected within timeout")
        return False

    def navigate_to_channel(self, guild_id: str, channel_id: str):
        if not guild_id or guild_id == "@me":
            url = f"https://discord.com/channels/@me/{channel_id}"
        else:
            url = f"https://discord.com/channels/{guild_id}/{channel_id}"
        logger.info(f"Navigating to {url}")
        try:
            self.driver.get(url)
            time.sleep(3.0 + random.random() * 2.0)
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False

    def _get_element_center(self, element):
        rect = self.driver.execute_script("""
            const r = arguments[0].getBoundingClientRect();
            return {x: Math.floor(r.left + r.width/2), y: Math.floor(r.top + r.height/2),
                    w: Math.floor(r.width), h: Math.floor(r.height)};
        """, element)
        return rect

    def human_move_to_and_click(self, element):
        try:
            rect = self._get_element_center(element)
            target_x, target_y = rect['x'], rect['y']
            moves = max(6, int(random.uniform(6, 12)))
            for i in range(moves):
                frac = (i + 1) / moves
                ix = int(target_x * frac + random.uniform(-10, 10) * (1 - frac))
                iy = int(target_y * frac + random.uniform(-8, 8) * (1 - frac))
                try:
                    ActionChains(self.driver).move_by_offset(ix, iy).perform()
                except Exception:
                    try:
                        ActionChains(self.driver).move_to_element_with_offset(element, random.randint(-5,5), random.randint(-5,5)).perform()
                    except Exception:
                        pass
                time.sleep(random.uniform(0.02, 0.08))
            try:
                ActionChains(self.driver).move_to_element(element).pause(random.uniform(0.05, 0.15)).click().perform()
            except Exception:
                try:
                    element.click()
                except Exception as e:
                    logger.debug(f"Final click fallback failed: {e}")
            time.sleep(0.15 + random.random() * 0.25)
        except Exception as e:
            logger.debug(f"human_move_to_and_click error: {e}")
            try:
                element.click()
            except Exception:
                pass

    def find_message_box(self):
        try:
            xpath = "//div[@role='textbox' and @contenteditable='true']"
            box = WebDriverWait(self.driver, 12).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            return box
        except Exception as e:
            logger.debug(f"find_message_box error: {e}")
            return None

    def human_type(self, element, text: str):
        try:
            try:
                self.human_move_to_and_click(element)
            except:
                try:
                    element.click()
                except:
                    pass
            time.sleep(0.05 + random.random() * 0.12)
            for ch in text:
                element.send_keys(ch)
                time.sleep(random.uniform(0.03, 0.12))
            time.sleep(random.uniform(0.08, 0.25))
            element.send_keys(Keys.RETURN)
            logger.info(f"Typed message: {text}")
            return True
        except Exception as e:
            logger.error(f"human_type error: {e}")
            return False


def parse_tokens(path: str):
    if not os.path.exists(path):
        logger.error(f"Tokens file not found: {path}")
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if ":" in s:
                token, ch = s.split(":", 1)
                token = token.strip()
                ch = ch.strip()
                if token and ch:
                    out.append((token, ch))
            else:
                logger.warning(f"Malformed tokens line: {s}")
    return out


def handle_account(token, channel_id, guild_id, profiles_base):
    aid = short_id(token)
    profile_dir = os.path.join(profiles_base, aid)
    client = None
    try:
        logger.info(f"Starting account {aid} -> channel {channel_id}")
        client = HumanLikeDiscord(profile_dir)
        if not client.inject_token(token):
            logger.error(f"Failed to inject token for {aid}")
            return
        if not client.wait_for_login(timeout=35):
            logger.warning(f"Login not clearly detected for {aid}; continuing")
        if not client.navigate_to_channel(guild_id, channel_id):
            logger.error(f"Cannot navigate for {aid}")
            return

        commands = COMMANDS or []
        if not commands:
            logger.warning("No commands configured")
            return

        for i in range(ROUNDS_PER_ACCOUNT):
            cmd = commands[i % len(commands)]
            box = client.find_message_box()
            if not box:
                logger.warning(f"No message box found for {aid}")
                break
            success = client.human_type(box, cmd)
            if not success:
                logger.warning(f"Failed to send message for {aid}")
            wait_time = COMMAND_INTERVAL + random.uniform(-5, 5)
            time.sleep(max(1, wait_time))
        logger.info(f"Finished account {aid}")
    except Exception as e:
        logger.error(f"Exception in handle_account {aid}: {e}")
    finally:
        if client:
            client.close()


def main():
    logger.info("Runner starting")
    if not GUILD_ID:
        logger.error("GUILD_ID not set in .env")
        return
    accounts = parse_tokens(TOKENS_FILE)
    if not accounts:
        logger.error("No accounts found in tokens file")
        return
    max_workers = len(accounts) if CONCURRENCY <= 0 else min(CONCURRENCY, len(accounts))
    logger.info(f"Running {len(accounts)} accounts with concurrency={max_workers}")
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = []
        for token, ch in accounts:
            futures.append(ex.submit(handle_account, token, ch, GUILD_ID, PROFILES_DIR))
        for f in futures:
            try:
                f.result()
            except Exception as e:
                logger.error(f"Account job failed: {e}")
    logger.info("All done")


if __name__ == "__main__":
    main()
