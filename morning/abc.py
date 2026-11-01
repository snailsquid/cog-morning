from abc import ABC
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable, Dict, Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

# async def render(self, user, today) -> text for the digest, or None to skip the section today.
Renderer = Callable[[Any, discord.abc.User, date], Awaitable[Optional[str]]]


class MixinMeta(ABC):
    """Attributes the manager and every section mixin can rely on."""

    bot: Red
    config: Config

    def section_conf(self, key: str, user: discord.abc.User) -> Any:
        """The Config group that section `key` stores this user's data in."""
        return self.config.custom(key, user.id)


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """Lets the Cog class combine ABC-based mixins."""


@dataclass(frozen=True)
class SectionInfo:
    key: str
    title: str
    order: int
    description: str
    defaults: Dict[str, Any]


def section(
    key: str,
    title: str,
    *,
    order: int = 50,
    description: str = "",
    defaults: Optional[Dict[str, Any]] = None,
) -> Callable[[Renderer], Renderer]:
    """Mark a mixin method as a morning section renderer.

    `defaults` are registered as a per-user Config group, reached with
    `self.section_conf(key, user)`. Lower `order` renders first.
    """

    def deco(func: Renderer) -> Renderer:
        func.__morning_section__ = SectionInfo(key, title, order, description, defaults or {})
        return func

    return deco
