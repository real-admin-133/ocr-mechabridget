import argparse

from discord_bot import DiscordBot


def parse_args() -> argparse.Namespace:
   parser = argparse.ArgumentParser()
   parser.add_argument('--prod-mode', required=False, action='store_true',
      help='Enable production mode')
   args = parser.parse_args()
   return args

def main() -> None:
   args = parse_args()
   DiscordBot(args).run()


if __name__ == '__main__':
   main()
