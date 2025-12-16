# Horizont RP Discord Bot

A professional Discord bot for managing leaders/deputies, punishments, news, and utilities on the Horizont RP server.

## Features
- Leader/Deputy management with conflict resolution
- Punishment system with warnings and reprimand role progression
- News posting with rich embeds and auto-expiration (24h)
- Utilities: clear, role checks, stats, info, help
- JSON storage, .env configuration, detailed logging

## Requirements
- Python 3.8+
- `pip install -r requirements.txt`
- Create `.env` with `DISCORD_TOKEN=...`

## Configuration
Edit `ROLE_IDS` and `ADMIN_ROLES` in `main.py` to match your server.

## Run
```
python main.py
```

## Example Commands
- `!add_leader John_Doe LSPD Captain`
- `!add_deputy Jane_Doe FIB Lieutenant`
- `!reprimand John_Doe "No report submitted"`
- `!warning John_Doe "Late for briefing"`
- `!news general "Server maintenance at 20:00"`
- `!leaders`, `!leader John_Doe`, `!deputies`, `!deputy Jane_Doe`
- `!remove_leader John_Doe`, `!remove_deputy Jane_Doe`
- `!check_roles`, `!check_member John_Doe`, `!clear 50`
- `!stats`, `!info`, `!help`

## Data Structure
See `leaders_data.json` generated on first run. A sample is provided in the project description.

## Notes
- The bot requires permission to manage roles and read/send messages.
- Ensure the bot's role is above leader/deputy/reprimand roles.
