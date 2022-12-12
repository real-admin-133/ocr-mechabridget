import os
import sys
import glob
import argparse
import logging

import cv2

sys.path.append(os.environ['SRC_DIR'])

from logging_utils import logger_factory

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logger_factory.formatter)
logger_factory.handler = stream_handler

from tip_recognizer import TipRecognizer


SAMPLES_DIR = os.environ['SAMPLES_DIR']
EN_IMAGE_PATH = os.path.join(SAMPLES_DIR, 'en')
CN_IMAGE_PATH = os.path.join(SAMPLES_DIR, 'cn')
KR_IMAGE_PATH = os.path.join(SAMPLES_DIR, 'kr')

log = logger_factory.get_logger('dry-run')
log.setLevel(logging.INFO)

recognizer = TipRecognizer()


def parse_args() -> argparse.Namespace:
   parser = argparse.ArgumentParser()
   parser.add_argument('--filter', required=False, default='samples',
      help='Select a sub-group of sample images')
   parser.add_argument('--show-image', required=False, action='store_true',
      help='Show each image and wait for a keypress before moving to next one')
   args = parser.parse_args()
   return args

def main() -> None:
   args = parse_args()
   success_count = 0
   fail_count = 0
   fail_images = []
   for image_dir in (EN_IMAGE_PATH, CN_IMAGE_PATH, KR_IMAGE_PATH):
      images = glob.glob(os.path.join(image_dir, '*'))
      for filepath in images:
         if args.filter not in filepath:
            continue
         log.info('Load image: "{}"'.format(filepath))
         image = cv2.imread(filepath)
         success, _ = recognizer.process_tip(image)
         if success:
            success_count += 1
         else:
            fail_count += 1
            fail_images.append(filepath.removeprefix(SAMPLES_DIR))
         if args.show_image:
            cv2.imshow('tip-image', image)
            cv2.waitKey(0)
   log.info('Completed all samples, success={}, fail={}'.format(success_count, fail_count))
   if fail_count > 0:
      log.info('Failed images: {}'.format(fail_images))
   cv2.destroyAllWindows()


if __name__ == '__main__':
   main()
