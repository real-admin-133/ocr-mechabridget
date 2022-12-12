
class BasicUtils(object):
   @staticmethod
   def get_list_from_csv(csv_str: str) -> list[str]:
      return [x.strip() for x in csv_str.split(',') if x.strip()]
