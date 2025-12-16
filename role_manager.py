from dataclasses import dataclass
from typing import Optional
import discord


@dataclass
class RoleIDs:
    leader: int
    deputy: int
    reprimand_1: int
    reprimand_2: int


class RoleManager:
    def __init__(self, guild: discord.Guild, roles: RoleIDs):
        self.guild = guild
        self.roles = roles

    def get_role(self, role_id: int) -> Optional[discord.Role]:
        return self.guild.get_role(role_id)

    async def ensure_roles_exist(self) -> bool:
        needed = [self.roles.leader, self.roles.deputy, self.roles.reprimand_1, self.roles.reprimand_2]
        return all(self.get_role(r) is not None for r in needed)

    async def add_role(self, member: discord.Member, role_id: int):
        role = self.get_role(role_id)
        if role and role not in member.roles:
            await member.add_roles(role, reason="HorizontRP Bot role add")

    async def remove_role(self, member: discord.Member, role_id: int):
        role = self.get_role(role_id)
        if role and role in member.roles:
            await member.remove_roles(role, reason="HorizontRP Bot role remove")

    async def remove_roles(self, member: discord.Member, *role_ids: int):
        roles = [self.get_role(r) for r in role_ids]
        roles = [r for r in roles if r and r in member.roles]
        if roles:
            await member.remove_roles(*roles, reason="HorizontRP Bot bulk role remove")

    async def set_leader(self, member: discord.Member):
        await self.remove_role(member, self.roles.deputy)
        await self.add_role(member, self.roles.leader)

    async def set_deputy(self, member: discord.Member):
        await self.remove_role(member, self.roles.leader)
        await self.add_role(member, self.roles.deputy)

    async def clear_punishment_roles(self, member: discord.Member):
        await self.remove_roles(member, self.roles.reprimand_1, self.roles.reprimand_2)

    async def apply_reprimand_role(self, member: discord.Member, count: int):
        # 1 -> reprimand_1, 2 -> reprimand_2, 3 -> handled externally (dismissal)
        if count == 1:
            await self.remove_role(member, self.roles.reprimand_2)
            await self.add_role(member, self.roles.reprimand_1)
        elif count == 2:
            await self.remove_role(member, self.roles.reprimand_1)
            await self.add_role(member, self.roles.reprimand_2)
