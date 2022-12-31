import os
import pickle
import copy
import logging

from logging_utils import logger_factory


class SimpleDataSaver(object):
   SAVE_FILE = os.path.join(os.environ['ROOT_DIR'], '.saved')
   PICKLE_PROTOCOL = 4

   def __init__(self) -> None:
      self._setup_logging()
      self._data = {}
      self._load_data()

   def load_key(self, key: str, default = None):
      try:
         ret = copy.deepcopy(self._data[key])
      except KeyError:
         ret = default
      self._log.debug('Loaded key, key="{}", default={}, ret={}'.format(
         key, default, ret))
      return ret

   def save_key(self, key: str, value) -> None:
      self._data[key] = copy.deepcopy(value)
      self._save_data()
      self._log.debug('Saved key, key="{}", value={}, data={}'.format(
         key, value, self._data))

   def _load_data(self) -> None:
      self._ensure_save_file()
      with open(self.SAVE_FILE, 'rb') as file:
         self._data = pickle.load(file)

   def _save_data(self) -> None:
      with open(self.SAVE_FILE, 'wb') as file:
         pickle.dump(self._data, file, protocol=self.PICKLE_PROTOCOL)

   def _ensure_save_file(self) -> None:
      if not os.path.isfile(self.SAVE_FILE):
         self._save_data()

   def _setup_logging(self) -> None:
      self._log = logger_factory.get_logger('simple-data-saver')
      self._log.setLevel(logging.INFO)


simple_saver = SimpleDataSaver()
