import asyncio
import asyncpg
import aiohttp
import discord
import gettext
import json
import re
import sys
import traceback
import urllib

from .utils.paginator import ziPages
from datetime import datetime
from discord.ext import commands, menus
from markdownify import markdownify as md


class MoodleEventsPageSource(menus.ListPageSource):
    def __init__(self, events):
        super().__init__(entries=events, per_page=1)

    def format_page(self, menu, event):
        # Very messy way to convert html to markdown
        regex = [
            r"(<div(?:.*)?>(.*)</div>)",
            r"(<h([1-6])>(.*)</h[1-6]>)",
            r"(<strong>(.*)</strong>)",
            r"(<p>(.*)</p>)",
        ]
        subst = "\\2"
        content_unfilt = re.sub(r"\r\n", "\\n", event["description"])
        content_unfilt = re.sub(regex[3], "\\2", content_unfilt)
        try:
            content_unfilt = re.sub(
                regex[1],
                "{0} \\3".format("-" * int(re.match(regex[1], content_unfilt)[2])),
                content_unfilt,
            )
        except TypeError:
            pass
        content_unfilt = re.sub(regex[2], "**\\2**", content_unfilt)
        content = re.sub(regex[0], subst, content_unfilt)

        e = discord.Embed(
            title=str(event["name"]).strip(" is due"),
            description=content,
            colour=discord.Colour.blue(),
            url=event["url"],
        )
        e.set_author(
            name=event["course"]["fullname"],
            url=event["course"]["viewurl"],
            icon_url="https://cdn.discordapp.com/avatars/769367431109541918/11102322dbeaf7b4d20bf49a9ef62ed0.webp",
        )

        e.add_field(
            name="Last Modified",
            value=datetime.fromtimestamp(event["timemodified"]).strftime(
                "%A, %-d %B %Y, %H:%M"
            ),
        )
        e.add_field(
            name="Deadline",
            value=datetime.fromtimestamp(event["timesort"]).strftime(
                "%A, %-d %B %Y, %H:%M"
            ),
        )

        maximum = self.get_max_pages()
        e.set_footer(text=f"Page {menu.current_page + 1}/{maximum}")
        return e


class MoodleAPI(object):
    def __init__(self, base_url):
        self.session = aiohttp.ClientSession()
        self.base_url = base_url

    async def get_token(self, username: str, password: str):
        username = "username=" + username
        password = "password=" + urllib.parse.quote(password)
        res = None
        async with self.session.post(
            self.base_url
            + "login/token.php?service=moodle_mobile_app"
            + "&"
            + "&".join([username, password])
        ) as page:
            res = json.loads(await page.text())
        try:
            if res:
                return res["token"]
            return None
        except KeyError:
            return None

    async def get_func_json(self, token: str, function: str):
        async with self.session.post(
            self.base_url
            + "webservice/rest/server.php?moodlewsrestformat=json&wstoken="
            + token
            + "&wsfunction="
            + function
        ) as page:
            res = json.loads(await page.text())
        try:
            if res:
                return res
            return None
        except KeyError:
            return None

    async def get_userid(self, token: str):
        userid = await self.get_func_json(token, "core_webservice_get_site_info")
        try:
            userid = userid["userid"]
        except KeyError:
            return None
        return userid


class Moodle(commands.Cog, name="moodle"):
    def __init__(self, bot):
        self.bot = bot
        self.logger = self.bot.logger
        self.conn = self.bot.pool
        self.moodle = MoodleAPI(self.bot.config["moodle_baseurl"])

    async def is_registered(self, ctx):
        token = await self.fetch_token(ctx.author)
        return token is not None

    async def fetch_token(self, member: discord.User):
        token = await self.conn.fetchrow(
            """
            SELECT * FROM elearningbot.token 
            WHERE user_id = $1
            """,
            str(member.id),
        )
        if not token:
            return None
        return token[1]

    async def fetch_userid(self, member: discord.User):
        token = await self.fetch_token(member)
        return await self.moodle.get_userid(token)

    @commands.command()
    @commands.guild_only()
    async def register(self, ctx):
        """Register your elearning account to Elearning Bot."""

        def check(msg):
            return (
                msg.content is not None
                and msg.author == ctx.author
                and isinstance(msg.channel, discord.DMChannel)
            )

        # Check if user already registered
        token = await self.fetch_token(ctx.author)
        if token:
            e = discord.Embed(
                description=self.bot._("You already have token registered!"),
                colour=discord.Colour.blue(),
            )
            return await ctx.send(embed=e)

        auth = {"username": "", "password": ""}

        e = discord.Embed(
            description=self.bot._(
                "Please check your DM to complete the registration!"
            ),
            colour=discord.Colour.blue(),
        )
        await ctx.send(embed=e)
        for i in list(auth.keys()):
            try:
                info = ""
                if i == "password":
                    info = "*This will not stored in the bot's database!"
                elif i == "username":
                    info = "*Usually registered as your student ID."

                if info:
                    e = discord.Embed(
                        title=self.bot._(f"{i.title()}?"),
                        description=info,
                        colour=discord.Colour.blue(),
                    )
                else:
                    e = discord.Embed(
                        title=self.bot._(f"{i.title()}?"), colour=discord.Colour.blue()
                    )
                bot_msg = await ctx.author.send(embed=e)
                wait = await self.bot.wait_for("message", timeout=60.0, check=check)
            except asyncio.TimeoutError:
                e = discord.Embed(
                    description=self.bot._("Timed Out! Cancelled"),
                    colour=discord.Colour.blue(),
                )
                await ctx.send(embed=e)
                return
            else:
                auth[i] = wait.content

        token = await self.moodle.get_token(auth["username"], auth["password"])
        if not token:
            e = discord.Embed(
                title=self.bot._("Registration Failed"),
                description=self.bot._("Invalid login, please try again"),
                colour=discord.Colour.blue(),
            )
            return await ctx.author.send(embed=e)

        await self.conn.execute(
            """
            INSERT INTO elearningbot.token (user_id, token)
            VALUES ($1, $2)
            """,
            str(ctx.author.id),
            token,
        )
        desc = f"Congratulation your token successfully registered!\n\n**Your account information**:\nUsername: `{auth['username']}`\nPassword: ||``{auth['password']}``||\nToken: ||`{token}`||\n"
        e = discord.Embed(
            title="User Information", description=desc, colour=discord.Colour.blue()
        )
        await ctx.author.send(embed=e)
        e = discord.Embed(
            title="Registration Success",
            description=f"Congratulation {ctx.author.mention}, your token successfully registered!",
            colour=discord.Colour.blue(),
        )
        await ctx.send(embed=e)

    @commands.group()
    async def get(self, ctx):
        """Get information from elearning."""
        pass

    @get.command(name="id")
    async def _id(self, ctx):
        user_id = await self.fetch_userid(ctx.author)
        await ctx.send(f"{ctx.author.mention}, your elearning user id is `{user_id}`")

    @get.command(aliases=["fucking_homework"])
    async def homework(self, ctx):
        if not await self.is_registered(ctx):
            return await ctx.send("You're not registered, please do `!register` first")

        user_id = await self.fetch_userid(ctx.author)
        token = await self.fetch_token(ctx.author)
        events = await self.moodle.get_func_json(
            token, "core_calendar_get_calendar_upcoming_view"
        )

        menu = ziPages(MoodleEventsPageSource(events["events"]))
        await menu.start(ctx)


def setup(bot):
    bot.add_cog(Moodle(bot))
