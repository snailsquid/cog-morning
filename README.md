# morning

Example cog created by new-cog. Replace this README when you build the real cog.

## Commands

| Command | Who | What |
|---|---|---|
| `[p]morning` | anyone | Says hello and increments a counter. |
| `[p]morning reset` | owner | Resets the counter. |

## Events emitted

| Event | Listener signature | When |
|---|---|---|
| `morning_hello` | `on_morning_hello(self, user: discord.abc.User, count: int)` | After `[p]morning` runs. |

## Public methods

None.

## Secrets

None. (If needed: `[p]set api <service> key,<value>`, read with `bot.get_shared_api_tokens("<service>")`.)
