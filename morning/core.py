import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from redbot.core import commands

from .abc import Content, MixinMeta

log = logging.getLogger("red.cogged-up.morning")

CHECK_EVERY = 30  # seconds
# Sections that weren't sent at their time (bot offline) still go out if the bot is back within this.
GRACE = timedelta(hours=1)
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _due(settings: Dict[str, Any], now: datetime) -> datetime:
    hour, minute = map(int, settings["time"].split(":"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


class Core(MixinMeta):
    """The manager: schedule, delivery, settings and the section registry. It never builds
    content itself; every message comes from a section."""

    async def cog_load(self) -> None:
        self._task = asyncio.create_task(self._scheduler())

    async def cog_unload(self) -> None:
        if self._task:
            self._task.cancel()

    async def red_delete_data_for_user(self, **kwargs) -> None:
        return

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
        settings = await self.config.all()
        if not settings["enabled"]:
            return
        now = datetime.now(ZoneInfo(settings["timezone"]))
        today = now.date()
        if settings["last_sent"] == today.isoformat():
            return
        due = _due(settings, now)
        if not due <= now < due + GRACE:
            return
        # Mark first so a failing delivery can't turn into a send every 30 s.
        await self.config.last_sent.set(today.isoformat())
        destination = await self._destination(settings)
        if destination is None:
            log.warning("Morning: no channel or owner to send to")
            return
        sent = await self._send_all(destination, await self.build_digest(today))
        if sent:
            self.bot.dispatch("morning_sent", today)

    async def _destination(self, settings: Dict[str, Any]) -> Optional[discord.abc.Messageable]:
        if settings["channel"]:
            channel = self.bot.get_channel(settings["channel"])
            if channel is not None:
                return channel
            log.warning("Morning: channel %s is gone; falling back to DM", settings["channel"])
        for owner_id in sorted(self.bot.owner_ids or ()):
            owner = self.bot.get_user(owner_id)
            if owner is None:
                try:
                    owner = await self.bot.fetch_user(owner_id)
                except discord.HTTPException:
                    continue
            return owner
        return None

    async def _send_all(self, destination: discord.abc.Messageable, contents: List[Content]) -> int:
        sent = 0
        for content in contents:
            try:
                await destination.send(
                    content=content.text, embeds=content.embeds, files=content.files
                )
                sent += 1
            except discord.HTTPException:
                log.exception("Morning: couldn't send a section to %s", destination)
        return sent

    async def build_digest(self, today: date) -> List[Content]:
        """Render every enabled section for `today`, in order. Sections returning None are left
        out; a section that raises is logged and skipped."""
        disabled = await self.config.disabled_sections()
        contents = []
        for info, render in self.sections:
            if info.key in disabled:
                continue
            try:
                content = await render(today)
            except Exception:
                log.exception("Morning section %s failed", info.key)
                continue
            if content is not None and (content.text or content.embeds or content.files):
                contents.append(content)
        return contents

    def _section_keys(self) -> str:
        return ", ".join(f"`{info.key}`" for info, _ in self.sections) or "none installed"

    def _find_section(self, key: str):
        return next((info for info, _ in self.sections if info.key == key.lower()), None)

    # ---- commands ---------------------------------------------------------------------------

    @commands.group(name="morning", invoke_without_command=True)
    @commands.is_owner()
    async def morning(self, ctx: commands.Context) -> None:
        """Show the morning schedule and sections."""
        settings = await self.config.all()
        now = datetime.now(ZoneInfo(settings["timezone"]))
        nxt = _due(settings, now)
        if nxt <= now or settings["last_sent"] == now.date().isoformat():
            nxt += timedelta(days=1)
        where = f"<#{settings['channel']}>" if settings["channel"] else "the owner's DMs"
        status = f"**On** · next <t:{int(nxt.timestamp())}:R>" if settings["enabled"] else "**Off**"
        sections = "\n".join(
            f"{'⬜' if info.key in settings['disabled_sections'] else '✅'} `{info.key}`"
            f"{f' · {info.description}' if info.description else ''}"
            for info, _ in self.sections
        )
        p = ctx.clean_prefix
        await ctx.send(
            f"{status}\nEvery day at **{settings['time']}** ({settings['timezone']}) in {where}.\n"
            f"**Sections**\n{sections or 'None installed.'}\n"
            f"-# {p}morning on|off · time HH:MM · timezone <tz> · here|dm · "
            f"enable|disable <section> · now"
        )

    @morning.command(name="on")
    async def morning_on(self, ctx: commands.Context) -> None:
        """Start sending the sections every day."""
        await self.config.enabled.set(True)
        await ctx.send("Morning **on**.")
        await ctx.invoke(self.morning)

    @morning.command(name="off")
    async def morning_off(self, ctx: commands.Context) -> None:
        """Stop sending."""
        await self.config.enabled.set(False)
        await ctx.send("Morning **off**.")

    @morning.command(name="time")
    async def morning_time(self, ctx: commands.Context, hh_mm: str) -> None:
        """Set the send time, 24h `HH:MM` in the configured timezone."""
        match = TIME_RE.match(hh_mm)
        if not match:
            await ctx.send("Use 24-hour `HH:MM`, e.g. `07:30`.")
            return
        value = f"{int(match[1]):02d}:{match[2]}"
        await self.config.time.set(value)
        await ctx.send(f"Send time set to **{value}**.")

    @morning.command(name="timezone", aliases=["tz"])
    async def morning_timezone(self, ctx: commands.Context, tz: str) -> None:
        """Set the timezone (IANA name, e.g. `Asia/Jakarta`)."""
        try:
            zone = ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            await ctx.send(
                f"Unknown timezone `{tz}`. Use an IANA name like `Asia/Jakarta` or `Europe/London`."
            )
            return
        await self.config.timezone.set(zone.key)
        await ctx.send(f"Timezone set to **{zone.key}** (it's {datetime.now(zone):%H:%M} there).")

    @morning.command(name="here")
    @commands.guild_only()
    async def morning_here(self, ctx: commands.Context) -> None:
        """Send to this channel instead of DMs."""
        if not ctx.channel.permissions_for(ctx.me).send_messages:
            await ctx.send("I can't post in this channel.")
            return
        await self.config.channel.set(ctx.channel.id)
        await ctx.send(f"Morning will be sent in {ctx.channel.mention}.")

    @morning.command(name="dm")
    async def morning_dm(self, ctx: commands.Context) -> None:
        """Send by DM to the bot owner (the default)."""
        await self.config.channel.clear()
        await ctx.send("Morning will be sent by DM.")

    @morning.command(name="enable")
    async def morning_enable(self, ctx: commands.Context, section: str) -> None:
        """Include a section."""
        info = self._find_section(section)
        if info is None:
            await ctx.send(f"No section `{section}`. Sections: {self._section_keys()}.")
            return
        async with self.config.disabled_sections() as disabled:
            if info.key in disabled:
                disabled.remove(info.key)
        await ctx.send(f"`{info.key}` enabled.")

    @morning.command(name="disable")
    async def morning_disable(self, ctx: commands.Context, section: str) -> None:
        """Leave a section out."""
        info = self._find_section(section)
        if info is None:
            await ctx.send(f"No section `{section}`. Sections: {self._section_keys()}.")
            return
        async with self.config.disabled_sections() as disabled:
            if info.key not in disabled:
                disabled.append(info.key)
        await ctx.send(f"`{info.key}` disabled.")

    @morning.command(name="now", aliases=["preview"])
    async def morning_now(self, ctx: commands.Context) -> None:
        """Send today's sections here, right now (doesn't affect the schedule)."""
        tz = ZoneInfo(await self.config.timezone())
        async with ctx.typing():
            contents = await self.build_digest(datetime.now(tz).date())
        if not contents:
            await ctx.send("No section has anything to send today.")
            return
        await self._send_all(ctx, contents)
