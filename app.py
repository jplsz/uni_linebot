from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import json
from datetime import datetime
import os
import gspread
import re
import random
from oauth2client.service_account import ServiceAccountCredentials
from io import StringIO


app = Flask(__name__)

# LINE Botの設定（トークンは環境変数または直接記述でも可）
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET", "YOUR_SECRET"))

# ユーザーID（Push先：自分のID）
USER_ID = "U7f366710ac3959bbaa4041a5c6a2dc5c" # ←自分のLINE ID

# タスクの読み込み
def load_tasks():
    with open("tasks.json", "r", encoding="utf-8") as f:
        return json.load(f)

# 「第◯回」の抽出
def extract_lesson_number(title):
    """タイトルから「第◯回」の数字を抽出"""
    match = re.search(r"第(\d+)回", title)
    return int(match.group(1)) if match else 9999 #該当なしは後回し

# 今日のクエストを抽出
def get_todays_quests(task_list, max_tasks=3):
    today = datetime.now().date()
    completed = get_completed_tasks()

    # 未達成かつ締切が今日以降のタスクを抽出
    filtered = []
    for task in task_list:
        try:
            deadline = datetime.strptime(task["deadline"], "%Y-%m-%d").date()
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

# # === 達成記録の保存処理 ===
# def record_task_completion(subject, title):
#     today = datetime.now().strftime("%Y-%m-%d")
#     done_file = "done_log.json"

#     # ログファイルが存在しなければ初期化
#     if not os.path.exists(done_file):
#         done_log = {}
#     else:
#         with open(done_file, "r", encoding="utf-8") as f:
#             done_log = json.load(f)

#     # 新規日付なら初期化
#     if today not in done_log:
#         done_log[today] = []

#     # 重複防止
#     if not any(t["subject"] == subject and t["title"] == title for t in done_log[today]):
#         done_log[today].append({
#             "subject": subject,
#             "title": title,
#             "completed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
#         })

#         with open(done_file, "w", encoding="utf-8") as f:
#             json.dump(done_log, f, indent=2, ensure_ascii=False)
#         return True # 成功
#     else:
#         return False # 既に記録済み

# Google Sheets接続設定
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Renderの環境変数から秘密鍵を読み込む
    raw_cred = os.environ.get("GOOGLE_CREDENTIALS_JSON")

    if raw_cred is None:
        raise Exception("GOOGLE_CREDENTIALS_JSON is not set")

    # エスケープされた改行を元に戻す
    # fixed_json = raw_cred.replace("\\n", "\n")
    # creds_dict = json.loads(fixed_json)

    creds_dict = json.loads(raw_cred)

    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    # スプレッドシートの名前を指定
    sheet = client.open("UniQuest達成記録").sheet1
    return sheet

# 達成記録をGoogle Sheetsに保存
def record_task_completion(subject, title):
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    try:
        sheet = get_sheet()

        # 重複チェック（同じ日付・科目・タイトルが既にあるか）
        records = sheet.get_all_records()
        for row in records:
            if row["Date"].strip() == today and row["Subject"].strip() == subject and row["Title"].strip == title:
                return False # 重複
        # 新規行の追加
        sheet.append_row([today, subject, title, timestamp])
        return True
    except Exception as e:
        print(f"❌️ Google Sheetsへの書き込み失敗: {e}")
        return False

# 達成済みタスクの取得関数
def get_completed_tasks():
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        completed = set()
        for row in records:
            completed.add((row["Subject"], row["Title"]))
        return completed
    except Exception as e:
        print(f"❌️ 達成済みタスクの取得失敗: {e}")
        return set()

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
                f"📘 {q['subject']}：{q['title']}{q['type']}\n"
                f"🗓️ 締切：{q['deadline']}\n\n"
            )

    # LINEにPush送信
    line_bot_api.push_message(
        USER_ID,
        TextSendMessage(text=message)
    )

    return "OK", 200

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
    else:
        reply = "📩 クエスト達成を記録したい場合は\n✅️福祉心理学：第3回(映像授業) のように送ってください！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )