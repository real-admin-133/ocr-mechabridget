import os
import sys
import shutil
import logging
import configparser

from logging_utils import logger_factory


class ConfigLoader(object):
   LOCAL_CONFIG_TEMPLATE = os.path.join(os.environ['TEMPLATES_DIR'], 'local_config.ini')
   LOCAL_CONFIG = os.path.join(os.environ['ROOT_DIR'], 'config.local.ini')
   CONFIG_STACK = [
      os.path.join(os.environ['ROOT_DIR'], 'config.ini'),
      LOCAL_CONFIG
   ]
   REQUIRED_FIELDS = [
      'tip-recognizer.gvision_service_account_file',
      'discord-bot.auth_token',
      'stonk-sheet-updater.gsheets_service_account_file',
      'stonk-sheet-updater.spreadsheet_id',
      'stonk-sheet-updater.sheet_name'
   ]

   def __init__(self) -> None:
      self._setup_logging()
      self._ensure_local_config()

   def get_config(self) -> configparser.ConfigParser:
      config = configparser.ConfigParser()
      for config_file in self.CONFIG_STACK:
         config.read(config_file)
      self._validate_config(config)
      return config

   def _setup_logging(self) -> None:
      self._log = logger_factory.get_logger('config-loader')
      self._log.setLevel(logging.INFO)

   def _ensure_local_config(self) -> None:
      if not os.path.isfile(self.LOCAL_CONFIG):
         self._log.info('Local config not found. Creating new one...')
         shutil.copyfile(self.LOCAL_CONFIG_TEMPLATE, self.LOCAL_CONFIG)
         sys.exit('Program terminated. Please fill in the fields in "{}" before starting again.'.format(self.LOCAL_CONFIG))

   def _validate_config(self, config: configparser.ConfigParser) -> None:
      for field in self.REQUIRED_FIELDS:
         section, key = field.split('.', 2)
         value = config.get(section, key, fallback='')
         if not value:
            raise ValueError('Missing value for required field "{}"'.format(field))


config = ConfigLoader().get_config()
