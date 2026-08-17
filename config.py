# Example config.py - edit values as needed
import os
from dotenv import load_dotenv

load_dotenv()  # optional: load from .env if present

# Discord channel ID to open (for DM or channel URL path)
# Example: CHANNEL_ID = 123456789012345678
CHANNEL_ID = int(os.getenv("CHANNEL_ID") or "0")

# Bot command sequence: any strings allowed. Use {bet} or {current_bet} placeholders.
# The bot will send these commands in order, cycle to the start when finished.
COMMANDS = [
    "flip {bet}",
    "balance",
    "status",
    "claim {bet}"
]

# Which command to look for to start and stop the sequence (case-insensitive).
# These are matched by simple substring containment in message text.
START_COMMAND = os.getenv("START_COMMAND") or "start"
STOP_COMMAND = os.getenv("STOP_COMMAND") or "stop"

# Betting parameters (used when you include {bet} in commands)
INITIAL_BET = int(os.getenv("INITIAL_BET") or "10")
BET_MULTIPLIER = float(os.getenv("BET_MULTIPLIER") or "2.0")

# How often to send commands (base interval)
COMMAND_INTERVAL = int(os.getenv("COMMAND_INTERVAL") or "20")
# Extra small delay after receiving a response (float seconds)
COMMAND_POST_RESPONSE_DELAY = float(os.getenv("COMMAND_POST_RESPONSE_DELAY") or "1.5")

# Logging config
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
LOG_FILE = os.getenv("LOG_FILE") or "bot.log"
