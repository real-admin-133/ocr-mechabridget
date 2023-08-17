from google.oauth2 import service_account
import gspread

from config_loader import config
from shared_constants import HeroTown


class StonkSheetBase(object):
   CONFIG_SECTION = 'stonk-sheet-base'
   PRICE_COLUMNS = {
      HeroTown.CELINE.value: config.get(CONFIG_SECTION, 'price_column_celine'),
      HeroTown.CHOCOLAT.value: config.get(CONFIG_SECTION, 'price_column_chocolat'),
      HeroTown.FERGUS.value: config.get(CONFIG_SECTION, 'price_column_fergus'),
      HeroTown.LENNY.value: config.get(CONFIG_SECTION, 'price_column_lenny'),
      HeroTown.LEDNAS.value: config.get(CONFIG_SECTION, 'price_column_lednas')
   }
   CHANGE_COLUMNS = {
      HeroTown.CELINE.value: config.get(CONFIG_SECTION, 'change_column_celine'),
      HeroTown.CHOCOLAT.value: config.get(CONFIG_SECTION, 'change_column_chocolat'),
      HeroTown.FERGUS.value: config.get(CONFIG_SECTION, 'change_column_fergus'),
      HeroTown.LENNY.value: config.get(CONFIG_SECTION, 'change_column_lenny'),
      HeroTown.LEDNAS.value: config.get(CONFIG_SECTION, 'change_column_lednas')
   }
   ACTION_COLUMNS = {
      HeroTown.CELINE.value: config.get(CONFIG_SECTION, 'action_column_celine'),
      HeroTown.CHOCOLAT.value: config.get(CONFIG_SECTION, 'action_column_chocolat'),
      HeroTown.FERGUS.value: config.get(CONFIG_SECTION, 'action_column_fergus'),
      HeroTown.LENNY.value: config.get(CONFIG_SECTION, 'action_column_lenny'),
      HeroTown.LEDNAS.value: config.get(CONFIG_SECTION, 'action_column_lednas')
   }

   def _setup_stonk_sheet(self) -> None:
      # Subclass will override this value. So need to be specific here.
      config_section = StonkSheetBase.CONFIG_SECTION
      gsheets_credentials = service_account.Credentials.from_service_account_file(
         filename=config.get(config_section, 'gsheets_service_account_file'),
         scopes=[
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/spreadsheets'
         ]
      )
      gsheets_client = gspread.authorize(gsheets_credentials)
      spreadsheet = gsheets_client.open_by_key(config.get(config_section, 'spreadsheet_id'))
      self._sheet = spreadsheet.worksheet(config.get(config_section, 'sheet_name'))
      self._starting_row = config.getint(config_section, 'starting_row')
      self._max_turn = config.getint(config_section, 'max_turn')

   def _get_fixed_row_turn_acell(self, col: str, turn: int) -> str:
      return '{}${}'.format(col, self._get_row_number(turn))

   def _get_turn_acell(self, col: str, turn: int) -> str:
      return col + str(self._get_row_number(turn))

   def _get_row_number(self, turn: int) -> int:
      return turn + self._starting_row - 1
