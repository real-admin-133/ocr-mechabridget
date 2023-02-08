
class BasicUtils(object):
   @staticmethod
   def get_list_from_csv(csv_str: str) -> list[str]:
      return [x.strip() for x in csv_str.split(',') if x.strip()]

   @staticmethod
   def get_int_list_from_csv(csv_str: str) -> list[int]:
      str_list = BasicUtils.get_list_from_csv(csv_str)
      int_list = []
      for s in str_list:
         try:
            int_list.append(int(s))
         except ValueError:
            pass
      return int_list

   @staticmethod
   def split_list_to_chunks(src_list: list, chunk_size: int) -> list[list]:
      output = []
      for i in range(0, len(src_list), chunk_size):
         output.append(src_list[i:i + chunk_size])
      return output
