from collections import Counter
from datetime import datetime, timedelta
from google_sheets_util import get_sheet, get_emotion_sheet, append_row_to_sheet
from openai import OpenAI
from zoneinfo import ZoneInfo
from library import get_jst_date

client = OpenAI()
import os

def get_week_range():
    """今週の月曜〜日曜の日付範囲を取得"""
    today = get_jst_date()

    start = today - timedelta(days=today.weekday()) # 月曜日
    end = start + timedelta(days=6) # 日曜日
    return start.date(), end.date()

def fetch_weekly_summary():
    start_date, end_date = get_week_range()
    sheet = get_sheet()
    emotion_sheet = get_emotion_sheet()

    # 達成記録の取得
    records = sheet.get_all_records()
    weekly_tasks = [
        row for row in records
        if start_date <= datetime.strptime(row["Date"], "%Y-%m-%d").date() <= end_date
    ]
    actual_count = len(weekly_tasks)

    # 実活動日数
    days_with_tasks = set(row["Date"] for row in weekly_tasks)
    ideal_count = len(days_with_tasks) * 3 # 1日3件が理想

    # 感情ログの取得
    emotion_records = emotion_sheet.get_all_records()
    weekly_emotions = [
        row for row in emotion_records
        if start_date <= datetime.strptime(row["today"], "%Y-%m-%d").date()
    ]

    # 平均集中度・感情傾向
    focus_values = []
    emojis = []
    for row in weekly_emotions:
        try:
            focus = int(row["集中度"].replace("%", "").strip())
            focus_values.append(focus)
            emojis.append(row["感情"])
        except:
            continue

    avg_focus = round(sum(focus_values) / len(focus_values)) if focus_values else 0
    top_emoji = Counter(emojis).most_common(1)[0][0] if emojis else "😐"

    # 結果を辞書で返す
    return {
        "週": f"{start_date} ~ {end_date}",
        "理想達成数": ideal_count,
        "実達成数": actual_count,
        "達成率": f"{round(actual_count / ideal_count * 100)}%" if ideal_count > 0 else "0%",
        "平均集中度": f"{avg_focus}%",
        "感情傾向": top_emoji
    }

def generate_summary_comment(summary_data):
    prompt = (
        f"以下は、ある学生の1週間の学習活動のサマリーです：\n"
        f"- 週の期間：{summary_data['週']}\n"
        f"- 理想達成数：{summary_data['理想達成数']}件\n"
        f"- 実達成数：{summary_data['実達成数']}件\n"
        f"- 達成率：{summary_data['達成率']}\n"
        f"- 平均集中度：{summary_data['平均集中度']}\n"
        f"- 感情傾向：{summary_data['感情傾向']}\n\n"
        f"このデータをもとに、学生に向けてポジティブで具体的な振り返りコメントを100文字以内で書いてください。"
    )

    response = client.chat.completions.create(
        model = "gpt-4o",
        messages = [
            {"role": "system", "content": "あなたは学習支援アシスタントです。。"},
            {"role": "user", "content": prompt}
        ]
    )

    print(response.choices[0].message.content)
    return response.choices[0].message.content.strip()

def create_weekly_report_message(summary_data, summary_comment):
    message = (
        f"📊 【今週のUniQuestレポート】\n\n"
        f"🎯 クエスト達成まとめ（{summary_data['週']}）\n"
        f"合計達成数：{summary_data['実達成数']}件（理想値：{summary_data['理想達成数']}件）\n"
        f"達成率：{summary_data['達成率']}\n\n"
        f"🧠 今週の気分と集中度\n"
        f"平均集中度：{summary_data['平均集中度']}\n"
        f"感情傾向：{summary_data['感情傾向']}\n\n"
        f"🤖 総括コメント：\n{summary_comment}\n\n"
    )
    return message

def record_weekly_report(summary_data, comment):
    row = [
        summary_data.get('週'),
        summary_data.get('理想達成数'),
        summary_data.get('実達成数'),
        summary_data.get('達成率'),
        summary_data.get('平均集中度'),
        summary_data.get('感情傾向'),
        comment
    ]
    print(summary_data)
    append_row_to_sheet('週次レポート', row)