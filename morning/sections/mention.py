from datetime import datetime
from typing import Optional

from ..abc import Content, MixinMeta, section


class Mention(MixinMeta):
    @section("mention", order=0, description="@-mentions the owner, so the morning pings")
    async def render_mention(self, now: datetime) -> Optional[Content]:
        mentions = " ".join(f"<@{i}>" for i in sorted(self.bot.owner_ids or ()))
        return Content(text=mentions) if mentions else None
