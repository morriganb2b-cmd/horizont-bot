from typing import Optional
import discord


async def find_member(guild: discord.Guild, nickname: str) -> Optional[discord.Member]:
    # Try by mention or ID
    # If nickname looks like <@id>
    if nickname.startswith("<@") and nickname.endswith(">"):
        inner = nickname.strip("<@!>")
        if inner.isdigit():
            m = guild.get_member(int(inner))
            if m:
                return m
    # If numeric ID
    if nickname.isdigit():
        m = guild.get_member(int(nickname))
        if m:
            return m
    # Exact name or display name or with underscore
    for m in guild.members:
        names = {m.name.lower(), m.display_name.lower()}
        if nickname.lower() in names:
            return m
        # Replace spaces/underscores
        variants = {nickname.replace(" ", "_").lower(), nickname.replace("_", " ").lower()}
        if m.display_name.lower() in variants or m.name.lower() in variants:
            return m
    # Partial match fallback
    lowered = nickname.lower()
    candidates = [m for m in guild.members if lowered in m.display_name.lower() or lowered in m.name.lower()]
    if len(candidates) == 1:
        return candidates[0]
    return None
