# Beacon Bot

A Discord bot that automatically generates battle report summaries from [WarBeacon](https://warbeacon.net) links for EVE Online.

## Features

- Detects WarBeacon battle report links in Discord messages
- Fetches battle data from the WarBeacon API
- Posts a formatted embed with ISK lost, ships destroyed, and pilot counts
- Supports both single-system (`/br/related/`) and multi-system (`/br/report/`) links
- Configurable "home team" detection for win/loss coloring

## Quick Start

### Prerequisites

- Python 3.10+
- A Discord bot token ([create one here](https://discord.com/developers/applications))

### Local Development

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/beacon.git
cd beacon

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your DISCORD_BOT_TOKEN

# Run the bot
python bot.py
```

### Docker

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env and add your DISCORD_BOT_TOKEN

# Build and run
docker compose up --build

# Or run in background
docker compose up -d --build
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | - | Your Discord bot token |
| `PREFERRED_ALLIANCES` | No | `99010452` | Comma-separated alliance IDs for "home team" |
| `PREFERRED_CORPS` | No | `98648442` | Comma-separated corporation IDs for "home team" |
| `DEBUG_BR` | No | `false` | Enable debug logging |

## Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to the "Bot" section and create a bot
4. Enable the "Message Content Intent" under Privileged Gateway Intents
5. Copy the bot token and add it to your `.env` file
6. Go to OAuth2 > URL Generator, select `bot` scope with these permissions:
   - Read Messages/View Channels
   - Send Messages
   - Embed Links
   - Manage Messages (optional, for deleting original links)
7. Use the generated URL to invite the bot to your server

## Commands

| Command | Description |
|---------|-------------|
| `!ping` | Check if the bot is responsive |

## How It Works

When a user posts a WarBeacon link like:
```
https://warbeacon.net/br/related/30004759/202512030400/
```

The bot will:
1. Parse the system ID and timestamp from the URL
2. Fetch battle data from the WarBeacon API
3. Compute sides based on killmail attackers/victims
4. Generate an embed showing the battle summary
5. Optionally delete the original message (if it has permissions)

## Author

[Stealthbot](https://zkillboard.com/character/1406208348/)
