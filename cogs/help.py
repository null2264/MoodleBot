import asyncio
import bot
import discord
import json
import logging
import re

from discord.ext import commands
from typing import Optional


class CustomHelp(commands.HelpCommand):
    COLOUR = discord.Colour.blue()

    async def send_bot_help(self, mapping):
        destination = self.get_destination()
        description = "To use <@!769367431109541918> you'll need to be registered first, use `!register` to start the registration.\nTo get upcoming event use `!get homework`.\n\nFor further support please DM `ZiRO2264#4572`!"
        e = discord.Embed(
            title="Help with Elearning Bot", description=description, colour=self.COLOUR
        )
        await destination.send(embed=e)


class Help(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("discord")
        self._original_help_command = bot.help_command
        bot.help_command = CustomHelp()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


def setup(bot):
    bot.add_cog(Help(bot))
