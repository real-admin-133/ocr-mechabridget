import asyncio
import requests
import logging
from typing import Optional, Union

import numpy
import cv2
import discord
from discord.ext import commands as disc_commands

from config_loader import config
from logging_utils import logger_factory
from simple_data_saver import simple_saver
from basic_utils import BasicUtils
from shared_constants import HeroTown
from tip_recognizer import Tip, TipRecognizer
from stonk_sheet_querier import StonkSheetQuerier
from stonk_sheet_updater import StonkSheetUpdater
from discord_paginator import Page, PageGenerator, PageNavigator


class FailedURLsPages(PageGenerator):
   EMBED_COLOR = discord.Color.red()

   def __init__(self, failed_urls: list[str], urls_per_page: int) -> None:
      super().__init__()
      # Make a copy since original list will be cleared afterward.
      self._failed_urls = [url for url in failed_urls]
      self._urls_per_page = urls_per_page
      self._pages = []
      self._make_pages()

   def get_pages(self) -> list[Page]:
      return self._pages

   def _make_pages(self) -> None:
      if self._failed_urls:
         self._pages = self._make_failed_urls_pages()
      else:
         self._pages = [self._make_default_page()]

   def _make_failed_urls_pages(self) -> list[Page]:
      pages = []
      failed_urls_for_pages = BasicUtils.split_list_to_chunks(
         self._failed_urls, self._urls_per_page)
      page_count = len(failed_urls_for_pages)
      for idx, urls in enumerate(failed_urls_for_pages):
         page_number = idx + 1
         embed_content = '\n'.join(['<{}>'.format(url) for url in urls])
         embed = discord.Embed(description=embed_content, color=self.EMBED_COLOR)
         embed.set_footer(text='Displayed {} in {} URLs. Page {}/{}'.format(
            len(urls), len(self._failed_urls), page_number, page_count))
         pages.append(Page(embed=embed))
      return pages

   def _make_default_page(self) -> Page:
      embed = discord.Embed(description='No new failed image so far.', color=self.EMBED_COLOR)
      embed.set_footer(text='Page 1/1')
      return Page(embed=embed)


class TipProcessingCog(disc_commands.Cog):
   FAILED_URLS_SAVE_KEY = 'failed-urls'
   DEFAULT_REACTION_EMOJI = '✅'
   DEFAULT_ERR_REACTION_EMOJI = '❌'
   EMBED_COLOR = discord.Color.blue()

   def __init__(self, bot: disc_commands.Bot, log: logging.Logger, prod_mode: bool,
                prod_privileged_guilds: list[int], allowed_channels: list[str],
                should_mention_roles: bool, mention_roles: list[str], reaction_emoji: int,
                err_reaction_emoji: int, mention_author: bool, history_messages_limit: int,
                failed_urls_per_page: int) -> None:
      self.bot = bot
      self._log = log
      self._prod_mode = prod_mode
      self._prod_privileged_guilds = prod_privileged_guilds
      self._allowed_channels = allowed_channels
      self._should_mention_roles = should_mention_roles
      self._mention_roles = mention_roles
      self._reaction_emoji = reaction_emoji
      self._err_reaction_emoji = err_reaction_emoji
      self._cached_reaction_emoji = None
      self._cached_err_reaction_emoji = None
      self._mention_author = mention_author
      self._history_messages_limit = history_messages_limit
      self._failed_urls_per_page = failed_urls_per_page
      self._failed_urls = simple_saver.load_key(
         self.FAILED_URLS_SAVE_KEY, {})
      self._tip_recognizer = TipRecognizer()
      self._sheet_updater = StonkSheetUpdater()

   @disc_commands.command()
   async def fails(self, ctx: disc_commands.Context) -> None:
      if not self._should_respond_to_command(ctx):
         return
      channel_name = ctx.channel.name
      guild_id = ctx.guild.id
      content = FailedURLsPages(self._failed_urls[guild_id][channel_name], self._failed_urls_per_page)
      self._failed_urls[guild_id][channel_name].clear()
      simple_saver.save_key(self.FAILED_URLS_SAVE_KEY, self._failed_urls)
      await PageNavigator(ctx, content.get_pages(), timeout=1800).run()

   @disc_commands.Cog.listener()
   async def on_ready(self) -> None:
      for guild in self.bot.guilds:
         if guild.id not in self._failed_urls:
            self._failed_urls[guild.id] = {channel: [] for channel in self._allowed_channels}
         for channel in guild.text_channels:
            if channel.name in self._allowed_channels:
               async for message in channel.history(limit=self._history_messages_limit):
                  await self._process_message(message)
         for thread in guild.threads:
            if thread.name in self._allowed_channels:
               async for message in thread.history(limit=self._history_messages_limit):
                  await self._process_message(message)

   @disc_commands.Cog.listener()
   async def on_message(self, message: discord.Message) -> None:
      await self._process_message(message)

   async def _process_message(self, message: discord.Message) -> None:
      if not self._should_respond_to_message(message):
         return
      self._log.info('Processing message, id={}, channel="{}", user="{}"'.format(
         message.id, message.channel.name, message.author.name))
      tips, failed_urls = self._process_attachments(message.attachments)
      if (len(tips) + len(failed_urls)) == 0:
         # Nothing to do.
         return
      # (Sensitive) Add new tips to stonk sheet.
      if self._should_perform_sensitive_actions(message.guild):
         for tip in tips:
            self._sheet_updater.update_sheet(tip)
      # Add new failed tip images to the channel's pile.
      if failed_urls:
         self._failed_urls[message.guild.id][message.channel.name].extend(failed_urls)
         simple_saver.save_key(self.FAILED_URLS_SAVE_KEY, self._failed_urls)
      # Post reply and react to message.
      embed = self._get_embed_for_reply(tips, failed_urls, message.guild)
      emoji = self._get_err_reaction_emoji() if failed_urls else self._get_reaction_emoji()
      await message.reply(embed=embed, mention_author=self._mention_author)
      await message.add_reaction(emoji)

   def _should_perform_sensitive_actions(self, guild: discord.Guild) -> bool:
      return (not self._prod_mode) or (guild.id in self._prod_privileged_guilds)

   def _should_respond_to_command(self, ctx: disc_commands.Context) -> bool:
      if ctx.channel.name not in self._allowed_channels:
         # Ignore commands invoked from outside the allowed (tip-posting) channels.
         return False
      if not any(role.name in self._mention_roles for role in ctx.author.roles):
         # Ignore commands from members without the mention-roles.
         return False
      return True

   def _should_respond_to_message(self, message: discord.Message) -> bool:
      if message.author == self.bot.user:
         # Ignore messages sent by this bot.
         return False
      if message.channel.name not in self._allowed_channels:
         # Ignore messages not from list of allowed (tip-posting) channels.
         return False
      if not message.attachments:
         # Ignore messages without any attachment.
         return False
      for reaction in message.reactions:
         if reaction.me:
            # Ignore messages this bot has reacted to.
            return False
      return True

   def _process_attachments(self, attachments: list[discord.Attachment]) -> tuple[list[Tip], list[str]]:
      tips = []
      failed_urls = []
      for attachment in attachments:
         if not self._is_attached_image(attachment):
            # Skip non-image attachments.
            continue
         image_url = attachment.url
         image = self._load_attached_image(image_url)
         if image is None:
            failed_urls.append(image_url)
            continue
         success, tip = self._tip_recognizer.process_tip(image)
         if success:
            tip.url = image_url
            tips.append(tip)
         else:
            failed_urls.append(image_url)
      return tips, failed_urls

   def _is_attached_image(self, attachment: discord.Attachment) -> bool:
      return attachment.content_type and attachment.content_type.startswith('image/')

   def _load_attached_image(self, url: str) -> Optional[numpy.ndarray]:
      try:
         response = requests.get(url, stream=True).raw
         image_array = numpy.asarray(bytearray(response.read()), dtype='uint8')
         return cv2.imdecode(image_array, cv2.IMREAD_COLOR)
      except Exception as e:
         self._log.error(
            'Unknown error occurred while fetching image, url="{}", exception="{}"'.format(url, repr(e)))
         return None

   def _get_embed_for_reply(self, tips: list[Tip], failed_urls: list[str], guild: discord.Guild) -> discord.Embed:
      embed = discord.Embed(color=self.EMBED_COLOR)
      if tips:
         lines = [tip.to_string() for tip in tips]
         embed.add_field(name='SUCCESS', value='\n'.join(lines), inline=False)
      if failed_urls:
         lines = ['Cannot read <{}>'.format(url) for url in failed_urls]
         lines.append('')  # Separation line.
         if self._should_mention_roles:
            lines.append(''.join([role.mention for role in self._get_mention_roles(guild)]))
         embed.add_field(name='FAILED', value='\n'.join(lines), inline=False)
      return embed

   def _get_mention_roles(self, guild: discord.Guild) -> list[discord.Role]:
      roles = []
      for rolename in self._mention_roles:
         maybe_role = discord.utils.get(guild.roles, name=rolename)
         if maybe_role:
            roles.append(maybe_role)
      return roles

   def _get_reaction_emoji(self) -> Union[discord.Emoji, str]:
      if not self._cached_reaction_emoji:
         maybe_emoji = discord.utils.get(self.bot.emojis, id=self._reaction_emoji)
         self._cached_reaction_emoji = maybe_emoji or self.DEFAULT_REACTION_EMOJI
      return self._cached_reaction_emoji

   def _get_err_reaction_emoji(self) -> Union[discord.Emoji, str]:
      if not self._cached_err_reaction_emoji:
         maybe_emoji = discord.utils.get(self.bot.emojis, id=self._err_reaction_emoji)
         self._cached_err_reaction_emoji = maybe_emoji or self.DEFAULT_ERR_REACTION_EMOJI
      return self._cached_err_reaction_emoji


class SheetHelperCog(disc_commands.Cog):
   EMBED_COLOR = discord.Color.dark_gray()

   def __init__(self, bot: disc_commands.Bot, log: logging.Logger,
                allowed_channels: list[str], mention_author: bool) -> None:
      self.bot = bot
      self._log = log
      self._allowed_channels = allowed_channels
      self._mention_author = mention_author
      self._sheet_querier = StonkSheetQuerier()

   @disc_commands.command()
   async def sheet(self, ctx: disc_commands.Context) -> None:
      if not self._should_respond_to_command(ctx):
         return
      await self._respond_to_command(ctx, self._sheet_querier.get_sheet_msg())

   @disc_commands.command()
   async def round(self, ctx: disc_commands.Context) -> None:
      if not self._should_respond_to_command(ctx):
         return
      await self._respond_to_command(ctx, self._sheet_querier.get_current_turn_msg())

   @disc_commands.command(aliases=['bb'])
   async def bestbuy(self, ctx: disc_commands.Context) -> None:
      if not self._should_respond_to_command(ctx):
         return
      await self._respond_to_command(ctx, self._sheet_querier.get_best_buy_msg())

   @disc_commands.command(aliases=['tb', 'check'])
   async def targetbuy(self, ctx: disc_commands.Context, *args) -> None:
      if not self._should_respond_to_command(ctx):
         return
      if len(args) == 0:
         error_msg = 'Command requires at least 1 argument. Accept positive numbers only.'
         await self._respond_to_command(ctx, error_msg)
         return

      target_turns = []
      invalid_args = []
      for arg in args:
         try:
            target_turn = int(arg)
            if target_turn > 0:
               target_turns.append(target_turn)
            else:
               invalid_args.append(arg)
         except ValueError:
            invalid_args.append(arg)

      contents = []
      if invalid_args:
         contents.append('Invalid argument(s): {}. Accept positive numbers only.'.format(
            ', '.join(invalid_args)))
      if target_turns:
         contents.append(self._sheet_querier.get_target_buy_msg(target_turns))
      await self._respond_to_command(ctx, '\n'.join(contents))

   @disc_commands.command()
   async def tips(self, ctx: disc_commands.Context, *args) -> None:
      if not self._should_respond_to_command(ctx):
         return

      special_accepts = ['all']
      option_accepts_dict = {e.value.lower(): e for e in HeroTown
                             if e is not HeroTown.UNKNOWN}
      option_accepts = list(option_accepts_dict.keys())
      accepts = special_accepts + option_accepts
      if len(args) == 0:
         error_msg = 'Command requires at least 1 argument. Accept: {}.'.format(
            ', '.join(accepts))
         await self._respond_to_command(ctx, error_msg)
         return

      if 'all' in args:
         unique_args = option_accepts
      else:
         unique_args = list(set(args))
      stocks = []
      invalid_args = []
      for arg in unique_args:
         if arg in option_accepts_dict:
            stocks.append(option_accepts_dict[arg])
         else:
            invalid_args.append(arg)

      contents = []
      if invalid_args:
         contents.append('Invalid argument(s): {}. Accept: {}.'.format(
            ', '.join(invalid_args),
            ', '.join(accepts)))
      if stocks:
         contents.append(self._sheet_querier.get_tips_msg(stocks))
      await self._respond_to_command(ctx, '\n'.join(contents))

   async def _respond_to_command(self, ctx: disc_commands.Context, content: str) -> None:
      embed = discord.Embed(color=self.EMBED_COLOR)
      embed.add_field(name='', value=content, inline=False)
      await ctx.message.reply(embed=embed, mention_author=self._mention_author)

   def _should_respond_to_command(self, ctx: disc_commands.Context) -> bool:
      if ctx.channel.name not in self._allowed_channels:
         # Ignore commands invoked from outside the allowed (tip-querying) channels.
         return False
      return True


class DiscordBot(object):
   CONFIG_SECTION = 'discord-bot'

   def __init__(self) -> None:
      self._setup_logging()
      self._prod_mode = config.getboolean(self.CONFIG_SECTION, 'prod_mode')
      asyncio.get_event_loop().run_until_complete(self._setup_discord_bot())

   def run(self) -> None:
      self._bot.run(self._auth_token,
         log_handler=logger_factory.handler,
         log_formatter=logger_factory.formatter,
         log_level=logging.INFO)

   def _setup_logging(self) -> None:
      self._log = logger_factory.get_logger('discord-bot')
      self._log.setLevel(logging.INFO)

   async def _setup_discord_bot(self) -> None:
      self._auth_token = config.get(self.CONFIG_SECTION, 'auth_token')
      # Bot needs to have "message content" intent enabled.
      intents = discord.Intents.default()
      intents.message_content = True
      self._bot = disc_commands.Bot(
         command_prefix=config.get(self.CONFIG_SECTION, 'command_prefix'),
         intents=intents)
      # Setup TipProcessingCog.
      prod_privileged_guilds = BasicUtils.get_int_list_from_csv(
         config.get(self.CONFIG_SECTION, 'prod_privileged_guilds'))
      tip_posting_channels = BasicUtils.get_list_from_csv(config.get(self.CONFIG_SECTION, 'tip_posting_channels'))
      should_mention_roles = config.getboolean(self.CONFIG_SECTION, 'should_mention_roles')
      tip_mention_roles = BasicUtils.get_list_from_csv(config.get(self.CONFIG_SECTION, 'failed_tip_mention_roles'))
      tip_reaction_emoji = config.getint(self.CONFIG_SECTION, 'tip_reaction_emoji')
      tip_err_reaction_emoji = config.getint(self.CONFIG_SECTION, 'tip_err_reaction_emoji')
      mention_author = config.getboolean(self.CONFIG_SECTION, 'mention_author')
      history_messages_limit = config.getint(self.CONFIG_SECTION, 'history_messages_limit')
      failed_urls_per_page = config.getint(self.CONFIG_SECTION, 'failed_urls_per_page')
      await self._bot.add_cog(TipProcessingCog(
         self._bot, self._log, self._prod_mode, prod_privileged_guilds, tip_posting_channels,
         should_mention_roles, tip_mention_roles, tip_reaction_emoji, tip_err_reaction_emoji,
         mention_author, history_messages_limit, failed_urls_per_page))
      # Setup SheetHelperCog.
      tip_querying_channels = BasicUtils.get_list_from_csv(config.get(self.CONFIG_SECTION, 'tip_querying_channels'))
      await self._bot.add_cog(SheetHelperCog(
         self._bot, self._log, tip_querying_channels, mention_author))
