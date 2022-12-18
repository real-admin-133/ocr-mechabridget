import abc
from typing import Optional

import discord
from discord.ext import commands as disc_commands


class Page(object):
   def __init__(self, content: Optional[str] = None,
                embed: Optional[discord.Embed] = None) -> None:
      self.content = content
      self.embed = embed


class PageGenerator(abc.ABC):
   @abc.abstractmethod
   def get_pages(self) -> list[Page]:
      return []


class PageNavigator(discord.ui.View):
   NAV_BTN_STYLE = discord.ButtonStyle.gray

   NAV_BTN_NEXT_PAGE_INAME = 'next-page'
   NAV_BTN_NEXT_PAGE_EMOJI = '▶️'

   NAV_BTN_PREV_PAGE_INAME = 'prev-page'
   NAV_BTN_PREV_PAGE_EMOJI = '◀️'

   NAV_BTN_FIRST_PAGE_INAME = 'first-page'
   NAV_BTN_FIRST_PAGE_EMOJI = '⏮️'

   NAV_BTN_LAST_PAGE_INAME = 'last-page'
   NAV_BTN_LAST_PAGE_EMOJI = '⏭️'

   def __init__(self, ctx: disc_commands.Context, pages: list[Page], timeout: Optional[float] = None) -> None:
      super().__init__(timeout=timeout)
      self._ctx = ctx
      self._pages = pages
      self._nav_btns = {}
      self._curr_page = 0
      self._max_page = len(self._pages) - 1
      self._setup_nav_btns()

   def _setup_nav_btns(self) -> None:
      self._register_nav_btn(self.NAV_BTN_FIRST_PAGE_INAME, self._onclick_first_page,
         self.NAV_BTN_FIRST_PAGE_EMOJI)
      self._register_nav_btn(self.NAV_BTN_PREV_PAGE_INAME, self._onclick_prev_page,
         self.NAV_BTN_PREV_PAGE_EMOJI)
      self._register_nav_btn(self.NAV_BTN_NEXT_PAGE_INAME, self._onclick_next_page,
         self.NAV_BTN_NEXT_PAGE_EMOJI)
      self._register_nav_btn(self.NAV_BTN_LAST_PAGE_INAME, self._onclick_last_page,
         self.NAV_BTN_LAST_PAGE_EMOJI)

   def _register_nav_btn(self, intra_name: str, callback, emoji: str, disabled: bool = False) -> None:
      nav_btn = discord.ui.Button(
         style=self.NAV_BTN_STYLE, emoji=emoji, disabled=disabled)
      nav_btn.callback = callback
      self._nav_btns[intra_name] = nav_btn
      self.add_item(nav_btn)

   async def _onclick_next_page(self, interaction: discord.Interaction) -> None:
      self._curr_page = min(self._curr_page + 1, self._max_page)
      await self._update_message(interaction)

   async def _onclick_prev_page(self, interaction: discord.Interaction) -> None:
      self._curr_page = max(self._curr_page - 1, 0)
      await self._update_message(interaction)

   async def _onclick_first_page(self, interaction: discord.Interaction) -> None:
      self._curr_page = 0
      await self._update_message(interaction)

   async def _onclick_last_page(self, interaction: discord.Interaction) -> None:
      self._curr_page = self._max_page
      await self._update_message(interaction)

   async def run(self) -> None:
      page = self._pages[self._curr_page]
      self._update_nav_btns_state()
      await self._ctx.channel.send(content=page.content, embed=page.embed, view=self)

   async def _update_message(self, interaction: discord.Interaction) -> None:
      page = self._pages[self._curr_page]
      self._update_nav_btns_state()
      await interaction.message.edit(content=page.content, embed=page.embed, view=self)
      await interaction.response.defer()

   def _update_nav_btns_state(self) -> None:
      self._nav_btns[self.NAV_BTN_FIRST_PAGE_INAME].disabled = self._is_at_first_page()
      self._nav_btns[self.NAV_BTN_PREV_PAGE_INAME].disabled = self._is_at_first_page()
      self._nav_btns[self.NAV_BTN_NEXT_PAGE_INAME].disabled = self._is_at_last_page()
      self._nav_btns[self.NAV_BTN_LAST_PAGE_INAME].disabled = self._is_at_last_page()

   def _is_at_first_page(self) -> bool:
      return self._curr_page == 0

   def _is_at_last_page(self) -> bool:
      return self._curr_page == self._max_page

   async def interaction_check(self, interaction: discord.Interaction) -> bool:
      # Allow only the user which invoked the command to be able to use the interaction.
      return interaction.user == self._ctx.author
