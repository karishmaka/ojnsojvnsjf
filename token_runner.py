# Token-based multi-account runner for Discord using Selenium
# Reads tokens.txt (one entry per line: token:channel_id)
# Uses persistent Chrome profiles in the `profiles/` folder so you can reuse sessions.

import os
import time
import logging
import threading
import hashlib
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
import random

# Load config from .env if present
load_dotenv()

GUILD_ID = os.getenv("GUILD_ID") or ""
PROFILES_DIR = os.getenv("PROFILES_DIR") or "profiles"
TOKENS_FILE = os.getenv("TOKENS_FILE") or "tokens.txt"
CONCURRENCY = int(os.getenv("CONCURRENCY") or "4")  # set 0 to run unlimited (all accounts)
LOG_FILE = os.getenv("LOG_FILE") or "multi_token_runner.log"

# Messaging behavior (shares settings with bot.py by default)
COMMANDS = [
    "flip {bet}",
    "balance",
    "status",
    "claim {bet}"
]
INITIAL_BET = int(os.getenv("INITIAL_BET") or "10")
BET_MULTIPLIER = float(os.getenv("BET_MULTIPLIER") or "2.0")
COMMAND_INTERVAL = int(os.getenv("COMMAND_INTERVAL") or "20")
COMMAND_POST_RESPONSE_DELAY = float(os.getenv("COMMAND_POST_RESPONSE_DELAY") or "1.5")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[
    logging.FileHandler(LOG_FILE),
    logging.StreamHandler()
])
logger = logging.getLogger(__name__)

# Helpers
def short_id(token: str) -> str:
    h = hashlib.sha1(token.encode('utf-8')).hexdigest()
    return h[:10]

class SimpleDiscordClient:
    def __init__(self, profile_dir: str):
        self.profile_dir = profile_dir
        self.driver = None
        self.setup_browser()

    def setup_browser(self):
        options = Options()
        options.add_argument("--window-size=1200,900")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Use profile if provided
        if self.profile_dir:
            os.makedirs(self.profile_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={os.path.abspath(self.profile_dir)}")

        # Start driver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(60)
        time.sleep(1)

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

    def inject_token(self, token: str) -> bool:
        try:
            self.driver.get("https://discord.com/login")
            time.sleep(1.5)
            # Tokens in localStorage are usually stored as a quoted string
            token_value = f'"{token}"'
            script = "window.localStorage.setItem('token', arguments[0]);"
            self.driver.execute_script(script, token_value)
            time.sleep(0.3)
            self.driver.refresh()
            time.sleep(3)
            return True
        except Exception as e:
            logger.error(f"inject_token error: {e}")
            return False

    def wait_for_login(self, timeout=30) -> bool:
        start = time.time()
        logger.info("Waiting for login to complete...")
        while time.time() - start < timeout:
            try:
                url = self.driver.current_url
                if "/login" not in url and "/register" not in url and "discord.com" in url:
                    # Simple check: guild scroller exists
                    try:
                        self.driver.find_element(By.CSS_SELECTOR, "[data-testid='guild-scroller']")
                        logger.info("Login detected via guild scroller")
                        return True
                    except:
                        # maybe in channels view already
                        return True
            except Exception:
                pass
            time.sleep(1)
        logger.warning("Login not detected in time")
        return False

    def navigate_to_channel(self, guild_id: str, channel_id: str) -> bool:
        try:
            if not guild_id or guild_id == "@me":
                url = f"https://discord.com/channels/@me/{channel_id}"
            else:
                url = f"https://discord.com/channels/{guild_id}/{channel_id}"
            logger.info(f"Navigating to {url}")
            self.driver.get(url)
            time.sleep(4)
            return True
        except Exception as e:
            logger.error(f"navigate_to_channel error: {e}")
            return False

    def find_message_box(self):
        try:
            xpath = "//div[@role='textbox' and @contenteditable='true' and contains(@aria-label, 'Message')]"
            box = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            return box
        except Exception as e:
            logger.error(f"find_message_box error: {e}")
            return None

    def send_message(self, content: str) -> bool:
        try:
            box = self.find_message_box()
            if not box:
                return False
            ActionChains(self.driver).move_to_element(box).click().perform()
            time.sleep(0.2)
            # Type slowly
            for ch in content:
                box.send_keys(ch)
                time.sleep(random.uniform(0.03, 0.08))
            time.sleep(0.2)
            box.send_keys(Keys.RETURN)
            logger.info(f"Sent: {content}")
            time.sleep(1.2)
            return True
        except Exception as e:
            logger.error(f"send_message error: {e}")
            return False

    def wait_for_response(self, timeout: int = 20):
        # Simple wait; returning last visible message text if present
        try:
            start = time.time()
            last = None
            while time.time() - start < timeout:
                try:
                    articles = self.driver.find_elements(By.CSS_SELECTOR, "[role='article']")
                    texts = [a.text.strip() for a in articles if a.text.strip()]
                    if texts:
                        if last != texts[-1]:
                            last = texts[-1]
                        else:
                            return last
                except Exception:
                    pass
                time.sleep(1)
            return last
        except Exception:
            return None


class GameStateLocal:
    def __init__(self):
        self.current_bet = INITIAL_BET
        self.total_games = 0
        self.wins = 0
        self.losses = 0

    def on_win(self):
        self.wins += 1
        self.total_games += 1
        self.current_bet = INITIAL_BET

    def on_loss(self):
        self.losses += 1
        self.total_games += 1
        self.current_bet = int(self.current_bet * BET_MULTIPLIER)


def handle_account(token: str, channel_id: str, guild_id: str, profile_base: str):
    account_id = short_id(token)
    profile_dir = os.path.join(profile_base, account_id)
    client = None
    state = GameStateLocal()

    try:
        logger.info(f"Starting account {account_id} -> channel {channel_id}")
        client = SimpleDiscordClient(profile_dir)

        # Inject token and login
        if not client.inject_token(token):
            logger.error(f"Failed to inject token for {account_id}")
            return

        if not client.wait_for_login(timeout=30):
            logger.warning(f"Login not detected for {account_id}; continuing but may fail")

        # Navigate to channel
        if not client.navigate_to_channel(guild_id, channel_id):
            logger.error(f"Could not navigate to channel for {account_id}")
            return

        # Main loop: send commands in sequence (simple loop with no advanced parsing)
        cmd_index = 0
        commands = COMMANDS or []
        if not commands:
            logger.warning("No commands set; exiting account loop")
            return

        # Send a small number of rounds by default (to avoid runaway behavior)
        rounds = int(os.getenv("ROUNDS_PER_ACCOUNT") or "10")
        for r in range(rounds):
            cmd = commands[cmd_index]
            try:
                to_send = cmd.format(bet=state.current_bet, current_bet=state.current_bet)
            except Exception:
                to_send = cmd

            sent = client.send_message(to_send)
            if not sent:
                logger.warning(f"Failed to send message for {account_id}")
            else:
                # wait for response heuristically
                resp = client.wait_for_response(timeout=20)
                if resp:
                    rl = resp.lower()
                    if 'you lost' in rl or 'lost it all' in rl:
                        state.on_loss()
                    elif 'you won' in rl or 'gained' in rl:
                        state.on_win()

            cmd_index = (cmd_index + 1) % len(commands)

            # wait interval with jitter
            interval = COMMAND_INTERVAL + random.randint(-5, 5)
            post_delay = COMMAND_POST_RESPONSE_DELAY
            time.sleep(max(0, interval + post_delay))

        logger.info(f"Finished account {account_id} after {rounds} rounds. Stats: {state.wins}W {state.losses}L")

    except Exception as e:
        logger.error(f"Exception in handle_account {account_id}: {e}")
    finally:
        if client:
            client.close()


def parse_tokens_file(path: str):
    if not os.path.exists(path):
        logger.error(f"Tokens file not found: {path}")
        return []
    out = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            # expecting token:channel_id
            if ':' in s:
                token, ch = s.split(':', 1)
                token = token.strip()
                ch = ch.strip()
                if token and ch:
                    out.append((token, ch))
            else:
                logger.warning(f"Skipping malformed line: {s}")
    return out


def main():
    logger.info("Multi-token runner starting")
    if not GUILD_ID:
        logger.error("GUILD_ID not set in environment (.env). Set GUILD_ID and rerun.")
        return

    os.makedirs(PROFILES_DIR, exist_ok=True)
    accounts = parse_tokens_file(TOKENS_FILE)
    if not accounts:
        logger.error("No accounts to run. Populate tokens.txt with lines token:channel_id")
        return

    # Determine concurrency
    if CONCURRENCY <= 0:
        max_workers = len(accounts)
    else:
        max_workers = min(CONCURRENCY, len(accounts))

    logger.info(f"Running {len(accounts)} accounts with concurrency={max_workers}")

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = []
        for token, ch in accounts:
            futures.append(ex.submit(handle_account, token, ch, GUILD_ID, PROFILES_DIR))

        # wait for all
        for f in futures:
            try:
                f.result()
            except Exception as e:
                logger.error(f"Account job exception: {e}")

    logger.info("All accounts finished")

if __name__ == '__main__':
    main()
