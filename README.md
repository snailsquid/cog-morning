# morning

Sends the morning **sections** at a set time each day. The manager only schedules and delivers;
it never builds content. Each section builds its own message (text, embeds, images, files), and
each section is sent as its own message, in order.

The timezone is the owner's, from the [Profile](https://github.com/snailsquid/cog-profile) cog
(`[p]profile tz <tz>`; UTC if Profile isn't loaded).

One global schedule, sent by DM to the bot owner unless a channel is set. Owner-only commands.

## Commands

| Command | Who | What |
|---|---|---|
| `[p]morning` | owner | Schedule, next send time, and which sections are on. |
| `[p]morning on` / `off` | owner | Start / stop the daily send. |
| `[p]morning time <HH:MM>` | owner | Send time, 24h, in your timezone (default `07:00`). |
| `[p]morning here` / `dm` | owner | Send in this channel, or by DM to the owner (default). |
| `[p]morning enable <section>` / `disable <section>` | owner | Include / leave out a section. |
| `[p]morning now` | owner | Send today's sections here right now (doesn't affect the schedule). Alias `preview`. |

If the bot is offline at send time, the sections still go out if it's back within an hour.

## Sections

| Key | What | From |
|---|---|---|
| `weekcard` | week number, date, week progress, days left this year (image) | [cog-weekcard](https://github.com/snailsquid/cog-weekcard) |

Sections come from two places: mixins in this repo (`morning/sections/`), or **other cogs**
that offer them (below). `[p]morning` lists both; enable/disable works the same for both.

### Adding a section

1. Create `morning/sections/<key>.py` with a mixin:

   ```python
   from datetime import datetime
   from typing import Optional

   import discord
   from redbot.core import commands

   from ..abc import Content, MixinMeta, section
   from ..core import Core


   class Weather(MixinMeta):
       @section("weather", order=10, description="today's forecast", defaults={"city": None})
       async def render_weather(self, now: datetime) -> Optional[Content]:
           city = await self.section_conf("weather").city()
           if not city:
               return None  # skip this section today
           embed = discord.Embed(title=f"🌤️ {city}", description="28°C, sunny")
           embed.set_image(url="https://example.com/radar.png")
           return Content(embeds=[embed])  # also: Content(text=..., files=[discord.File(...)])

       @Core.morning.command(name="weather")  # optional settings commands
       async def morning_weather(self, ctx: commands.Context, *, city: str) -> None:
           await self.section_conf("weather").city.set(city)
           await ctx.send("Saved.")
   ```

2. Add it to `SECTIONS` in `morning/sections/__init__.py`.

### Offering a section from another cog

Any loaded cog with a `morning_sections()` method shows up as a section; Morning looks for it
on every send, so load order doesn't matter and nothing needs registering or unregistering.
Nothing is imported from Morning:

```python
def morning_sections(self) -> list:
    return [{
        "key": "weekcard",          # unique; a key that already exists is ignored
        "order": 10,                # optional, default 50
        "description": "...",      # optional, shown in [p]morning
        "render": self.render_morning,
    }]

async def render_morning(self, now: datetime) -> Optional[dict]:
    # dict with any of "text", "embeds", "files"; or None to be skipped today
    return {"files": [discord.File(...)]}
```

The section keeps its data in its own cog's Config.

Rules:
- Renderers get `now`, a timezone-aware `datetime` in the profile timezone (`now.date()` is the day).
- A section returns one `Content` (one Discord message: `text`, up to 10 `embeds`, `files`) or
  `None` to be skipped. Create `discord.File` objects fresh on every render.
- The manager adds nothing: no header, titles or colours. A header is its own section.
- Section keys are unique. Method names (renderers and commands) must be unique across all mixins.
- A section's data lives only in its own `self.section_conf(key)` Config group, registered from
  `defaults`.
- A section that raises is logged and skipped; the other sections still send. Lower `order` is
  sent first.

## Events emitted

| Event | Listener signature | When |
|---|---|---|
| `morning_sent` | `on_morning_sent(self, day: datetime.date)` | After a scheduled send delivered at least one section. |

## Public methods

| Method | What |
|---|---|
| `await cog.build_digest(now) -> List[Content]` | Render the enabled sections for `now` (a timezone-aware `datetime`), in order. |
| `cog.all_sections() -> List[(SectionInfo, renderer)]` | Every section, this repo's and other cogs', in send order. |

## Data

Global settings, plus one Config group per section. No per-user data.

## Secrets

None.
