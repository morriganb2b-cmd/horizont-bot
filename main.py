import os
import re
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from utils.data_manager import DataManager, now_str
from utils.member_finder import find_member
from utils.role_manager import RoleIDs, RoleManager

# ===================== КОНФІГУРАЦІЯ / КОЛЬОРИ =====================
# Яскраві узгоджені кольори
COLOR_INFO = 0x00AEEF   # ℹ️ Інформація (синій)
COLOR_SUCCESS = 0x00E676  # ✅ Успіх (зелений)
COLOR_WARNING = 0xFFA500  # ⚠️ Попередження (помаранчевий)
COLOR_ERROR = 0xFF1744    # ❌ Помилка (червоний яскравий)
COLOR_REP_1 = 0xFFD700    # 🟡 Догана 1 (жовтий)
COLOR_REP_2 = 0xFF8C00    # 🟠 Догана 2 (темно-помаранчевий)
COLOR_DISMISSAL = 0xDC143C # 🟥 Звільнення (бордовий)
COLOR_NEWS = 0x9370DB     # 🟣 Новини (фіолетови��)
SEP = "────────────────────"

# Ідентифікатори ролей (замініть на власні)
ROLE_IDS = RoleIDs(
    leader=123456789012345678,
    deputy=123456789012345679,
    reprimand_1=123456789012345680,
    reprimand_2=123456789012345681,
)

# Ролі адміністрації (за назвами)
ADMIN_ROLES = [
    "🌩️┆Заступник Головного Адміністратора┆🌩️",
    "⚡┆Головний Адміністратор┆⚡",
]

# Шляхи до даних / логів
DATA_PATH = os.path.join(os.path.dirname(__file__), "leaders_data.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "bot_logs.txt")

# Префікс команд
COMMAND_PREFIX = "!"

# Автознищення повідомлень (сек)
AUTO_DELETE_SECONDS = 8

# Логіка попереджень/доган
WARNINGS_PER_REPRIMAND = 5
MAX_REPRIMANDS = 3

# Термін життя новин (год)
NEWS_TTL_HOURS = 24

# Інтенти
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "")

bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    intents=intents,
    help_command=None  # ← ДОБАВЬТЕ ЭТО!
)

# Менеджер даних
DM = DataManager(DATA_PATH, LOG_PATH)


# ===================== ХЕЛПЕРИ / ДЕКОРАТОРИ =====================

def is_admin():
    async def predicate(ctx: commands.Context):
        if ctx.author.guild_permissions.administrator:
            return True
        author_roles = {r.name for r in getattr(ctx.author, 'roles', [])}
        allowed = any(a in author_roles for a in ADMIN_ROLES)
        if not allowed:
            try:
                await ctx.message.delete(delay=1)
            except Exception:
                pass
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Відмовлено у доступі",
                    description=(
                        "У вас немає дозволу використовувати цю команду.\n"
                        f"Спробуйте звернутися до адміністрації."
                    ),
                    color=COLOR_ERROR,
                ),
                delete_after=AUTO_DELETE_SECONDS,
            )
        return allowed
    return commands.check(predicate)


def usage_error(usage: str) -> discord.Embed:
    return discord.Embed(
        title="⚠️ Неправильне використання",
        description=f"Використання: `{COMMAND_PREFIX}{usage}`\n{SEP}",
        color=COLOR_WARNING,
    )


async def auto_purge(ctx: commands.Context):
    try:
        await ctx.message.delete(delay=1)
    except Exception:
        pass


async def resolve_member_or_reply(ctx: commands.Context, nickname: str) -> Optional[discord.Member]:
    member = await find_member(ctx.guild, nickname)
    if not member:
        await ctx.send(
            embed=discord.Embed(
                title="❌ Користувача не знайдено",
                description=(
                    "Спробуйте варіанти: @Згадка, ID користувача, або точний нік/відображуване ім'я.\n"
                    f"Приклад: `{COMMAND_PREFIX}перевірити_учасника @User`, `{COMMAND_PREFIX}перевірити_учасника 1234567890`\n{SEP}"
                ),
                color=COLOR_ERROR,
            ),
            delete_after=AUTO_DELETE_SECONDS,
        )
    return member


def _(s: str) -> str:
    # Простий аліас для можливого майбутнього i18n
    return s


# ===================== ПОДІЇ =====================

@bot.event
async def on_ready():
    DM.set_start_time()
    print(f"Увійшов як {bot.user} (id: {bot.user.id})")
    cleanup_news_task.start()
    await bot.change_presence(activity=discord.Game(name="Horizont RP • Керування сервером"))


@bot.event
async def on_command_completion(ctx: commands.Context):
    # Підрахунок виконаних команд
    try:
        DM.increment_commands()
    except Exception:
        pass


# ===================== ПЛАНУВАЛЬНИКИ =====================

@tasks.loop(minutes=30)
async def cleanup_news_task():
    removed = DM.cleanup_news(older_than_minutes=NEWS_TTL_HOURS * 60)
    if removed:
        DM.log(f"Auto-cleanup removed {removed} old news entries")


# ===================== ПЕРЕВІРКИ РОЛЕЙ =====================

async def check_role_hierarchy(ctx: commands.Context, member: discord.Member) -> bool:
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send(
            embed=discord.Embed(
                title="❌ Проблема ієрархії ролей",
                description=(
                    "Моя роль повинна бути ВИЩЕ за ролі цільового учасника, щоб керувати його ролями.\n"
                    f"Перемістіть роль бота вище у налаштуваннях сервера.\n{SEP}"
                ),
                color=COLOR_ERROR,
            ),
            delete_after=AUTO_DELETE_SECONDS,
        )
        return False
    return True


# ===================== КОМАНДИ ОСНОВНИХ СИСТЕМ =====================

@bot.command(name="check_roles", aliases=["перевірити_ролі"]) 
@is_admin()
async def check_roles(ctx: commands.Context):
    await auto_purge(ctx)
    rm = RoleManager(ctx.guild, ROLE_IDS)
    ok = await rm.ensure_roles_exist()
    color = COLOR_SUCCESS if ok else COLOR_ERROR
    title = "✅ Перевірка ролей" if ok else "❌ Перевірка ролей"
    desc = "Усі налаштовані ролі знайдено." if ok else "Деякі з налаштованих ролей відсутні. Перевірте IDs."
    await ctx.send(embed=discord.Embed(title=title, description=f"{desc}\n{SEP}", color=color), delete_after=AUTO_DELETE_SECONDS)


# ---- Додавання керівника/заступника ----
async def add_person(ctx: commands.Context, category: str, nickname: str, організація: str, посада: str):
    await auto_purge(ctx)
    member = await resolve_member_or_reply(ctx, nickname)
    if not member:
        return
    if not await check_role_hierarchy(ctx, member):
        return

    rm = RoleManager(ctx.guild, ROLE_IDS)

    other_category = "deputies" if category == "leaders" else "leaders"
    # Перевірка дубля у своїй категорії (по відображуваному ніку)
    if DM.get_person(category, member.display_name):
        await ctx.send(embed=usage_error("додати_керівника [нік] [організація] [посада]" if category=="leaders" else "додати_заступника [нік] [організація] [посада]"), delete_after=AUTO_DELETE_SECONDS)
        return

    # Прибираємо роль протилежної категорії та покарання
    await rm.clear_punishment_roles(member)
    if other_category == "leaders":
        await rm.remove_role(member, ROLE_IDS.leader)
    else:
        await rm.remove_role(member, ROLE_IDS.deputy)

    # Призначення ролі
    if category == "leaders":
        await rm.set_leader(member)
    else:
        await rm.set_deputy(member)

    info = {
        # Локалізовані поля у JSON
        "організація": організація,
        "посада": посада,
        "appointment_date": now_str(),
        "appointed_by": str(ctx.author),
        "warnings": [],
        "reprimands": [],
        "activity": "Актив��ий",
        "last_activity": now_str(),
    }
    DM.set_person(category, member.display_name, info)
    DM.log(f"{ctx.author} додав(ла) {member} як {('керівника' if category=='leaders' else 'заступника')} у {організація} - {посада}")

    embed = discord.Embed(
        title="✅ Успішно",
        description=(
            f"Додано {member.mention} як {('Керівника' if category=='leaders' else 'Заступника')}\n"
            f"**Організація:** {організація}\n**Посада:** {посада}\n{SEP}"
        ),
        color=COLOR_SUCCESS,
    )
    await ctx.send(embed=embed, delete_after=AUTO_DELETE_SECONDS)


@bot.command(name="add_leader", aliases=["додати_керівника", "дк"]) 
@is_admin()
async def add_leader(ctx: commands.Context, nickname: str = None, організація: str = None, *, посада: str = None):
    if not (nickname and організація and посада):
        await ctx.send(embed=usage_error("додати_керівника [нік] [організація] [посада]"), delete_after=AUTO_DELETE_SECONDS)
        return
    await add_person(ctx, "leaders", nickname, організація, посада)


@bot.command(name="add_deputy", aliases=["додати_��аступника", "дз"]) 
@is_admin()
async def add_deputy(ctx: commands.Context, nickname: str = None, організація: str = None, *, посада: str = None):
    if not (nickname and організація and посада):
        await ctx.send(embed=usage_error("додати_заступника [нік] [організація] [посада]"), delete_after=AUTO_DELETE_SECONDS)
        return
    await add_person(ctx, "deputies", nickname, організація, посада)


# ---- Видалення керівника/заступника ----
async def remove_person(ctx: commands.Context, category: str, nickname: str):
    await auto_purge(ctx)
    member = await resolve_member_or_reply(ctx, nickname)
    if not member:
        return
    if not await check_role_hierarchy(ctx, member):
        return
    rm = RoleManager(ctx.guild, ROLE_IDS)

    ok = DM.remove_person(category, member.display_name)
    await rm.clear_punishment_roles(member)
    if category == "leaders":
        await rm.remove_role(member, ROLE_IDS.leader)
    else:
        await rm.remove_role(member, ROLE_IDS.deputy)

    if ok:
        DM.log(f"{ctx.author} видалив(ла) {member} із {('керівників' if category=='leaders' else 'заступників')}")
        await ctx.send(embed=discord.Embed(title="✅ В��далено", description=f"{member.mention} видалено та ролі очищено.\n{SEP}", color=COLOR_SUCCESS), delete_after=AUTO_DELETE_SECONDS)
    else:
        await ctx.send(embed=discord.Embed(title="⚠️ Не знайдено", description=f"{member.mention} не зареєстрований як {('керівник' if category=='leaders' else 'заступник')}.\n{SEP}", color=COLOR_WARNING), delete_after=AUTO_DELETE_SECONDS)


@bot.command(name="remove_leader", aliases=["видалити_керівника"]) 
@is_admin()
async def remove_leader(ctx: commands.Context, nickname: str = None):
    if not nickname:
        await ctx.send(embed=usage_error("видалити_керівника [нік]"), delete_after=AUTO_DELETE_SECONDS)
        return
    await remove_person(ctx, "leaders", nickname)


@bot.command(name="remove_deputy", aliases=["видалити_заступника"]) 
@is_admin()
async def remove_deputy(ctx: commands.Context, nickname: str = None):
    if not nickname:
        await ctx.send(embed=usage_error("видалити_заступника [нік]"), delete_after=AUTO_DELETE_SECONDS)
        return
    await remove_person(ctx, "deputies", nickname)


# ---- Списки та деталі ----

def get_org_from_info(info: dict) -> str:
    return info.get("організація") or info.get("organization") or "?"

def get_pos_from_info(info: dict) -> str:
    return info.get("посада") or info.get("position") or "?"


def group_by_org(category: str):
    data = DM.load()
    items = data.get(category, {})
    grouped = defaultdict(list)
    for nick, info in items.items():
        grouped[get_org_from_info(info)].append((nick, info))
    return grouped


@bot.command(name="leaders", aliases=["керівники"]) 
async def leaders(ctx: commands.Context):
    data = group_by_org("leaders")
    if not data:
        await ctx.send(embed=discord.Embed(title="ℹ️ Керівники", description=f"Немає керівників.\n{SEP}", color=COLOR_INFO), delete_after=AUTO_DELETE_SECONDS)
        return
    embed = discord.Embed(title="👑 Керівники", color=COLOR_INFO)
    for org, people in data.items():
        value = "\n".join([f"• {nick} — {get_pos_from_info(info)}" for nick, info in people])
        embed.add_field(name=f"🏢 {org}", value=value, inline=False)
    await ctx.send(embed=embed)


@bot.command(name="deputies", aliases=["заступники"]) 
async def deputies(ctx: commands.Context):
    data = group_by_org("deputies")
    if not data:
        await ctx.send(embed=discord.Embed(title="ℹ️ Заступники", description=f"Немає заступників.\n{SEP}", color=COLOR_INFO), delete_after=AUTO_DELETE_SECONDS)
        return
    embed = discord.Embed(title="🛡️ Заступники", color=COLOR_INFO)
    for org, people in data.items():
        value = "\n".join([f"• {nick} — {get_pos_from_info(info)}" for nick, info in people])
        embed.add_field(name=f"🏢 {org}", value=value, inline=False)
    await ctx.send(embed=embed)


def person_embed(nickname: str, info: dict, title: str) -> discord.Embed:
    embed = discord.Embed(title=title, color=COLOR_INFO)
    embed.description = f"👤 Користувач: **{nickname}**\n{SEP}"
    embed.add_field(name="🏢 Організація", value=get_org_from_info(info))
    embed.add_field(name="🧰 Посада", value=get_pos_from_info(info))
    embed.add_field(name="👤 Призначив", value=info.get("appointed_by", "-"), inline=False)
    embed.add_field(name="📅 Дата призначення", value=info.get("appointment_date", "-"), inline=False)
    embed.add_field(name="⚠️ Попереджень", value=str(len(info.get("warnings", []))))
    embed.add_field(name="🟧 Доган", value=str(len(info.get("reprimands", []))))
    embed.add_field(name="📈 Активність", value=info.get("activity", "-"), inline=False)
    embed.set_footer(text=f"Остання а��тивність: {info.get('last_activity', '-')} | Horizont RP")
    return embed


@bot.command(name="leader", aliases=["керівник"]) 
async def leader(ctx: commands.Context, *, nickname: str = None):
    if not nickname:
        await ctx.send(embed=usage_error("керівник [нік]"), delete_after=AUTO_DELETE_SECONDS)
        return
    # Пошук по двох варіантах ключа (з пропусками/підкресленнями)
    info = DM.get_person("leaders", nickname) or DM.get_person("leaders", nickname.replace(" ", "_"))
    if not info:
        await ctx.send(embed=discord.Embed(title="⚠️ Не знайдено", description=f"Керівника не знайдено.\n{SEP}", color=COLOR_WARNING), delete_after=AUTO_DELETE_SECONDS)
        return
    await ctx.send(embed=person_embed(nickname, info, "👑 Інформація про керівника"))


@bot.command(name="deputy", aliases=["заступник"]) 
async def deputy(ctx: commands.Context, *, nickname: str = None):
    if not nickname:
        await ctx.send(embed=usage_error("заступник [нік]"), delete_after=AUTO_DELETE_SECONDS)
        return
    info = DM.get_person("deputies", nickname) or DM.get_person("deputies", nickname.replace(" ", "_"))
    if not info:
        await ctx.send(embed=discord.Embed(title="⚠️ Не знайдено", description=f"Заступника не знайдено.\n{SEP}", color=COLOR_WARNING), delete_after=AUTO_DELETE_SECONDS)
        return
    await ctx.send(embed=person_embed(nickname, info, "🛡️ Інформація про заступника"))


# ===================== СИСТЕМА ПОКАРАНЬ =====================

def detect_category(nickname: str) -> Tuple[Optional[str], Optional[dict]]:
    data = DM.load()
    if nickname in data.get("leaders", {}):
        return "leaders", data["leaders"][nickname]
    if nickname in data.get("deputies", {}):
        return "deputies", data["deputies"][nickname]
    # Варіанти з підкресленнями/пробілами
    alt = nickname.replace(" ", "_")
    if alt in data.get("leaders", {}):
        return "leaders", data["leaders"][alt]
    if alt in data.get("deputies", {}):
        return "deputies", data["deputies"][alt]
    return None, None


@bot.command(name="warning", aliases=["попередження"]) 
@is_admin()
async def warning(ctx: commands.Context, nickname: str = None, *, reason: str = None):
    await auto_purge(ctx)
    if not (nickname and reason):
        await ctx.send(embed=usage_error("попередження [нік] [причина]"), delete_after=AUTO_DELETE_SECONDS)
        return

    category, info = detect_category(nickname)
    if not category:
        await ctx.send(embed=discord.Embed(title="⚠️ Не зареєстровано", description=f"Ціль не є керівником/заступником.\n{SEP}", color=COLOR_WARNING), delete_after=AUTO_DELETE_SECONDS)
        return

    count = DM.add_warning(category, nickname if info else nickname.replace(" ", "_"), reason, str(ctx.author))
    DM.log(f"{ctx.author} видав(ла) ПОПЕРЕДЖЕННЯ {nickname}: {reason} (разом {count})")

    embed = discord.Embed(title="⚠️ Попередження", description=f"{nickname} отримав(ла) попередження. Разом: **{count}**\n{SEP}", color=COLOR_WARNING)
    await ctx.send(embed=embed, delete_after=AUTO_DELETE_SECONDS)

    if count >= WARNINGS_PER_REPRIMAND:
        DM.clear_warnings(category, nickname if info else nickname.replace(" ", "_"))
        await reprimand_impl(ctx, nickname, reason=f"Авто-конвертація з {WARNINGS_PER_REPRIMAND} попереджень")


async def reprimand_impl(ctx: commands.Context, nickname: str, reason: str):
    category, info = detect_category(nickname)
    if not category:
        await ctx.send(embed=discord.Embed(title="⚠️ Не зареєстровано", description=f"Ціль не є керівником/заступником.\n{SEP}", color=COLOR_WARNING), delete_after=AUTO_DELETE_SECONDS)
        return
    # Отримати учасника
    member = await resolve_member_or_reply(ctx, nickname)
    if not member:
        return
    if not await check_role_hierarchy(ctx, member):
        return

    count = DM.add_reprimand(category, nickname if info else nickname.replace(" ", "_"), reason, str(ctx.author))
    rm = RoleManager(ctx.guild, ROLE_IDS)

    if count >= MAX_REPRIMANDS:
        # Звільнення
        await rm.clear_punishment_roles(member)
        if category == "leaders":
            await rm.remove_role(member, ROLE_IDS.leader)
        else:
            await rm.remove_role(member, ROLE_IDS.deputy)
        DM.remove_person(category, member.display_name)
        DM.log(f"{ctx.author} ЗВІЛЬНИВ(ЛА) {nickname} через 3 догани. Причина: {reason}")
        embed = discord.Embed(
            title="🟥 Звільнення",
            description=f"{nickname} звільнено через 3 догани.\n{SEP}",
            color=COLOR_DISMISSAL,
        )
        await ctx.send(embed=embed)
        return

    # Призначення ролей за прогресією
    await rm.apply_reprimand_role(member, count)
    DM.log(f"{ctx.author} видав(ла) ДОГАНУ №{count} {nickname}: {reason}")

    color = COLOR_REP_1 if count == 1 else COLOR_REP_2
    embed = discord.Embed(title=f"🟧 Догана №{count}", description=f"{nickname} отримав(ла) догану. Причина: _{reason}_\n{SEP}", color=color)
    await ctx.send(embed=embed, delete_after=AUTO_DELETE_SECONDS)


@bot.command(name="reprimand", aliases=["догана"]) 
@is_admin()
async def reprimand(ctx: commands.Context, nickname: str = None, *, reason: str = None):
    await auto_purge(ctx)
    if not (nickname and reason):
        await ctx.send(embed=usage_error("догана [нік] [причина]"), delete_after=AUTO_DELETE_SECONDS)
        return
    await reprimand_impl(ctx, nickname, reason)


# ===================== НОВИНИ (ВИПРАВЛЕННЯ КАНАЛУ) =====================

def parse_channel_arg(guild: discord.Guild, arg: str) -> Optional[discord.TextChannel]:
    # Підтримка згадок <#id>, числового ID та назв
    # Згадка каналу
    m = re.fullmatch(r"<#(\d+)>", arg.strip())
    if m:
        ch = guild.get_channel(int(m.group(1)))
        if isinstance(ch, discord.TextChannel):
            return ch
    # Числовий ID
    if arg.isdigit():
        ch = guild.get_channel(int(arg))
        if isinstance(ch, discord.TextChannel):
            return ch
    # Назва каналу
    # Пошук за назвою (без #, без регістру)
    name = arg.strip().lstrip('#').lower()
    for ch in guild.text_channels:
        if ch.name.lower() == name:
            return ch
    return None


def make_news_embed(author: discord.Member, channel: discord.TextChannel, text: str) -> discord.Embed:
    now = datetime.now().astimezone()
    embed = discord.Embed(color=COLOR_NEWS, timestamp=now)
    embed.title = "📢 **НОВИНИ СЕРВЕРА**"
    embed.description = (
        f"👤 Автор: {author.mention} | 🕒 {now.strftime('%d.%m.%Y %H:%M')}\n"
        f"{SEP}\n"
        f"📝 {text}\n"
        f"{SEP}\n"
        f"✅ Опубліковано адміністрацією\n"
        f"🗑️ Автоматичне видалення через 24 год"
    )
    embed.add_field(name="📺 Канал", value=f"#{channel.name}")
    embed.set_author(name=str(author), icon_url=getattr(author.display_avatar, 'url', discord.Embed.Empty))
    return embed


@bot.command(name="news", aliases=["новини"]) 
async def news(ctx: commands.Context, channel_arg: str = None, *, text: str = None):
    await auto_purge(ctx)
    if not (channel_arg and text):
        await ctx.send(embed=usage_error("новини [#канал|назва|ID] [текст]"), delete_after=AUTO_DELETE_SECONDS)
        return

    channel = parse_channel_arg(ctx.guild, channel_arg)
    if not channel:
        await ctx.send(
            embed=discord.Embed(
                title="❌ Канал не знайдено",
                description=(
                    "Вкажіть назву каналу, згадку або ID.\n"
                    f"Приклад: `{COMMAND_PREFIX}новини #general Текст` або `{COMMAND_PREFIX}новини general Текст`\n{SEP}"
                ),
                color=COLOR_ERROR,
            ),
            delete_after=AUTO_DELETE_SECONDS,
        )
        return

    # Перевірка прав: автор має мати право писати у цільовий канал
    perms = channel.permissions_for(ctx.author)
    if not perms.send_messages:
        await ctx.send(embed=discord.Embed(title="❌ Немає прав", description=f"У вас немає права писати у #{channel.name}.\n{SEP}", color=COLOR_ERROR), delete_after=AUTO_DELETE_SECONDS)
        return

    embed = make_news_embed(ctx.author, channel, text)
    try:
        msg = await channel.send(embed=embed)
    except discord.Forbidden:
        await ctx.send(embed=discord.Embed(title="❌ Помилка", description=f"Бот не може писати у #{channel.name}. Перевірте права.\n{SEP}", color=COLOR_ERROR), delete_after=AUTO_DELETE_SECONDS)
        return

    # Реакції
    for emoji in ["✅", "❌", "📌"]:
        try:
            await msg.add_reaction(emoji)
        except Exception:
            pass

    # Трекінг новин
    DM.add_news(text, str(ctx.author), channel.name, channel.id)
    DM.log(f"News published by {ctx.author} in #{channel.name}: {text[:60]}...")

    # План видалення через 24 години
    async def delete_later(m: discord.Message):
        try:
            await asyncio.sleep(NEWS_TTL_HOURS * 3600)
            await m.delete()
        except Exception:
            pass
    bot.loop.create_task(delete_later(msg))


@bot.command(name="news_list", aliases=["список_новин"]) 
async def news_list(ctx: commands.Context):
    data = DM.load()
    entries = data.get("news", [])[:10]
    if not entries:
        await ctx.send(embed=discord.Embed(title="ℹ️ Новини", description=f"Новин ще немає.\n{SEP}", color=COLOR_INFO), delete_after=AUTO_DELETE_SECONDS)
        return
    embed = discord.Embed(title="🟣 Останні 10 новин", color=COLOR_NEWS)
    for item in entries:
        text = item.get("text", "")
        author = item.get("author", "-")
        date = item.get("date", "-")
        channel = item.get("channel", "-")
        value = (text if len(text) <= 200 else text[:197] + "...")
        embed.add_field(name=f"{date} — #{channel}", value=value, inline=False)
    embed.set_footer(text="Використовуйте !новини для публікації")
    await ctx.send(embed=embed)


# ===================== КОРИСНІ КОМАНДИ =====================

@bot.command(name="clear", aliases=["очистити"]) 
@is_admin()
async def clear(ctx: commands.Context, amount: int = None):
    await auto_purge(ctx)
    if amount is None or amount < 1 or amount > 100:
        await ctx.send(embed=usage_error("очистити [кількість<=100]"), delete_after=AUTO_DELETE_SECONDS)
        return
    try:
        deleted = await ctx.channel.purge(limit=amount)
        await ctx.send(embed=discord.Embed(title="✅ Очищено", description=f"Видалено {len(deleted)} повідомлень.\n{SEP}", color=COLOR_SUCCESS), delete_after=AUTO_DELETE_SECONDS)
    except discord.Forbidden:
        await ctx.send(embed=discord.Embed(title="❌ Помилк�� доступу", description=f"Мені потрібен дозвіл 'Керувати повідомленнями'.\n{SEP}", color=COLOR_ERROR), delete_after=AUTO_DELETE_SECONDS)


@bot.command(name="check_member", aliases=["перевірити_учасника"]) 
@is_admin()
async def check_member(ctx: commands.Context, *, nickname: str = None):
    await auto_purge(ctx)
    if not nickname:
        await ctx.send(embed=usage_error("перевірити_учасника [нік]"), delete_after=AUTO_DELETE_SECONDS)
        return
    member = await resolve_member_or_reply(ctx, nickname)
    if not member:
        return
    roles = ", ".join([r.name for r in member.roles if r.name != "@everyone"]) or "Без ролей"
    embed = discord.Embed(title="ℹ️ Інформація про учасника", color=COLOR_INFO)
    embed.add_field(name="👤 Користувач", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="🏷️ Ролі", value=roles, inline=False)
    await ctx.send(embed=embed, delete_after=AUTO_DELETE_SECONDS)


@bot.command(name="stats", aliases=["статистика"]) 
async def stats(ctx: commands.Context):
    data = DM.load()
    leaders = data.get("leaders", {})
    deputies = data.get("deputies", {})
    rep_count = sum(len(v.get("reprimands", [])) for v in list(leaders.values()) + list(deputies.values()))
    warn_count = sum(len(v.get("warnings", [])) for v in list(leaders.values()) + list(deputies.values()))
    total_commands = data.get("settings", {}).get("total_commands", 0)
    embed = discord.Embed(title="📊 Статистика сервера", color=COLOR_INFO)
    embed.add_field(name="👑 Керівники", value=str(len(leaders)))
    embed.add_field(name="🛡️ Заступники", value=str(len(deputies)))
    embed.add_field(name="🟧 Догани", value=str(rep_count))
    embed.add_field(name="⚠️ Попередження", value=str(warn_count))
    embed.add_field(name="📈 Усього команд", value=str(total_commands))
    await ctx.send(embed=embed)


@bot.command(name="info", aliases=["інфо"]) 
async def info(ctx: commands.Context):
    embed = discord.Embed(title="ℹ️ Horizont RP", description="Бот керування сервером.", color=COLOR_INFO)
    embed.add_field(name="Префікс", value=COMMAND_PREFIX)
    embed.add_field(name="TTL новин", value=f"{NEWS_TTL_HOURS} год")
    embed.set_footer(text="Створено для Horizont RP")
    await ctx.send(embed=embed)


@bot.command(name="help", aliases=["допомога"]) 
async def help_cmd(ctx: commands.Context):
    embed = discord.Embed(title="🧭 Допомога", color=COLOR_INFO)
    embed.add_field(name="🎯 Керівництво", value="\n".join([
        "`!додати_керівника [нік] [орг] [посада]` (аліас: `!дк`)",
        "`!керівники` — список всіх",
        "`!керівник [нік]` — детальна інформація",
        "`!додати_заступника [нік] [орг] [посада]` (аліас: `!дз`)",
        "`!заступники` — список всіх",
        "`!заступник [нік]` — детальна інформація",
        "`!видалити_керівника [нік]` / `!видалити_заступника [нік]`",
    ]), inline=False)
    embed.add_field(name="⚠️ Покарання", value="\n".join([
        "`!попередження [нік] [причина]` — запис у базі (без ролей)",
        f"Після {WARNINGS_PER_REPRIMAND} попереджень — автоматична `!догана`",
        "`!догана [нік] [причина]` — прогресія ролей (1→🟡, 2→🟠, 3→звільнення)",
    ]), inline=False)
    embed.add_field(name="🟣 Новини", value="\n".join([
        "`!новини [#канал|назва|ID] [текст]` — публікація новини",
        "`!список_новин` — останні 10 новин",
    ]), inline=False)
    embed.add_field(name="🛠️ Утиліти", value="\n".join([
        "`!очистити [кількість]` — видалити повідомлення (≤100)",
        "`!перевірити_ролі` — перевірка наявності ролей",
        "`!перевірити_учасника [нік]` — докладна інформація",
        "`!статистика`, `!інфо`",
    ]), inline=False)
    embed.set_footer(text="Усі команди мають англійські аналоги для сумісності.")
    await ctx.send(embed=embed)


# ===================== ОБРОБКА ПОМИЛОК =====================

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    try:
        DM.increment_commands()
    except Exception:
        pass
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=discord.Embed(title="❌ Немає прав", description=f"У вас недостатньо прав.\n{SEP}", color=COLOR_ERROR), delete_after=AUTO_DELETE_SECONDS)
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=discord.Embed(title="⚠️ Відсутні аргументи", description=f"{error}\n{SEP}", color=COLOR_WARNING), delete_after=AUTO_DELETE_SECONDS)
        return
    if isinstance(error, commands.CommandNotFound):
        # Ігноруємо невідомі команди
        return
    DM.log(f"Error: {type(error).__name__}: {error}")
    await ctx.send(embed=discord.Embed(title="❌ Помилка", description=f"Сталася помилка. Перевірте логи.\n{SEP}", color=COLOR_ERROR), delete_after=AUTO_DELETE_SECONDS)


# ===================== ВХІДНА ТОЧКА =====================

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN не встановлено у .env")
    bot.run(TOKEN)
