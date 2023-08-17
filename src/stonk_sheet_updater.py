import os
import json
import logging

import gspread_formatting as gsf

from config_loader import config
from logging_utils import logger_factory
from stonk_sheet_base import StonkSheetBase
from tip_recognizer import Tip


class StonkSheetUpdater(StonkSheetBase):
   CONFIG_SECTION = 'stonk-sheet-updater'
   PRICE_CELL_FORMAT = os.path.join(os.environ['TEMPLATES_DIR'], 'price_cell_format.json')
   CHANGE_CELL_FORMAT = os.path.join(os.environ['TEMPLATES_DIR'], 'change_cell_format.json')

   def __init__(self) -> None:
      self._setup_logging()
      self._setup_stonk_sheet()
      self._incl_change_update = config.getboolean(self.CONFIG_SECTION, 'incl_change_update')
      self._incl_action_update = config.getboolean(self.CONFIG_SECTION, 'incl_action_update')
      with open(self.PRICE_CELL_FORMAT, 'r') as file:
         self._price_cell_format = json.load(file)
      with open(self.CHANGE_CELL_FORMAT, 'r') as file:
         self._change_cell_format = json.load(file)
      if self._incl_change_update:
         # Setup conditional format rules for change columns.
         self._setup_change_format_rules()

   def update_sheet(self, tip: Tip) -> None:
      self._update_price(tip)
      if self._incl_change_update:
         self._update_change(tip)
      if self._incl_action_update:
         self._update_action(tip)

   def _update_price(self, tip: Tip) -> None:
      col = self.PRICE_COLUMNS[tip.hero_town.value]
      src_cell = self._get_turn_acell(col, tip.current_turn)
      dst_cell = self._get_turn_acell(col, tip.target_turn)
      op, abs_price_change = tip.get_price_change_op_and_abs()
      dst_value = '=HYPERLINK("{}", IF(ISNUMBER({}), {} {} {}, "T{} {} {}"))'.format(
         tip.url, src_cell, src_cell, op, abs_price_change, tip.current_turn, op, abs_price_change)
      self._sheet.update(dst_cell, dst_value, raw=False)
      self._sheet.format(dst_cell, self._price_cell_format)

   def _update_change(self, tip: Tip) -> None:
      price_col = self.PRICE_COLUMNS[tip.hero_town.value]
      start_cell = self._get_fixed_row_turn_acell(price_col, 1)
      end_cell = self._get_turn_acell(price_col, tip.target_turn - 1)
      target_cell = self._get_turn_acell(price_col, tip.target_turn)
      # Construct formula.
      filter_range_formula = 'FILTER({}:{}, ISNUMBER({}:{}))'.format(
         start_cell, end_cell, start_cell, end_cell)
      base_cell_formula = 'INDEX({}, COUNT({}))'.format(
         filter_range_formula, filter_range_formula)
      change_formula = 'ROUND(100 * ({} - {}) / {}, 1)'.format(
         target_cell, base_cell_formula, base_cell_formula)
      sign_formula = 'IFS({} > 0, "▲", {} < 0, "▼", {} = 0, "∴ ")'.format(
         change_formula, change_formula, change_formula)
      dst_value = '=IF(ISNUMBER({}), CONCATENATE({}, ABS({}), "%"), "")'.format(
         target_cell, sign_formula, change_formula)
      # Edit destination cell.
      change_col = self.CHANGE_COLUMNS[tip.hero_town.value]
      dst_cell = self._get_turn_acell(change_col, tip.target_turn)
      self._sheet.update(dst_cell, dst_value, raw=False)
      self._sheet.format(dst_cell, self._change_cell_format)

   def _update_action(self, tip: Tip) -> None:
      # TODO: Meh, too much effort to automate this effectively.
      pass

   def _setup_logging(self) -> None:
      self._log = logger_factory.get_logger('stonk-sheet-updater')
      self._log.setLevel(logging.INFO)

   def _setup_change_format_rules(self):
      rules = gsf.get_conditional_format_rules(self._sheet)
      rules.clear()
      cell_ranges = []
      for _, col in self.CHANGE_COLUMNS.items():
         start_cell = self._get_turn_acell(col, 1)
         end_cell = self._get_turn_acell(col, self._max_turn)
         cell_range = '{}:{}'.format(start_cell, end_cell)
         cell_ranges.append(gsf.GridRange.from_a1_range(cell_range, self._sheet))
      inc_price_rule = gsf.ConditionalFormatRule(
         ranges=cell_ranges,
         booleanRule=gsf.BooleanRule(
            condition=gsf.BooleanCondition('TEXT_CONTAINS', ['▲']),
            format=gsf.CellFormat(
               textFormat=gsf.TextFormat(
                  foregroundColorStyle=gsf.ColorStyle(rgbColor=gsf.Color(1, 0, 0))
               )
            )
         )
      )
      dec_price_rule = gsf.ConditionalFormatRule(
         ranges=cell_ranges,
         booleanRule=gsf.BooleanRule(
            condition=gsf.BooleanCondition('TEXT_NOT_CONTAINS', ['▲']),
            format=gsf.CellFormat(
               textFormat=gsf.TextFormat(
                  foregroundColorStyle=gsf.ColorStyle(rgbColor=gsf.Color(0, 0, 1))
               )
            )
         )
      )
      rules.append(inc_price_rule)
      rules.append(dec_price_rule)
      rules.save()
