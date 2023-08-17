import time
import logging
from typing import Optional

from basic_utils import BasicUtils
from config_loader import config
from logging_utils import logger_factory
from shared_constants import HeroTown
from stonk_sheet_base import StonkSheetBase


class StonkSheetQuerier(StonkSheetBase):
   CONFIG_SECTION = 'stonk-sheet-querier'

   def __init__(self) -> None:
      self._setup_logging()
      self._setup_stonk_sheet()
      self._starting_time = config.getint(self.CONFIG_SECTION, 'starting_time')
      self._cache_fresh_time = config.getint(self.CONFIG_SECTION, 'cache_fresh_time')
      self._cached_data = None
      self._cached_time = 0

   def get_best_buy_msg(self) -> str:
      current_turn = self._get_current_turn()
      lines = [self.get_current_turn_msg()]
      if current_turn == self._max_turn:
         return lines[0]

      excludes, _, includes_data = self._get_only_usable_data()
      # If missing current turn's price for at least 1 stock.
      if excludes:
         lines.append(self._get_missing_current_price_msg(excludes))
      # Get stock with highest increase in next round.
      target_turn = current_turn + 1
      best_change_name, best_change_percent = self._get_best_change_for_turn(
         includes_data, target_turn)
      if best_change_name is not None:
         lines.append('{} will have the highest growth of {} next round.'.format(
            best_change_name, str(best_change_percent) + r'%'))
      else:
         lines.append('No good stock to buy this round. Consider holding.')

      return '\n'.join(lines)

   def get_target_buy_msg(self, target_turns: list[int]) -> str:
      current_turn = self._get_current_turn()
      lines = [self.get_current_turn_msg()]
      if current_turn == self._max_turn:
         return lines[0]
      
      excludes, _, includes_data = self._get_only_usable_data()
      # If missing current turn's price for at least 1 stock.
      if excludes:
         lines.append(self._get_missing_current_price_msg(excludes))
      for target_turn in target_turns:
         target_turn = min(current_turn + target_turn, self._max_turn)
         turn_diff = target_turn - current_turn
         # Get stock with highest increase in N rounds.
         best_change_name, best_change_percent = self._get_best_change_for_turn(
            includes_data, target_turn)
         if best_change_name is not None:
            lines.append('{} will have the highest growth of {} in {} round(s).'.format(
               best_change_name, str(best_change_percent) + r'%', turn_diff))
         else:
            lines.append('No good stock to hold for {} round(s).'.format(turn_diff))

      return '\n'.join(lines)

   def get_tips_msg(self, stocks: list[HeroTown]) -> str:
      current_turn = self._get_current_turn()
      lines = [self.get_current_turn_msg()]
      if current_turn == self._max_turn:
         return lines[0]

      excludes, _, includes_data = self._get_only_usable_data()
      if excludes:
         lines.append(self._get_missing_current_price_msg(excludes))
      next_turn = current_turn + 1
      next_turn_idx = self._get_idx_for_turn(next_turn)
      for stock in stocks:
         if stock.value in includes_data:
            prices = includes_data[stock.value]
            next_price = None
            # Get first available price after current turn.
            for idx, price in enumerate(prices[next_turn_idx:]):
               if price is not None:
                  next_price = price
                  break
            if next_price is not None:
               current_price = prices[self._get_idx_for_turn(current_turn)]
               change_percent = self._get_change_percent(
                  current_price, next_price)
               lines.append('{} will be {} on round {}. A change of {}.'.format(
                  stock.value, next_price, next_turn + idx,
                  str(change_percent) + r'%'))
            else:
               lines.append('No tip available for {}.'.format(stock.value))

      return '\n'.join(lines)

   def get_sheet_msg(self) -> str:
      spreadsheet_id = config.get(StonkSheetBase.CONFIG_SECTION, 'spreadsheet_id')
      return 'https://docs.google.com/spreadsheets/d/{}/#gid={}'.format(
         spreadsheet_id, self._sheet.id)

   def get_current_turn_msg(self) -> str:
      current_turn = self._get_current_turn()
      lines = ['The current round is {}.'.format(current_turn)]
      if current_turn == self._max_turn:
         lines.append('Event has ended. Thanks for playing.')
      return '\n'.join(lines)

   def _get_missing_current_price_msg(self, excludes: list[str]) -> str:
      return '\n'.join([
         'No current price for {}.'.format(', '.join(excludes)),
         'Please contact an available editor and request them to update.'
      ])

   def _get_best_change_for_turn(
         self, data: dict[str, list[Optional[int]]],
         target_turn: int) -> tuple[Optional[str], float]:
      current_turn = self._get_current_turn()
      best_change_name = None
      best_change_percent = 0
      for hero_town_name, hero_town_data in data.items():
         current_turn_price = hero_town_data[self._get_idx_for_turn(current_turn)]
         target_turn_price = hero_town_data[self._get_idx_for_turn(target_turn)]
         if (current_turn_price is None) or (target_turn_price is None):
            continue
         change_percent = self._get_change_percent(current_turn_price,
                                                   target_turn_price)
         if change_percent > best_change_percent:
            best_change_name = hero_town_name
            best_change_percent = change_percent
      return (best_change_name, best_change_percent)

   def _get_only_usable_data(self) -> tuple[list[str], list[str],
                                            dict[str, list[Optional[int]]]]:
      current_turn = self._get_current_turn()
      data = self._get_data()
      excludes = []
      includes = []
      for hero_town_name, hero_town_data in data.items():
         if hero_town_data[self._get_idx_for_turn(current_turn)] is None:
            excludes.append(hero_town_name)
         else:
            includes.append(hero_town_name)
      includes_data = {k: data[k] for k in includes}
      return (excludes, includes, includes_data)

   def _get_data(self) -> dict[str, list[Optional[int]]]:
      if not self._should_use_cache():
         self._fetch_new_data()
      return self._cached_data

   def _fetch_new_data(self) -> None:
      cell_ranges = []
      hero_town_names = []
      for hero_town_name, col in self.PRICE_COLUMNS.items():
         start_cell = self._get_turn_acell(col, 1)
         end_cell = self._get_turn_acell(col, self._max_turn)
         cell_range = '{}:{}'.format(start_cell, end_cell)
         cell_ranges.append(cell_range)
         hero_town_names.append(hero_town_name)
      raw_data_all = self._sheet.batch_get(cell_ranges)

      self._cached_data = {}
      for hero_town_name, raw_data in zip(hero_town_names, raw_data_all):
         processed_data = [None] * self._max_turn
         for idx, entry in enumerate(raw_data):
            if entry:
               try:
                  processed_data[idx] = int(entry[0])
               except ValueError:
                  pass
         self._cached_data[hero_town_name] = processed_data
      self._cached_time = time.time()

   def _should_use_cache(self) -> bool:
      return ((self._cached_data is not None) and
              ((time.time() - self._cached_time) <= self._cache_fresh_time))

   def _get_change_percent(self, before: int, after: int) -> float:
      return round(100 * ((after - before) / before), 2)

   def _get_idx_for_turn(self, turn: int) -> int:
      # Clamp the value between [0, max_turn - 1].
      return BasicUtils.clamp_number(turn - 1, 0, self._max_turn - 1)

   def _get_current_turn(self) -> int:
      # Clamp the value between [1, max_turn].
      current_turn = int((time.time() - self._starting_time) / 3600) + 1
      return BasicUtils.clamp_number(current_turn, 1, self._max_turn)

   def _setup_logging(self) -> None:
      self._log = logger_factory.get_logger('stonk-sheet-querier')
      self._log.setLevel(logging.INFO)
