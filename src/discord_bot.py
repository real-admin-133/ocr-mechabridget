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
from tip_recognizer import Tip, TipRecognizer
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

   def __init__(self, bot: disc_commands.Bot, log: logging.Logger, allowed_channels: list[str],
                mention_roles: list[str], reaction_emoji: int, err_reaction_emoji: int,
                history_messages_limit: int, failed_urls_per_page: int) -> None:
      self.bot = bot
      self._log = log
      self._allowed_channels = allowed_channels
      self._mention_roles = mention_roles
      self._reaction_emoji = reaction_emoji
      self._err_reaction_emoji = err_reaction_emoji
      self._cached_reaction_emoji = None
      self._cached_err_reaction_emoji = None
      self._history_messages_limit = history_messages_limit
      self._failed_urls_per_page = failed_urls_per_page
      self._failed_urls = simple_saver.load_key(
         self.FAILED_URLS_SAVE_KEY, {channel: [] for channel in allowed_channels})
      self._tip_recognizer = TipRecognizer()
      self._sheet_updater = StonkSheetUpdater()

   @disc_commands.command()
   async def fails(self, ctx: disc_commands.Context) -> None:
      if not self._should_respond_to_command(ctx):
         return
      channel_name = ctx.channel.name
      content = FailedURLsPages(self._failed_urls[channel_name], self._failed_urls_per_page)
      self._failed_urls[channel_name].clear()
      simple_saver.save_key(self.FAILED_URLS_SAVE_KEY, self._failed_urls)
      await PageNavigator(ctx, content.get_pages(), timeout=1800).run()

   @disc_commands.Cog.listener()
   async def on_ready(self) -> None:
      for guild in self.bot.guilds:
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
      # Add new tips to stonk sheet.
      for tip in tips:
         self._sheet_updater.update_sheet(tip)
      # Add new failed tip images to the channel's pile.
      if failed_urls:
         self._failed_urls[message.channel.name].extend(failed_urls)
         simple_saver.save_key(self.FAILED_URLS_SAVE_KEY, self._failed_urls)
      # Post reply and react to message.
      embed = self._get_embed_for_reply(tips, failed_urls, message.guild)
      emoji = self._get_err_reaction_emoji() if failed_urls else self._get_reaction_emoji()
      await message.reply(embed=embed)
      await message.add_reaction(emoji)

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


class DiscordBot(object):
   CONFIG_SECTION = 'discord-bot'

   def __init__(self) -> None:
      self._setup_logging()
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
      tip_posting_channels = BasicUtils.get_list_from_csv(config.get(self.CONFIG_SECTION, 'tip_posting_channels'))
      tip_mention_roles = BasicUtils.get_list_from_csv(config.get(self.CONFIG_SECTION, 'failed_tip_mention_roles'))
      tip_reaction_emoji = config.getint(self.CONFIG_SECTION, 'tip_reaction_emoji')
      tip_err_reaction_emoji = config.getint(self.CONFIG_SECTION, 'tip_err_reaction_emoji')
      history_messages_limit = config.getint(self.CONFIG_SECTION, 'history_messages_limit')
      failed_urls_per_page = config.getint(self.CONFIG_SECTION, 'failed_urls_per_page')
      await self._bot.add_cog(TipProcessingCog(
         self._bot, self._log, tip_posting_channels, tip_mention_roles, tip_reaction_emoji, tip_err_reaction_emoji,
         history_messages_limit, failed_urls_per_page))
