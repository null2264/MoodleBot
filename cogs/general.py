import asyncio
import aiohttp
import discord
import json

from .utils.paginator import ziPages
from discord.ext import commands, menus

class SearxResultsPageSource(menus.ListPageSource):
    def __init__(self, ctx, results):
        self.ctx = ctx
        super().__init__(entries=results, per_page=1)

    def format_page(self, menu, page):
        e = discord.Embed(title=page['title'], description=page['content'], url=page['pretty_url'], colour=discord.Colour.dark_gray())
        e.set_thumbnail(url='https://searx.github.io/searx/_static/searx_logo_small.png')
        maximum = self.get_max_pages()
        e.set_footer(text=f"Requested by {self.ctx.author} - Page {menu.current_page + 1}/{maximum}", icon_url=self.ctx.author.avatar_url)
        return e

class SearxAPI:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = aiohttp.ClientSession()
        self.engines = ['duckduckgo', 'google', 'bing']

    async def get_results(self, query: str) -> dict:
        """
        Search query and get all the results.
        """
        payload = {'q': query, 'format': 'json', 'language': 'en-US', 'safesearch': 1, 'engines': ",".join(self.engines)}
        async with self.session.post(self.base_url, data=payload) as page:
            _json = json.loads(await page.text())
        return _json['results']


class General(commands.Cog, name="general"):
    def __init__(self, bot):
        self.bot = bot
        self.logger = self.bot.logger
        self.searx = SearxAPI('https://searx.lukesmith.xyz/')

    @commands.command(aliases=['searx'])
    async def search(self, ctx, *, keyword):
        results = await self.searx.get_results(keyword)
        menu = ziPages(source=SearxResultsPageSource(ctx, results))
        await menu.start(ctx)


def setup(bot):
    bot.add_cog(General(bot))
