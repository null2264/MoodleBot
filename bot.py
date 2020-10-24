import asyncio
import asyncpg
import aiohttp
import copy
import discord
import gettext
import json
import logging
import os
import sys
import traceback
import time

from discord.errors import NotFound
from discord.ext import commands
from dotenv import load_dotenv

# Create data directory if its not exist
try:
    os.makedirs("data")
except FileExistsError:
    pass

extensions = [
    "cogs.error_handler",
    "cogs.moodle",
    "cogs.help"
]

start_time = time.time()

def get_prefix(bot, message):
    """A callable Prefix for our bot. This could be edited to allow per server prefixes."""
    return commands.when_mentioned_or('!')(bot, message)


class ziBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=get_prefix,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False),
            intents=discord.Intents.all(),
        )
        
        self.localedir = './locale'
        self.translate = gettext.translation('elearningbot', self.localedir, fallback=True)
        self._ = self.translate.gettext

        self.logger = logging.getLogger("discord")
        self.session = aiohttp.ClientSession(loop=self.loop)
        
        with open("config.json", "r") as f:
            self.config = json.load(f)

        if not self.config["bot_token"]:
            self.logger.error("No token found. Please add it to config.json!")
            raise AttributeError("No token found!")
        
        self.master = [186713080841895936]
    
    async def create_empty_table(self):
        await self.pool.execute(
            """CREATE TABLE IF NOT EXISTS elearningbot.token (user_id text, token text)"""
        )

    async def on_ready(self):
        activity = discord.Activity(
            name="over your shoulder", type=discord.ActivityType.watching
        )
        await self.change_presence(activity=activity)

        for extension in extensions:
            self.load_extension(extension)
        
        # Create elearningbot schema if not exist
        await self.pool.execute(
            """CREATE SCHEMA IF NOT EXISTS elearningbot"""
        )
        await self.create_empty_table()

        self.logger.warning(f"Online: {self.user} (ID: {self.user.id})")

    async def on_message(self, message):
        # dont accept commands from bot
        if message.author.bot:
            return

        await self.process_commands(message)

    async def close(self):
        await super().close()
        await self.session.close()

    def run(self):
        super().run(self.config["bot_token"], reconnect=True)
