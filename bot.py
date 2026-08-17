"""
Discord UI Automation bot (Selenium) — sequenced commands, configurable start/stop, and placeholders.

Notes:
- This automates a real browser. Log in manually when the browser opens.
- Use config.py to control commands and triggers.
- Commands can be any string (do not need to start with '!').
"""

import logging
import os
from datetime import datetime
import asyncio
import time
from typing import Optional
import random
import sys
import io
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

from config import *

# Fix Unicode on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Use COMMAND_INTERVAL from config if present
try:
    COMMAND_INTERVAL = int(COMMAND_INTERVAL)
except Exception:
    COMMAND_INTERVAL = 20

logger.info("Using Chrome Browser - Manual Login Required")

# Human-like delays
def random_delay(min_sec=1, max_sec=3):
    """Add random delay to mimic human behavior"""
    time.sleep(random.uniform(min_sec, max_sec))

class DiscordChromeClient:
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self.driver = None
        self.last_seen_messages = []  # Keep ordered list to preserve message order

        logger.info("Initializing Discord Chrome Browser Client...")
        self.setup_browser()

    def setup_browser(self):
        """Setup Selenium with Chrome browser"""
        chrome_options = Options()

        # Realistic user agent
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Basic arguments
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-crash-reporter")
        chrome_options.add_argument("--disable-popup-blocking")

        # Anti-detection (optional)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        try:
            logger.info("Downloading ChromeDriver...")
            service = Service(ChromeDriverManager().install())

            logger.info("Launching Chrome browser...")
            self.driver = webdriver.Chrome(service=service, options=chrome_options)

            # Set timeouts
            self.driver.set_page_load_timeout(30)

            logger.info("Chrome browser launched successfully!")
            time.sleep(2)

        except Exception as e:
            logger.error(f"Failed to initialize Chrome browser: {e}")
            import traceback
            traceback.print_exc()
            raise

    def wait_for_login(self, timeout=300) -> bool:
        """Wait for user to manually login"""
        try:
            logger.info("\n" + "="*50)
            logger.info("PLEASE LOGIN TO DISCORD")
            logger.info("="*50)
            logger.info("A browser window has opened.")
            logger.info("Login using your email/password or SSO.")
            logger.info("Waiting for you to login...")
            logger.info("="*50 + "\n")

            self.driver.get("https://discord.com/login")
            time.sleep(2)

            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    current_url = self.driver.current_url

                    # Check if logged in by URL (should not be on /login anymore)
                    if "discord.com" in current_url and "/login" not in current_url and "/register" not in current_url:
                        logger.info("Login detected via URL change!")
                        time.sleep(3)  # Wait for page to fully load
                        return True

                    # Try to find guild scroller
                    try:
                        self.driver.find_element(By.CSS_SELECTOR, "[data-testid='guild-scroller']")
                        logger.info("Login detected via guild scroller!")
                        return True
                    except:
                        pass

                    time.sleep(1)

                except Exception as e:
                    logger.debug(f"Error during login check: {e}")
                    time.sleep(1)

            logger.error("Login timeout - user did not login within timeout")
            return False

        except Exception as e:
            logger.error(f"Login wait failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def navigate_to_channel(self) -> bool:
        """Navigate to target channel using CHANNEL_ID from config"""
        try:
            logger.info(f"Navigating to channel {self.channel_id}...")

            channel_url = f"https://discord.com/channels/@me/{self.channel_id}"
            self.driver.get(channel_url)

            time.sleep(5)
            random_delay(1, 2)

            logger.info("In target channel")
            return True

        except Exception as e:
            logger.error(f"Error navigating: {e}")
            return False

    def get_message_contents(self):
        """Get actual message contents using article selector (returns ordered list)"""
        try:
            message_contents = []

            # Use article selector since it generally corresponds to message blocks
            articles = self.driver.find_elements(By.CSS_SELECTOR, "[role='article']")

            for article in articles:
                try:
                    text = article.text.strip()
                    if text:
                        message_contents.append(text)
                except:
                    pass

            return message_contents
        except Exception as e:
            logger.debug(f"Error getting messages: {e}")
            return []

    def wait_for_start_command(self, start_trigger: str, timeout_sec: int = 120) -> bool:
        """Wait for configured START_COMMAND in chat (case-insensitive)"""
        try:
            logger.info("\n" + "="*50)
            logger.info("WAITING FOR START COMMAND IN DISCORD")
            logger.info("="*50)
            logger.info(f"Type '{start_trigger}' in the channel to begin")
            logger.info("Checking for messages every 0.5 seconds...")
            logger.info("="*50 + "\n")

            # Seed last_seen_messages with current messages
            time.sleep(2)
            current_messages = self.get_message_contents()
            self.last_seen_messages = list(current_messages)

            logger.info(f"Found {len(current_messages)} existing messages")

            start_time = time.time()

            while time.time() - start_time < timeout_sec:
                try:
                    current_messages = self.get_message_contents()

                    # find new messages while preserving order
                    for msg in current_messages:
                        if msg not in self.last_seen_messages:
                            self.last_seen_messages.append(msg)
                            if start_trigger.lower() in msg.lower():
                                logger.info("START command detected!")
                                time.sleep(1)
                                return True

                    time.sleep(0.5)

                except Exception as e:
                    logger.debug(f"Error checking messages: {e}")
                    time.sleep(0.5)

            logger.error(f"Timeout waiting for start command ({timeout_sec} seconds)")
            return False

        except Exception as e:
            logger.error(f"Error waiting for start: {e}")
            import traceback
            traceback.print_exc()
            return False

    def check_for_stop_command(self, stop_trigger: str) -> bool:
        """Check latest messages for STOP_COMMAND (simple, looks at most recent message)"""
        try:
            messages = self.get_message_contents()
            if not messages:
                return False

            last_message = messages[-1].lower()
            if stop_trigger.lower() in last_message:
                logger.info("STOP command detected!")
                return True

            return False

        except Exception as e:
            logger.debug(f"Error checking for stop: {e}")
            return False

    def send_message(self, content: str) -> bool:
        """Send message to Discord channel"""
        try:
            logger.info("Attempting to find and click message input box...")

            # Close any open search/modals first by pressing Escape
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)

            # Find message input using the aria-label that contains "Message"
            message_input_xpath = "//div[@role='textbox' and @contenteditable='true' and contains(@aria-label, 'Message')]"

            try:
                message_box = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, message_input_xpath))
                )
                logger.info("Found message input box")
            except Exception as e:
                logger.error(f"Could not find message input box: {e}")
                return False

            # Scroll to ensure it's visible
            self.driver.execute_script("arguments[0].scrollIntoView(true);", message_box)
            time.sleep(0.5)

            # Click on the message box
            ActionChains(self.driver).move_to_element(message_box).click().perform()
            time.sleep(0.5)

            # Wait for focus
            WebDriverWait(self.driver, 5).until(
                lambda d: d.execute_script("return document.activeElement === arguments[0]", message_box)
            )

            # Clear any existing text
            message_box.send_keys(Keys.CONTROL + 'a')
            time.sleep(0.1)
            message_box.send_keys(Keys.DELETE)
            time.sleep(0.3)

            # Type the message character by character
            for char in content:
                message_box.send_keys(char)
                time.sleep(random.uniform(0.05, 0.12))

            time.sleep(0.5)

            # Send the message with Enter
            message_box.send_keys(Keys.RETURN)

            logger.info(f"Message sent: {content}")
            time.sleep(1)
            return True

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            import traceback
            traceback.print_exc()
            return False

    def wait_for_response(self, timeout: int = 45) -> Optional[str]:
        """Wait for bot response and attempt to return a complete message"""
        try:
            start_time = time.time()

            logger.info(f"Waiting for response... (timeout: {timeout}s)")

            last_response = None
            stable_count = 0  # Counter to check if message is stable

            while time.time() - start_time < timeout:
                try:
                    current_messages = self.get_message_contents()

                    # Check all messages for new responses
                    for msg in current_messages:
                        if msg not in self.last_seen_messages:
                            self.last_seen_messages.append(msg)
                            last_response = msg
                            stable_count = 0
                            logger.debug("New message detected; waiting for it to stabilize...")

                    # If we have a response, try to decide if it's complete
                    if last_response:
                        msg_lower = last_response.lower()

                        # Heuristics: look for win/loss indicators
                        if any(k in msg_lower for k in ['you won', 'you lost', 'gained', 'lost it all', 'spent', 'cowoncy']):
                            logger.info("Bot response detected and considered complete.")
                            return last_response

                        # otherwise wait a bit for message to stabilize
                        stable_count += 1
                        if stable_count >= 3:
                            logger.warning("Message seems stable but no explicit win/loss keywords; returning latest message.")
                            return last_response

                    time.sleep(1)

                except Exception as e:
                    logger.error(f"Error checking messages: {e}")
                    time.sleep(1)

            if last_response:
                logger.warning(f"Timeout reached but have a response; returning it")
                return last_response

            logger.warning(f"No response received after {timeout} seconds")
            return None

        except Exception as e:
            logger.error(f"Error waiting for response: {e}")
            return None

    def close(self):
        """Close browser"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Chrome browser closed")
            except:
                pass


# Game State
class GameState:
    def __init__(self):
        self.current_bet = int(INITIAL_BET)
        self.total_games = 0
        self.wins = 0
        self.losses = 0
        self.is_running = False
        self.last_result = None
        self.last_timestamp = None

    def on_win(self):
        self.wins += 1
        self.total_games += 1
        self.current_bet = int(INITIAL_BET)
        logger.info(f"WIN! Bet reset to {INITIAL_BET}. Stats: {self.wins}W - {self.losses}L")

    def on_loss(self):
        self.losses += 1
        self.total_games += 1
        # avoid non-integer bets if config uses floats
        self.current_bet = int(self.current_bet * BET_MULTIPLIER)
        logger.warning(f"LOSS! Bet updated to {self.current_bet}. Stats: {self.wins}W - {self.losses}L")

    def get_stats(self):
        win_rate = (self.wins / self.total_games * 100) if self.total_games > 0 else 0
        return {
            "current_bet": self.current_bet,
            "total_games": self.total_games,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": win_rate
        }

game_state = GameState()

async def play_game(browser_client: DiscordChromeClient, commands, start_trigger: str, stop_trigger: str):
    """Main game loop - sends commands in sequence from the 'commands' list."""
    logger.info("Starting game loop (sequenced commands)...")
    logger.info(f"Command interval: {COMMAND_INTERVAL} seconds")
    logger.info("Bot is running! Type stop trigger in Discord to stop.\n")

    if not commands:
        logger.error("No commands provided. Set COMMANDS in config.")
        return

    cmd_index = 0
    num_commands = len(commands)

    while game_state.is_running:
        try:
            # Check for stop command
            if browser_client.check_for_stop_command(stop_trigger):
                logger.info("Stop command received!")
                game_state.is_running = False
                break

            # Build command text and support placeholders
            raw_command = commands[cmd_index]
            try:
                command_text = raw_command.format(bet=game_state.current_bet, current_bet=game_state.current_bet)
            except Exception as e:
                logger.warning(f"Failed to format command '{raw_command}' with bet placeholders: {e}")
                command_text = raw_command

            logger.info(f"Sending command [{cmd_index+1}/{num_commands}]: {command_text}")

            if not browser_client.send_message(command_text):
                logger.error("Failed to send message")
                # Advance to next command to avoid repeating a problematic command
                cmd_index = (cmd_index + 1) % num_commands
                await asyncio.sleep(COMMAND_INTERVAL)
                continue

            # Small human-like delay after sending
            random_delay(2, 4)

            # Wait for response from bot
            result = browser_client.wait_for_response(timeout=45)

            if result:
                game_state.last_result = result
                game_state.last_timestamp = datetime.now()

                result_lower = result.lower()
                logger.info(f"Full bot message: {result}")

                is_loss = False
                is_win = False

                if 'you lost' in result_lower or 'lost it all' in result_lower:
                    is_loss = True
                    logger.info("Detected: loss indicator")

                if 'you won' in result_lower or 'gained' in result_lower:
                    is_win = True
                    logger.info("Detected: win indicator")

                logger.info(f"Win check: {is_win}, Loss check: {is_loss}")

                if is_loss and not is_win:
                    logger.info("Result: LOSS detected")
                    game_state.on_loss()
                elif is_win and not is_loss:
                    logger.info("Result: WIN detected")
                    game_state.on_win()
                else:
                    logger.warning("Could not determine win/loss or message ambiguous.")
                    logger.warning(f"Message: {result[:300]}")
            else:
                logger.warning("No response received from bot")

            # Advance to the next command in the sequence
            cmd_index = (cmd_index + 1) % num_commands

            # Optional small post-response delay (from config)
            try:
                post_delay = float(COMMAND_POST_RESPONSE_DELAY)
            except Exception:
                post_delay = 0

            # Base wait interval (randomized around COMMAND_INTERVAL)
            random_interval = COMMAND_INTERVAL + random.randint(-5, 5)
            total_wait = max(0, random_interval + post_delay)

            logger.info(f"Waiting {total_wait} seconds before next command...\n")
            await asyncio.sleep(total_wait)

        except Exception as e:
            logger.error(f"Error in game loop: {e}")
            await asyncio.sleep(COMMAND_INTERVAL)

def print_stats():
    """Print game statistics"""
    stats = game_state.get_stats()
    print("\n" + "="*50)
    print("GAME STATISTICS")
    print("="*50)
    print(f"Current Bet: {stats['current_bet']}")
    print(f"Total Games: {stats['total_games']}")
    print(f"Wins: {stats['wins']}")
    print(f"Losses: {stats['losses']}")
    print(f"Win Rate: {stats['win_rate']:.2f}%")
    print("="*50 + "\n")

def main():
    """Main entry point"""

    if not CHANNEL_ID or CHANNEL_ID == 0:
        logger.error("CHANNEL_ID not set in config.py or .env!")
        return

    # Commands from config
    try:
        commands = COMMANDS
    except Exception:
        commands = []

    logger.info("Starting Discord Sequenced Commands Bot (Chrome Browser Mode)...")
    logger.info(f"Command interval: {COMMAND_INTERVAL} seconds\n")

    browser_client = DiscordChromeClient(CHANNEL_ID)

    try:
        # Wait for manual login
        if not browser_client.wait_for_login():
            logger.error("Login failed!")
            return

        # Navigate to channel
        if not browser_client.navigate_to_channel():
            logger.error("Failed to navigate to channel!")
            return

        # Wait for start trigger (configurable)
        if not browser_client.wait_for_start_command(START_COMMAND):
            logger.error("Failed waiting for start trigger command!")
            return

        # Start the game/sequence
        game_state.is_running = True
        asyncio.run(play_game(browser_client, commands, START_COMMAND, STOP_COMMAND))

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        game_state.is_running = False
        print_stats()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        game_state.is_running = False

    finally:
        print_stats()
        browser_client.close()

if __name__ == "__main__":
    main()
