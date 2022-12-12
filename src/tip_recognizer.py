import re
import logging

import numpy
import cv2
from google.oauth2 import service_account
from google.cloud import vision as google_vision

from config_loader import config
from logging_utils import logger_factory
from shared_constants import HeroTown


class OpenCVError(Exception):
   pass

class GoogleVisionError(Exception):
   pass

class TipParsingError(Exception):
   pass


class Tip(object):
   def __init__(self, hero_town: HeroTown, current_turn: int,
                target_turn: int, price_change: int) -> None:
      self.hero_town = hero_town
      self.current_turn = current_turn
      self.target_turn = target_turn
      self.price_change = price_change
      self.url = ''

   def get_price_change_op_and_abs(self) -> tuple[str, int]:
      op = '+' if self.price_change >= 0 else '-'
      abs_price_change = abs(self.price_change)
      return op, abs_price_change

   def to_string(self) -> str:
      op, abs_price_change = self.get_price_change_op_and_abs()
      return '{} T{} = T{} {} {}'.format(
         self.hero_town.value, self.target_turn, self.current_turn, op, abs_price_change)


class TipRecognizer(object):
   CONFIG_SECTION = 'tip-recognizer'
   SEARCH_KEYWORDS = (
      (HeroTown.CELINE, ['Celine', 'Atelier']),
      (HeroTown.CHOCOLAT, ['Chocolat', 'Bakery']),
      (HeroTown.FERGUS, ['Fergus', 'Anvil']),
      (HeroTown.LEDNAS, ['Lednas', 'Association']),
      (HeroTown.LENNY, ['Lenny', 'Orchard'])
   )
   CURR_TURN_REGEX = re.compile(r'\ATURN (?P<turn_number>\d+)')
   TARGET_TURN_REGEX_EN = re.compile(r'Turn (?P<turn_number>\d+)')
   PRICE_CHANGE_REGEX_EN = re.compile(r'approximately (?P<price_change>-?\d+)')
   PRICE_NO_CHANGE_KEYWORDS = ['remain stable']

   def __init__(self) -> None:
      self._setup_logging()
      self._setup_gvision()

   def process_tip(self, image: numpy.ndarray) -> tuple[bool, Tip]:
      try:
         tip_curturn_image, tip_content_image = self._locate_latest_tip_region(image)
         tip_text = self._do_gvision_ocr_work(cv2.vconcat([tip_curturn_image, tip_content_image]))
         hero_town = self._get_hero_town_name(tip_text)
         curr_turn = self._get_current_turn(tip_text)
         target_turn = self._get_target_turn(tip_text)
         price_change = self._get_price_change(tip_text)
         tip = Tip(hero_town, curr_turn, target_turn, price_change)
         self._log.info('Parsed tip: "{}"'.format(tip.to_string()))
         return True, tip
      except (OpenCVError, GoogleVisionError, TipParsingError) as e:
         self._log.error(str(e))
         return False, Tip(HeroTown.UNKNOWN, -1, -1, 0)

   def _setup_logging(self) -> None:
      self._log = logger_factory.get_logger('tip-recognizer')
      self._log.setLevel(logging.INFO)

   def _setup_gvision(self) -> None:
      gvision_credentials = service_account.Credentials.from_service_account_file(
         filename=config.get(self.CONFIG_SECTION, 'gvision_service_account_file'),
         scopes=['https://www.googleapis.com/auth/cloud-platform'])
      self._gvision_client = google_vision.ImageAnnotatorClient(credentials=gvision_credentials)

   def _locate_latest_tip_region(self, image: numpy.ndarray) -> tuple[numpy.ndarray, numpy.ndarray]:
      grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
      _, binary = cv2.threshold(
         grayscale, config.getint(self.CONFIG_SECTION, 'latest_tip_border_threshold'),
         255, cv2.THRESH_BINARY)
      # Draw a 1-pixel-wide border around the binary image to help forming a contour for
      # images in which the author were too lazy to capture the entire latest tip's box.
      binary = cv2.copyMakeBorder(binary, top=1, bottom=1, left=1, right=1,
         borderType=cv2.BORDER_CONSTANT, value=255)
      # Find the 2 largest, inner-most contours.
      # The largest is the tip's content, and the second largest is the tip's current turn.
      contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
      if not contours:
         raise OpenCVError('No contour found')
      inner_most_contours = []
      for idx, entry in enumerate(hierarchy[0]):
         # Inner-most = No child contour.
         if entry[2] == -1:
            inner_most_contours.append((idx, contours[idx]))
      if len(inner_most_contours) < 2:
         raise OpenCVError('Cannot locate contours surrounding the latest tip')
      inner_most_contours.sort(reverse=True, key=lambda e: cv2.contourArea(e[1]))
      first_contour = contours[inner_most_contours[0][0]]
      second_contour = contours[inner_most_contours[1][0]]
      # Mask the original image.
      white_color = (255, 255, 255)
      outputs = []
      for cntr in [second_contour, first_contour]:
         mask = numpy.zeros_like(image)
         out = numpy.zeros_like(image)
         cv2.drawContours(mask, [cntr], -1, white_color, -1)
         out[mask == 255] = image[mask == 255]
         outputs.append(out)
      return tuple(outputs)

   def _do_gvision_ocr_work(self, image: numpy.ndarray) -> str:
      _, encoded_image = cv2.imencode('.png', image)
      gvision_image = google_vision.Image(content=encoded_image.tobytes())
      response = self._gvision_client.text_detection(image=gvision_image)
      err_msg = response.error.message
      if err_msg:
         raise GoogleVisionError('Failed GoogleOCR, message="{}"'.format(err_msg))
      if not response.text_annotations:
         return ''
      return response.text_annotations[0].description.replace('\n', ' ')

   def _get_hero_town_name(self, tip_text: str) -> HeroTown:
      for keywords_group in self.SEARCH_KEYWORDS:
         for keyword in keywords_group[1]:
            if keyword in tip_text:
               self._log.debug('Matched NPC for tip, keyword="{}", tip="{}"'.format(keyword, tip_text))
               return keywords_group[0]
      raise TipParsingError('Unknown NPC for tip, tip="{}"'.format(tip_text))

   def _get_current_turn(self, tip_text: str) -> int:
      re_match = self.CURR_TURN_REGEX.search(tip_text)
      if not re_match:
         raise TipParsingError('Unknown current turn for tip, tip="{}"'.format(tip_text))
      curr_turn_str = re_match.group('turn_number')
      try:
         curr_turn = int(curr_turn_str)
         self._log.debug('Found current turn for tip, turn={}, tip="{}"'.format(curr_turn, tip_text))
         return curr_turn
      except ValueError:
         raise TipParsingError('Unknown current turn for tip, match="{}", tip="{}"'.format(curr_turn_str, tip_text))

   def _get_target_turn(self, tip_text: str) -> int:
      # TODO: Add RegEx patterns for CN and KR.
      for pattern in (self.TARGET_TURN_REGEX_EN,):
         re_match = pattern.search(tip_text)
         if not re_match:
            continue
         target_turn_str = re_match.group('turn_number')
         try:
            target_turn = int(target_turn_str)
            self._log.debug('Found target turn for tip, turn={}, tip="{}"'.format(target_turn, tip_text))
            return target_turn
         except ValueError:
            raise TipParsingError('Unknown target turn for tip, match="{}", tip="{}"'.format(target_turn_str, tip_text))
      raise TipParsingError('Unknown target turn for tip, tip="{}"'.format(tip_text))

   def _get_price_change(self, tip_text: str) -> int:
      # TODO: Add RegEx patterns for CN and KR.
      for keyword in self.PRICE_NO_CHANGE_KEYWORDS:
         if keyword in tip_text:
            self._log.debug('No price change for tip, keyword="{}", tip="{}"'.format(keyword, tip_text))
            return 0
      for pattern in (self.PRICE_CHANGE_REGEX_EN,):
         re_match = pattern.search(tip_text)
         if not re_match:
            continue
         price_change_str = re_match.group('price_change')
         try:
            price_change = int(price_change_str)
            self._log.debug('Found price change for tip, price_change={}, tip="{}"'.format(price_change, tip_text))
            return price_change
         except ValueError:
            raise TipParsingError('Unknown price change for tip, match="{}", tip="{}"'.format(price_change_str, tip_text))
      raise TipParsingError('Unknown price change for tip, tip="{}"'.format(tip_text))
