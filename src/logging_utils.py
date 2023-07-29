import os
import logging


class LoggingUtils(object):
   LOG_FORMAT = r'%(asctime)s - %(name)s - [%(levelname)s] %(message)s'
   LOG_FILE = os.path.join(os.environ['ROOT_DIR'], 'runtime.log')

   def __init__(self) -> None:
      self.formatter = logging.Formatter(self.LOG_FORMAT)
      self.handler = logging.FileHandler(self.LOG_FILE)
      self.handler.setFormatter(self.formatter)

   def get_logger(self, logger_name: str) -> logging.Logger:
      logger = logging.getLogger(logger_name)
      if not logger.hasHandlers():
         logger.addHandler(self.handler)
      return logger


logger_factory = LoggingUtils()
