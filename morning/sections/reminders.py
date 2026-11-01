from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import discord
from redbot.core import commands

from ..abc import MixinMeta, section
from ..core import Core

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PRESETS = {"daily": list(range(7)), "weekdays": list(range(5)), "weekends": [5, 6]}


def _parse_when(when: str, today: date) -> Optional[Dict[str, Any]]:
    """`today`, `tomorrow`, `YYYY-MM-DD`, `daily`, `weekdays`, `weekends`, or `mon,thu`."""
    when = when.lower()
    if when == "today":
        return {"date": today.isoformat(), "days": []}
    if when == "tomorrow":
        return {"date": (today + timedelta(days=1)).isoformat(), "days": []}
    if when in PRESETS:
        return {"date": None, "days": PRESETS[when]}
    try:
        return {"date": date.fromisoformat(when).isoformat(), "days": []}
    except ValueError:
        pass
    days = []
    for part in when.split(","):
        part = part.strip()[:3]
        if part not in DAYS:
            return None
        days.append(DAYS.index(part))
    return {"date": None, "days": sorted(set(days))}


def _describe(item: Dict[str, Any]) -> str:
    if item["date"]:
        return item["date"]
    for name, days in PRESETS.items():
        if item["days"] == days:
            return name
    return ",".join(DAYS[d] for d in item["days"])


class Reminders(MixinMeta):
    """Things to do today: one-off (by date) or repeating (by weekday)."""

    @section(
        "reminders",
        "📝 To do today",
        order=20,
        description="things to do today",
        defaults={"items": [], "next_id": 1},
    )
    async def render_reminders(self, user: discord.abc.User, today: date) -> Optional[str]:
        async with self.section_conf("reminders", user).items() as items:
            # Drop one-offs whose day has passed.
            items[:] = [i for i in items if not i["date"] or i["date"] >= today.isoformat()]
            due = [
                i for i in items if i["date"] == today.isoformat() or today.weekday() in i["days"]
            ]
        return "\n".join(f"• {i['text']}" for i in due) or None

    async def _user_today(self, user: discord.abc.User) -> date:
        return datetime.now(ZoneInfo(await self.config.user(user).timezone())).date()

    @Core.morning.group(name="remind", invoke_without_command=True)
    async def morning_remind(self, ctx: commands.Context) -> None:
        """List your reminders."""
        items: List[Dict[str, Any]] = await self.section_conf("reminders", ctx.author).items()
        if not items:
            await ctx.send(
                f"No reminders. Add one with `{ctx.clean_prefix}morning remind add <when> <text>`."
            )
            return
        lines = [f"`#{i['id']}` **{_describe(i)}** · {i['text']}" for i in items]
        await ctx.send(
            embed=discord.Embed(
                title="Your reminders", description="\n".join(lines)[:4000], colour=discord.Colour.gold()
            )
        )

    @morning_remind.command(name="add")
    async def morning_remind_add(self, ctx: commands.Context, when: str, *, text: str) -> None:
        """Add a reminder for your morning digest.

        `when` is `today`, `tomorrow`, a date (`2026-12-24`), `daily`, `weekdays`, `weekends`,
        or days like `mon,thu`.
        """
        today = await self._user_today(ctx.author)
        parsed = _parse_when(when, today)
        if parsed is None:
            await ctx.send(
                "I don't understand that `when`. Use `today`, `tomorrow`, `YYYY-MM-DD`, `daily`, "
                "`weekdays`, `weekends`, or days like `mon,thu`."
            )
            return
        if parsed["date"] and parsed["date"] < today.isoformat():
            await ctx.send("That date has already passed.")
            return
        conf = self.section_conf("reminders", ctx.author)
        rid = await conf.next_id()
        await conf.next_id.set(rid + 1)
        item = {"id": rid, "text": text, **parsed}
        async with conf.items() as items:
            items.append(item)
        await ctx.send(f"Added `#{rid}` (**{_describe(item)}**): {text}")

    @morning_remind.command(name="remove", aliases=["rm", "done"])
    async def morning_remind_remove(self, ctx: commands.Context, rid: int) -> None:
        """Remove a reminder by its number."""
        async with self.section_conf("reminders", ctx.author).items() as items:
            match = next((i for i in items if i["id"] == rid), None)
            if match:
                items.remove(match)
        if match is None:
            await ctx.send(f"No reminder `#{rid}`.")
            return
        await ctx.send(f"Removed `#{rid}`: {match['text']}")
