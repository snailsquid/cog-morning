from typing import List, Tuple

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass, SectionInfo
from .core import Core
from .sections import SECTIONS


class Morning(Core, *SECTIONS, commands.Cog, metaclass=CompositeMetaClass):
    """Sends the morning sections at a set time each day."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=426660349173, force_registration=True)
        self.config.register_global(
            enabled=False,
            time="07:00",
            channel_id=None,  # None = DM the bot owner (not `channel`: that name is a Config method)
            disabled_sections=[],
            last_sent=None,  # ISO date, in the profile timezone
        )
        self.sections: List[Tuple[SectionInfo, object]] = []
        for name in dir(type(self)):
            info = getattr(getattr(type(self), name, None), "__morning_section__", None)
            if info is None:
                continue
            self.config.init_custom(info.key, 0)
            self.config.register_custom(info.key, **info.defaults)
            self.sections.append((info, getattr(self, name)))
        self.sections.sort(key=lambda s: (s[0].order, s[0].key))
        self._task = None
