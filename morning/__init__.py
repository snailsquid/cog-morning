from redbot.core.bot import Red

from .morning import Morning


async def setup(bot: Red) -> None:
    await bot.add_cog(Morning(bot))
