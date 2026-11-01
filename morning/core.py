import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from redbot.core import commands

from .abc import MixinMeta

log = logging.getLogger("red.cogged-up.morning")

CHECK_EVERY = 30  # seconds
# A digest that wasn't sent at its time (bot offline) still goes out if the bot is back within this.
GRACE = timedelta(hours=1)
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _due(settings: Dict[str, Any], now: datetime) -> datetime:
    hour, minute = map(int, settings["time"].split(":"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


class Core(MixinMeta):
    """The manager: schedule, delivery, settings and the section registry."""

    async def cog_load(self) -> None:
        self._task = asyncio.create_task(self._scheduler())

    async def cog_unload(self) -> None:
        if self._task:
            self._task.cancel()

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        await self.config.user_from_id(user_id).clear()
        for info, _ in self.sections:
            await self.config.custom(info.key, user_id).clear()

    # ---- scheduling -------------------------------------------------------------------------

    async def _scheduler(self) -> None:
        await self.bot.wait_until_red_ready()
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Morning scheduler tick failed")
            await asyncio.sleep(CHECK_EVERY)

    async def _tick(self) -> None:
        for user_id, settings in (await self.config.all_users()).items():
            if not settings["enabled"]:
                continue
            now = datetime.now(ZoneInfo(settings["timezone"]))
            today = now.date()
            if settings["last_sent"] == today.isoformat():
                continue
            due = _due(settings, now)
            if not due <= now < due + GRACE:
                continue
            # Mark first so a failing delivery can't turn into a message every 30 s.
            await self.config.user_from_id(user_id).last_sent.set(today.isoformat())
            user = self.bot.get_user(user_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.HTTPException:
                    log.warning("Morning: can't find user %s", user_id)
                    continue
            await self._deliver(user, settings, today)

    async def _deliver(self, user: discord.abc.User, settings: Dict[str, Any], today: date) -> None:
        embed = await self.build_digest(user, today)
        destination: Optional[discord.abc.Messageable] = None
        if settings["channel"]:
            destination = self.bot.get_channel(settings["channel"])
        if destination is None:
            destination = user
        try:
            await destination.send(content=user.mention if destination is not user else None, embed=embed)
        except discord.HTTPException:
            log.warning("Morning: couldn't deliver to %s for user %s", destination, user.id)
            return
        self.bot.dispatch("morning_sent", user, today)

    async def build_digest(self, user: discord.abc.User, today: date) -> discord.Embed:
        """Render every enabled section for `user` into one embed."""
        disabled = await self.config.user(user).disabled_sections()
        embed = discord.Embed(
            title=f"☀️ Good morning · {today:%A, %-d %B}", colour=discord.Colour.gold()
        )
        for info, render in self.sections:
            if info.key in disabled:
                continue
            try:
                text = await render(user, today)
            except Exception:
                log.exception("Morning section %s failed for user %s", info.key, user.id)
                text = "⚠️ This section failed to render; see the bot logs."
            if text:
                embed.add_field(name=info.title, value=text[:1024], inline=False)
        if not embed.fields:
            embed.description = "Nothing on today. Enjoy it."
        return embed

    def _section_keys(self) -> str:
        return ", ".join(f"`{info.key}`" for info, _ in self.sections)

    def _find_section(self, key: str):
        return next((info for info, _ in self.sections if info.key == key.lower()), None)

    # ---- commands ---------------------------------------------------------------------------

    @commands.group(name="morning", invoke_without_command=True)
    async def morning(self, ctx: commands.Context) -> None:
        """Show your morning digest settings."""
        settings = await self.config.user(ctx.author).all()
        now = datetime.now(ZoneInfo(settings["timezone"]))
        nxt = _due(settings, now)
        if nxt <= now or settings["last_sent"] == now.date().isoformat():
            nxt += timedelta(days=1)
        if settings["channel"]:
            where = f"<#{settings['channel']}>"
        else:
            where = "your DMs"
        status = f"**On** · next <t:{int(nxt.timestamp())}:R>" if settings["enabled"] else "**Off**"
        sections = "\n".join(
            f"{'⬜' if info.key in settings['disabled_sections'] else '✅'} `{info.key}` · "
            f"{info.title}{f' · {info.description}' if info.description else ''}"
            for info, _ in self.sections
        )
        p = ctx.clean_prefix
        embed = discord.Embed(
            title="Morning digest",
            description=(
                f"{status}\nEvery day at **{settings['time']}** ({settings['timezone']}) in {where}."
            ),
            colour=discord.Colour.gold(),
        )
        embed.add_field(name="Sections", value=sections or "None installed.", inline=False)
        embed.set_footer(
            text=f"{p}morning on|off · time HH:MM · timezone <tz> · here|dm · "
            f"enable|disable <section> · now"
        )
        await ctx.send(embed=embed)

    @morning.command(name="on")
    async def morning_on(self, ctx: commands.Context) -> None:
        """Start sending your daily digest."""
        await self.config.user(ctx.author).enabled.set(True)
        await ctx.send("Morning digest **on**.")
        await ctx.invoke(self.morning)

    @morning.command(name="off")
    async def morning_off(self, ctx: commands.Context) -> None:
        """Stop sending your daily digest."""
        await self.config.user(ctx.author).enabled.set(False)
        await ctx.send("Morning digest **off**.")

    @morning.command(name="time")
    async def morning_time(self, ctx: commands.Context, hh_mm: str) -> None:
        """Set the send time, 24h `HH:MM` in your timezone."""
        match = TIME_RE.match(hh_mm)
        if not match:
            await ctx.send("Use 24-hour `HH:MM`, e.g. `07:30`.")
            return
        value = f"{int(match[1]):02d}:{match[2]}"
        await self.config.user(ctx.author).time.set(value)
        await ctx.send(f"Digest time set to **{value}**.")

    @morning.command(name="timezone", aliases=["tz"])
    async def morning_timezone(self, ctx: commands.Context, tz: str) -> None:
        """Set your timezone (IANA name, e.g. `Asia/Jakarta`)."""
        try:
            zone = ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            await ctx.send(
                f"Unknown timezone `{tz}`. Use an IANA name like `Asia/Jakarta` or `Europe/London`."
            )
            return
        await self.config.user(ctx.author).timezone.set(zone.key)
        await ctx.send(f"Timezone set to **{zone.key}** (it's {datetime.now(zone):%H:%M} there).")

    @morning.command(name="here")
    @commands.guild_only()
    async def morning_here(self, ctx: commands.Context) -> None:
        """Post your digest in this channel instead of DMs."""
        if not ctx.channel.permissions_for(ctx.me).send_messages:
            await ctx.send("I can't post in this channel.")
            return
        await self.config.user(ctx.author).channel.set(ctx.channel.id)
        await ctx.send(f"Your digest will be posted in {ctx.channel.mention}.")

    @morning.command(name="dm")
    async def morning_dm(self, ctx: commands.Context) -> None:
        """Send your digest by DM (the default)."""
        await self.config.user(ctx.author).channel.clear()
        await ctx.send("Your digest will be sent by DM.")

    @morning.command(name="enable")
    async def morning_enable(self, ctx: commands.Context, section: str) -> None:
        """Include a section in your digest."""
        info = self._find_section(section)
        if info is None:
            await ctx.send(f"No section `{section}`. Sections: {self._section_keys()}.")
            return
        async with self.config.user(ctx.author).disabled_sections() as disabled:
            if info.key in disabled:
                disabled.remove(info.key)
        await ctx.send(f"**{info.title}** enabled.")

    @morning.command(name="disable")
    async def morning_disable(self, ctx: commands.Context, section: str) -> None:
        """Leave a section out of your digest."""
        info = self._find_section(section)
        if info is None:
            await ctx.send(f"No section `{section}`. Sections: {self._section_keys()}.")
            return
        async with self.config.user(ctx.author).disabled_sections() as disabled:
            if info.key not in disabled:
                disabled.append(info.key)
        await ctx.send(f"**{info.title}** disabled.")

    @morning.command(name="now", aliases=["preview"])
    async def morning_now(self, ctx: commands.Context) -> None:
        """Show today's digest here, right now (doesn't affect the schedule)."""
        tz = ZoneInfo(await self.config.user(ctx.author).timezone())
        async with ctx.typing():
            embed = await self.build_digest(ctx.author, datetime.now(tz).date())
        await ctx.send(embed=embed)
