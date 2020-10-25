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
    bot_mention = "<@!769367431109541918>"

    async def send_bot_help(self, mapping):
        # t_ = self.bot._
        global t_
        destination = self.get_destination()
        description = (
            t_("To use {0} you'll need to be registered first, use `!register` to start the registration.\n").format(self.bot_mention)
            + t_("To get upcoming event use `!get homework`.\n\n")
            + t_("For further support please DM `ZiRO2264#4572`!")
        )
        e = discord.Embed(
            title=t_("Help with Elearning Bot"), description=description, colour=self.COLOUR
        )
        await destination.send(embed=e)


class Help(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        global t_
        t_ = self.bot._
        self.logger = logging.getLogger("discord")
        self._original_help_command = bot.help_command
        bot.help_command = CustomHelp()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


def setup(bot):
    bot.add_cog(Help(bot))
