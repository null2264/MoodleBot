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
from pytz import timezone


def bar_make(value, gap, *, length=10, point=False, fill="█", empty="░"):
    bar = ""
    scaled_value = (value / gap) * length
    for i in range(1, (length + 1)):
        check = (i == round(scaled_value)) if point else (i <= scaled_value)
        bar += fill if check else empty
    if point and (bar.count(fill) == 0):
        bar = fill + bar[1:]
    return bar


class MoodleCoursesPageSource(menus.ListPageSource):
    def __init__(self, ctx, courses):
        self.ctx = ctx
        super().__init__(entries=courses, per_page=1)

    def format_page(self, menu, course):
        weblink = f"https://elearning.binadarma.ac.id/course/view.php?id={course['id']}"
        e = discord.Embed(
            title=course["displayname"], url=weblink, colour=discord.Colour.blue()
        )
        e.add_field(
            name="Start",
            value=datetime.fromtimestamp(
                course["startdate"], timezone("Asia/Jakarta")
            ).strftime("%A, %-d %B %Y, %H:%M"),
        )
        e.add_field(
            name="End",
            value=datetime.fromtimestamp(
                course["enddate"], timezone("Asia/Jakarta")
            ).strftime("%A, %-d %B %Y, %H:%M"),
        )
        e.add_field(
            name="Progress",
            value=f"{bar_make(round(course['progress']), 100, length=18)} {round(course['progress'])}%",
            inline=False,
        )
        e.set_author(name=", ".join([x["fullname"] for x in course["lecturers"]]))
        maximum = self.get_max_pages()
        e.set_footer(
            text=f"Requested by {self.ctx.author} - Page {menu.current_page + 1}/{maximum}",
            icon_url=self.ctx.author.avatar_url,
        )
        return e


class MoodleEventsPageSource(menus.ListPageSource):
    def __init__(self, ctx, events):
        self.ctx = ctx
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
            value=datetime.fromtimestamp(
                event["timemodified"], timezone("Asia/Jakarta")
            ).strftime("%A, %-d %B %Y, %H:%M"),
        )
        e.add_field(
            name="Deadline",
            value=datetime.fromtimestamp(
                event["timesort"], timezone("Asia/Jakarta")
            ).strftime("%A, %-d %B %Y, %H:%M"),
        )

        maximum = self.get_max_pages()
        e.set_footer(
            text=f"Requested by {self.ctx.author} - Page {menu.current_page + 1}/{maximum}",
            icon_url=self.ctx.author.avatar_url,
        )
        return e


class MoodleAPI(object):
    def __init__(self, base_url):
        self.session = aiohttp.ClientSession()
        self.base_url = base_url

    async def get_token(self, username: str, password: str):
        """
        Login to Moodle.

        Required by most Moodle webservice function.
        """
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
        """
        Request function.

        Get data with specific Moodle webservice function.
        """
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

    async def get_userid(self, token: str) -> str:
        """
        Get userid from token.

        Useful for some functions that require `userid=` parameter
        """
        userid = await self.get_func_json(token, "core_webservice_get_site_info")
        try:
            userid = userid["userid"]
        except KeyError:
            return None
        return userid

    async def get_raw_enrolled_courses(self, userid, token) -> list:
        """
        Get list of raw enrolled courses. Unfiltered
        """
        _courses = await self.get_func_json(
            token, f"core_enrol_get_users_courses&userid={userid}"
        )
        courses = []
        for course in _courses:
            info = await self.get_course_info(course["id"], token)
            courses.append(
                {
                    "id": info["id"],
                    "displayname": info["displayname"],
                    "startdate": info["startdate"],
                    "enddate": info["enddate"],
                    "progress": course["progress"],
                    "lecturers": info["contacts"],
                }
            )

        return list(courses)

    async def get_enrolled_courses(self, userid, token) -> list:
        """
        Get list of enrolled courses. Filtered, only show courses that still on-going
        """
        unfiltered = await self.get_raw_enrolled_courses(userid, token)
        # _json = await self.get_func_json(token, f"core_enrol_get_users_courses&userid={userid}")
        courses = []
        # filter courses that already ends
        for course in unfiltered:
            if datetime.now().timestamp() < course["enddate"]:
                courses.append(course)
        return courses

    async def get_course_info(self, courseid, token) -> dict:
        """
        Get course full information.
        """
        info = await self.get_func_json(
            token, f"core_course_get_courses_by_field&field=id&value={courseid}"
        )
        return info["courses"][0]


class Moodle(commands.Cog, name="moodle"):
    def __init__(self, bot):
        self.bot = bot
        global t_
        t_ = self.bot._
        self.logger = self.bot.logger
        self.conn = self.bot.pool
        self.moodle = MoodleAPI(self.bot.config["moodle_baseurl"])
        global moodle
        moodle = self.moodle

    async def is_registered(self, ctx) -> bool:
        """
        Check if user's token registered.
        """
        token = await self.fetch_token(ctx.author)
        return token is not None

    async def fetch_token(self, member: discord.User) -> str:
        """
        Get token from database
        """
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
        """
        Get user's Moodle userid
        """
        token = await self.fetch_token(member)
        return await self.moodle.get_userid(token)

    @commands.command()
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

        if str(ctx.channel.type) == "text":
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
                    info = t_("*This will not stored in the bot's database!")
                elif i == "username":
                    info = t_("*Usually registered as your student ID.")

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
        desc = (
            t_(
                "Congratulation your token successfully registered!\n\n**Your account information**:\nUsername: `"
            )
            + auth["username"]
            + t_("`\nPassword: ||``")
            + auth["password"]
            + t_("``||\nToken: ||`")
            + token
            + "`||\n"
        )
        e = discord.Embed(
            title=t_("User Information"), description=desc, colour=discord.Colour.blue()
        )
        await ctx.author.send(embed=e)
        if ctx.channel.type == "text":
            e = discord.Embed(
                title=t_("Registration Success"),
                description=t_(
                    "Congratulation {0}, your token successfully registered!"
                ).format(ctx.author.mention),
                colour=discord.Colour.blue(),
            )
            await ctx.send(embed=e)

    @commands.group(invoke_without_command=True, usage="(keyword/option)")
    async def get(self, ctx, *, keyword):
        """Get an information from Moodle, or search for something using Searx."""
        await ctx.invoke(self.bot.get_command("search"), keyword=keyword)

    @get.command(name="id")
    async def _id(self, ctx):
        """
        Get userid from Moodle.
        """
        user_id = await self.fetch_userid(ctx.author)
        await ctx.send(
            t_("{0}, your elearning user id is `{1}`").format(
                ctx.author.mention, user_id
            )
        )

    @get.command(aliases=["fucking_homework", "calendar"])
    async def homework(self, ctx):
        """
        Get upcoming events from Moodle.
        """
        if not await self.is_registered(ctx):
            return await ctx.send(
                t_("You're not registered, please do `!register` first")
            )

        user_id = await self.fetch_userid(ctx.author)
        token = await self.fetch_token(ctx.author)
        events = await self.moodle.get_func_json(
            token, "core_calendar_get_calendar_upcoming_view"
        )

        try:
            menu = ziPages(MoodleEventsPageSource(ctx, events["events"]))
            await menu.start(ctx)
        except KeyError:
            await ctx.send("Bot failed to get the homeworks, it might be that the site is down.")

    @get.command()
    async def courses(self, ctx):
        """
        Get list of all available courses
        """
        user_id = await self.fetch_userid(ctx.author)
        token = await self.fetch_token(ctx.author)
        courses = await self.moodle.get_enrolled_courses(user_id, token)
        menu = ziPages(MoodleCoursesPageSource(ctx, courses))
        await menu.start(ctx)


def setup(bot):
    bot.add_cog(Moodle(bot))
