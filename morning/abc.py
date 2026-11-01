from abc import ABC
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Awaitable, Callable, Dict, List, Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red


@dataclass
class Content:
    """One Discord message, built entirely by a section."""

    text: Optional[str] = None
    embeds: List[discord.Embed] = field(default_factory=list)
    files: List[discord.File] = field(default_factory=list)


# async def render(self, today) -> the section's message, or None to skip it today.
Renderer = Callable[[Any, date], Awaitable[Optional[Content]]]


class MixinMeta(ABC):
    """Attributes the manager and every section mixin can rely on."""

    bot: Red
    config: Config

    def section_conf(self, key: str) -> Any:
        """The Config group that section `key` stores its data in."""
        return self.config.custom(key)


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """Lets the Cog class combine ABC-based mixins."""


@dataclass(frozen=True)
class SectionInfo:
    key: str
    order: int
    description: str
    defaults: Dict[str, Any]


def section(
    key: str,
    *,
    order: int = 50,
    description: str = "",
    defaults: Optional[Dict[str, Any]] = None,
) -> Callable[[Renderer], Renderer]:
    """Mark a mixin method as a morning section renderer.

    `defaults` are registered as the section's own Config group, reached with
    `self.section_conf(key)`. Lower `order` is sent first.
    """

    def deco(func: Renderer) -> Renderer:
        func.__morning_section__ = SectionInfo(key, order, description, defaults or {})
        return func

    return deco
