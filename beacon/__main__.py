"""Entry point for running the bot with `python -m beacon`."""

import logging
import sys

from .config import Config


def main() -> None:
    """Main entry point for the beacon bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = Config.from_env()

    if config.debug_br:
        logging.getLogger().setLevel(logging.DEBUG)

    if not config.bot_token:
        print(
            "Error: DISCORD_BOT_TOKEN environment variable is required.\n"
            "Set it in your .env file or environment.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Import here to avoid circular imports and allow logging setup first
    from .bot import run

    run(config.bot_token)


if __name__ == "__main__":
    main()
