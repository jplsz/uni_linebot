from datetime import datetime, timedelta
import gspread
from google_sheets_util import get_sheet
from library import get_jst_date, get_jst_time

# 忘却曲線のスケジュール
REVIEW_DAYS = [1, 3, 7, 14, 30]

# 復習対象を取得
def get_review_targets():
    sheet = get_sheet()
    records = sheet.get_all_records()
    today = datetime.now().date()
    targets = []

    for row in records:
        try:
            date_str = row.get("Date")
            subject = row.get("Subject")
            title = row.get("Title")

            task_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            days_since = (today - task_date).days

            if days_since in REVIEW_DAYS:
                targets.append({
                    "date": date_str,
                    "subject": subject,
                    "title": title,
                    "review_stage": REVIEW_DAYS.index(days_since) + 1
                })
        except Exception as e:
            print(f"⚠️ 日付パースエラー: {row} - {e}")
            continue

    return targets

def record_review_reminder(subject, title, stage):
    date = get_jst_date()
    timestamp = get_jst_time()
    sheet = get_sheet("復習記録")

    sheet.append_row([date, subject, title, stage, timestamp])
    return True