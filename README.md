# Discord Sequenced Commands Bot (Selenium)

This repository contains a Selenium-based script to open Chrome, wait for a manual Discord login, navigate to a specified channel/DM, and send a configurable sequence of commands (commands can be any text — they do not need to start with `!`). Each command is sent in order; the bot waits for a response and then sends the next command.

Important warnings
- This automates a real user account via a browser. It may violate Discord Terms of Service and can lead to account action. Use at your own risk.
- Be careful with gambling commands and unbounded betting strategies (Martingale can quickly exhaust a bankroll).

Setup
1. Python 3.9+
2. Install deps:
   pip install -r requirements.txt
3. Edit `config.py` (or create a `.env`) and set CHANNEL_ID and the COMMANDS list and other parameters.
4. Run:
   python bot.py

Files
- bot.py — main script
- config.py — configuration (command list, start/stop triggers, betting params)
- requirements.txt — dependencies
- .gitignore — recommended ignores

If you want, I can:
- Push more changes (Dockerfile, CI) or change the branch name.
- Add a persistence file to remember last command index across restarts.
