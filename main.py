import asyncio
import asyncpg
import click
import contextlib
import discord
import json
import logging

from bot import ziBot


@contextlib.contextmanager
def setup_logging():
    try:
        FORMAT = "%(asctime)s - [%(levelname)s]: %(message)s"
        DATE_FORMAT = "%d/%m/%Y (%H:%M:%S)"

        logger = logging.getLogger("discord")
        logger.setLevel(logging.INFO)

        file_handler = logging.FileHandler(
            filename="discord.log", mode="a", encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(fmt=FORMAT, datefmt=DATE_FORMAT))
        file_handler.setLevel(logging.INFO)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(fmt=FORMAT, datefmt=DATE_FORMAT))
        console_handler.setLevel(logging.WARNING)
        logger.addHandler(console_handler)

        yield
    finally:
        handlers = logger.handlers[:]
        for handler in handlers:
            handler.close()
            logger.removeHandler(handler)


def check_json():
    try:
        f = open("config.json", "r")
    except FileNotFoundError as err:
        with open("config.json", "w+") as f:
            json.dump(
                {
                    "bot_token": "",
                    "postgresql": "",
                    "moodle_baseurl": "",
                },
                f,
                indent=4,
            )
        raise err


def init_bot():
    loop = asyncio.get_event_loop()
    logger = logging.getLogger()

    try:
        check_json()
    except FileNotFoundError:
        return

    with open("config.json", "r") as f:
        config = json.load(f)

    try:
        pool = loop.run_until_complete(asyncpg.create_pool(config["postgresql"]))
    except Exception as e:
        logger.error("Could not set up PostgreSQL. Exiting.")
        return

    bot = ziBot()
    bot.pool = pool
    bot.run()


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """Launch the bot."""
    if ctx.invoked_subcommand is None:
        loop = asyncio.get_event_loop()
        with setup_logging():
            init_bot()


if __name__ == "__main__":
    main()
