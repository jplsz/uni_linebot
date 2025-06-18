from zoneinfo import ZoneInfo
from datetime import datetime

# UTCをJSTに変換(時間)
def get_jst_time():
    jst = ZoneInfo("Asia/Tokyo")
    aware_jst = datetime.now(jst)

    return aware_jst.strftime("%Y-%m-%dT%H:%M:%S")

# UTCをJSTに変換(日付のみ)
def get_jst_date():
    jst = ZoneInfo("Asia/Tokyo")
    aware_jst = datetime.now(jst)

    return aware_jst.strftime("%Y-%m-%d")