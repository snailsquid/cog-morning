# morning

A daily morning digest. One message per day at your chosen time, built from **sections**
(reminders today; more later). Each section can be switched on or off per user.

## Commands

| Command | Who | What |
|---|---|---|
| `[p]morning` | anyone | Your settings, next send time, and which sections are on. |
| `[p]morning on` / `off` | anyone | Start / stop your daily digest. |
| `[p]morning time <HH:MM>` | anyone | Send time, 24h, in your timezone (default `07:00`). |
| `[p]morning timezone <tz>` | anyone | IANA timezone, e.g. `Asia/Jakarta` (default `UTC`). Alias `tz`. |
| `[p]morning here` / `dm` | anyone | Post in this channel (with a mention) or by DM (default). |
| `[p]morning enable <section>` / `disable <section>` | anyone | Include / leave out a section. |
| `[p]morning now` | anyone | Show today's digest here right now (doesn't affect the schedule). Alias `preview`. |
| `[p]morning remind` | anyone | List your reminders. |
| `[p]morning remind add <when> <text>` | anyone | `when`: `today`, `tomorrow`, `YYYY-MM-DD`, `daily`, `weekdays`, `weekends`, or days like `mon,thu`. |
| `[p]morning remind remove <id>` | anyone | Remove a reminder. Aliases `rm`, `done`. |

If the bot is offline at send time, the digest still goes out if it's back within an hour.

## Sections

| Key | Title | Content |
|---|---|---|
| `reminders` | 📝 To do today | Reminders due today. One-off reminders are dropped once their day has passed. |

### Adding a section

1. Create `morning/sections/<key>.py` with a mixin:

   ```python
   from datetime import date
   from typing import Optional

   import discord

   from ..abc import MixinMeta, section
   from ..core import Core


   class Weather(MixinMeta):
       @section("weather", "🌤️ Weather", order=10, defaults={"city": None})
       async def render_weather(self, user: discord.abc.User, today: date) -> Optional[str]:
           city = await self.section_conf("weather", user).city()
           return f"Sunny in {city}" if city else None  # None/"" = skip today

       @Core.morning.command(name="weather")  # optional settings commands
       async def morning_weather(self, ctx, *, city: str) -> None:
           await self.section_conf("weather", ctx.author).city.set(city)
           await ctx.send("Saved.")
   ```

2. Add it to `SECTIONS` in `morning/sections/__init__.py`.

Rules: section keys are unique; method names (renderers and commands) must be unique across all
mixins; a section's data lives only in its own `section_conf(key, user)` group (registered from
`defaults`, cleared on data deletion). A section that raises shows a warning line instead of
breaking the digest. Lower `order` renders first.

## Events emitted

| Event | Listener signature | When |
|---|---|---|
| `morning_sent` | `on_morning_sent(self, user: discord.abc.User, day: datetime.date)` | After a scheduled digest is delivered. |

## Public methods

| Method | What |
|---|---|
| `await cog.build_digest(user, day) -> discord.Embed` | Render the digest for `user` on `day` (a `datetime.date`). |

## Data

Per-user settings, plus one Config group per section per user (e.g. reminders).
All cleared by `red_delete_data_for_user`.

## Secrets

None.
