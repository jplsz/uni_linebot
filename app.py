from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import gspread
import re
import random
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from io import StringIO
from weekly_report import fetch_weekly_summary, generate_summary_comment, create_weekly_report_message, get_week_range, record_weekly_report
from google_sheets_util import get_sheet, get_emotion_sheet
from library import get_jst_date, get_jst_time, load_tasks
from review_reminder import REVIEW_DAYS, get_review_targets, record_review_reminder

app = Flask(__name__)

# LINE Botの設定（トークンは環境変数または直接記述でも可）
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET", "YOUR_SECRET"))

# ユーザーID（Push先：自分のID）
USER_ID = "U7f366710ac3959bbaa4041a5c6a2dc5c" # ←自分のLINE ID

# 文字列の正規化
def normalize(text):
    if not text:
        return ''
    text = unicodedata.normalize("NFKC", text).strip()
    text = re.sub(r'\s', '', text)
    return text.lower()

# 日付の形式に対応
def parse_deadline(date_str):
    """ハイフン・スラッシュどちらの形式にも対応"""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {date_str}")

# 「第◯回」の抽出
def extract_lesson_number(title):
    """タイトルから「第◯回」の数字を抽出"""
    match = re.search(r"第(\d+)回", title)
    return int(match.group(1)) if match else 9999 #該当なしは後回し

# 達成済みタスクの取得関数
def get_completed_tasks():
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        completed = set()
        for row in records:
            print(f"[DEBUG] 読み込んだ行: {row}")
            completed.add((normalize(row["Subject"]), normalize(row["Title"])))
        return completed
    except Exception as e:
        print(f"❌️ 達成済みタスクの取得失敗: {e}")
        return set()

# 今日のクエストを抽出
def get_todays_quests(task_list, max_tasks=3):
    today = datetime.now().date()
    completed = get_completed_tasks()

    # 未達成かつ締切が今日以降のタスクを抽出
    filtered = []
    for task in task_list:
        try:
            deadline = parse_deadline(task["deadline"])
            if deadline >= today and (task["subject"], task["title"]) not in completed:
                filtered.append(task)
        except Exception as e:
            print(f"❌️ タスクフィルタ中エラー: {e}")
            continue

    # 各科目ごとに最も若い回をピックアップ
    subject_to_tasks = {}
    for task in filtered:
        subject = task["subject"]
        current = subject_to_tasks.get(subject)

        if current is None or extract_lesson_number(task["title"]) < extract_lesson_number(current["title"]):
            subject_to_tasks[subject] = task

    # ピックアップされたものをランダムに並べ、上から3件
    selected = list(subject_to_tasks.values())
    random.shuffle(selected)
    return selected[:max_tasks]

# 達成記録をGoogle Sheetsに保存
def record_task_completion(subject, title):
    date = get_jst_date()
    timestamp = get_jst_time()
    subject = normalize(subject)
    title = normalize(title)

    try:
        sheet = get_sheet()

        # 重複チェック（同じ日付・科目・タイトルが既にあるか）
        records = sheet.get_all_records()
        for row in records:
            if normalize(row["Date"]) == date and normalize(row["Subject"]) == subject and normalize(row["Title"]) == title:
                return False # 重複
        # 新規行の追加
        sheet.append_row([date, subject, title, timestamp])
        return True
    except Exception as e:
        print(f"❌️ Google Sheetsへの書き込み失敗: {e}")
        return False

# 感情ログを保存
def record_emotion_log(emoji, focus, comment):
    sheet = get_emotion_sheet()
    today = get_jst_date()

    sheet.append_row([today, emoji, focus, comment])
    return True

# 未達成タスクの総数
def get_tasks_total():
    today = datetime.now().date()
    completed = get_completed_tasks()
    task_list = load_tasks()

    # 締切が今日以降かつ未達成のタスクを抽出
    filtered = []
    for task in task_list:
        try:

            deadline = parse_deadline(task["deadline"])
            subject = normalize(task["subject"])
            title = normalize(task["title"])

            if (subject, title) not in completed:
                print(f"[DEBUG] 未達: ({subject}, {title})")
            else:
                print(f"[DEBUG] 達成済: ({subject}, {title})")
            if deadline >= today and (subject, title) not in completed:
                filtered.append(task)
        except Exception as e:
            print(f"❌️ タスクフィルタ中エラー: {e}")
            continue
    # 抽出されたタスクの総数をカウント
    total = len(filtered)
    # print(filtered)
    # print(completed)
    return total

# 週次レポート
def send_weekly_report():
    try:
        summary = fetch_weekly_summary()
        comment = generate_summary_comment(summary)
        message = create_weekly_report_message(summary, comment)

        record_weekly_report(summary, comment)
        line_bot_api.push_message(USER_ID, TextSendMessage(text=message))
        print("✅️ 週次レポートを送信しました。")
    except Exception as e:
        print("❌️ 週次レポート送信に失敗：", e)

# 復習リマインド
def send_review_push():
    review_targets = get_review_targets()

    if not review_targets:
        message = "📘 今日の復習対象はありません！ゆっくり休もう✨️"
    else:
        message = "🔁 今日の復習対象はこちら！\n\n"
        for task in review_targets:
            message += (
                f"📘 {task['subject']} : {task['title']}\n"
                f"📅 学習日：{task['date']}({task['review_stage']}回目の復習)\n\n"
            )

    try:
        line_bot_api.push_message(
            USER_ID,
            TextSendMessage(text=message)
        )
        print("✅️ 復習Push送信成功！")
    except Exception as e:
        print(f"❌️ Push通知送信失敗：{e}")

# Push通知を送るためのエンドポイント（Render上で手動アクセス or スケジューラー用）
@app.route("/push_daily_quests", methods=["GET"])
def push_daily_quests():
    tasks = load_tasks()
    quests = get_todays_quests(tasks)

    if not quests:
        message = "🎯 今日のクエストはありません！ゆっくり休もう✨️"
    else:
        message = "📅 今日のクエストはこちら！\n\n"
        for q in quests:
            message += (
                f"📘 {q['subject']}：{q['title']}\n"
                f"🗓️ 締切：{q['deadline']}\n\n"
            )

    # LINEにPush送信
    line_bot_api.push_message(
        USER_ID,
        TextSendMessage(text=message)
    )

    return "OK", 200

@app.route("/push_daily_emotion_log", methods=["GET"])
def push_daily_emotion_log():
    message = (
        "🧠 今日の感情はどうだった？\n"
        "例）🧠 感情ログ：😐 集中50% コメント：あまりやる気が出なかったけど頑張った"
    )

    line_bot_api.push_message(
        USER_ID,
        TextSendMessage(text=message)
    )

    return "OK", 200

@app.route("/push_weekly_report", methods=["GET"])
def trigger_weekly_report():
    try:
        send_weekly_report()
        return "✅️ Weekly report sent", 200
    except Exception as e:
        return f"❌️ Error: {str(e)}", 500

@app.route("/push_review_reminder", methods=["GET"])
def push_review_reminder():
    try:
        send_review_push()
        return "✅️ Review reminder sent", 200
    except Exception as e:
        return f"❌️ Error: {str(e)}", 500

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        abort(400)

    return "OK"
def clean_text(text):
    # 制御文字を除去
    text = re.sub(r'[\x00-\x1F\x7F]', '', text)
    return text.strip()

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    raw_text = event.message.text
    text = clean_text(raw_text)

    if text.startswith("✅️"):
        # 例：✅️福祉心理学:第1回(映像授業)
        try:
            rest = text[1:].strip()
            subject, title = rest.split("：", 1)
            subject = subject.strip()
            title = title.strip()

            success = record_task_completion(subject, title)
            if success:
                reply = f"📝 記録しました！\n✅️{subject}：{title}"
            else:
                reply = "⚠️ すでに記録済みです。"
        except Exception as e:
            reply = "❌️ 記録形式が正しくありません。\n例：✅️福祉心理学：第3回(映像授業)"
    elif text == "クエスト":
        tasks = load_tasks()
        quests = get_todays_quests(tasks)

        if not quests:
            reply = "🎯 今日のクエストはありません！ゆっくり休もう✨️"
        else:
            reply = "📅 今日のクエストはこちら！\n\n"
            for q in quests:
                reply += (
                f"📘 {q['subject']}：{q['title']}\n"
                f"🗓️ 締切：{q['deadline']}\n"
                )
    elif text == "週次レポート":
        try:
            send_weekly_report()
            reply = "📊 週次レポートを送信しました！"
        except Exception as e:
            reply = f"❌️ エラー：{str(e)}"
    elif text == "合計":
        try:
            total = get_tasks_total()
            reply = f"📚️ 未達成タスク：{total}件"
        except Exception as e:
            reply = "❌️ 合計の取得中にエラーが発生しました。"
    elif text.startswith("🧠 感情ログ："):
        try:
            match = re.match(r"🧠 感情ログ：(.+?) 集中(\d+%) コメント：(.*)", text)
            if match:
                emoji = match.group(1).strip()
                focus = match.group(2).strip()
                comment = match.group(3).strip()
                record_emotion_log(emoji, focus, comment)
                reply = f"🧠 感情ログを記録しました！\n{emoji} 集中{focus}\nコメント：{comment or 'なし'}"
            else:
                reply = "⚠️ 書式が正しくありません。\n例）🧠 感情ログ：🙂 集中70% コメント：今日はまあまあ集中できた"
        except Exception as e:
            print(f"❌ 感情ログの記録中にエラー: {e}")
            reply = "❌ 感情ログの記録中にエラーが発生しました。"
    elif text.startswith("🔁"):
        # 例) 🔁福祉心理学:第1回(映像授業)
        try:
            match = re.match(r"🔁(.+?)：(.+?)【(.+?)】", text)
            if match:
                subject = match.group(1).strip()
                title = match.group(2).strip()
                stage = match.group(3).strip()
                success = record_review_reminder(subject, title, stage)
            if success:
                reply = f"📝 復習を記録しました！🔁{subject}：{title}【{stage}】"
            else:
                reply = "⚠️ すでに記録済みです。"
        except Exception as e:
            reply = "❌️ 記録形式が正しくありません。\n例：🔁福祉心理学：第3回(映像授業)【3回目】"
    else:
        reply = "📩 クエスト達成を記録したい場合は\n✅️福祉心理学：第3回(映像授業) のように送ってください！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )