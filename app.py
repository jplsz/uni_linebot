from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import json
from datetime import datetime
import os

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

# 今日のクエストを抽出
def get_todays_quests(task_list, max_tasks=3):
    today = datetime.now().date()
    upcoming_tasks = []

    for task in task_list:
        try:
            deadline = datetime.strptime(task["deadline"], "%Y-%m-%d").date()
            days_left = (deadline - today).days
            if days_left >= 0:
                upcoming_tasks.append((days_left, task))
        except Exception as e:
            continue

    upcoming_tasks.sort(key=lambda x: x[0])
    return [t[1] for t in upcoming_tasks[:max_tasks]]

# === 達成記録の保存処理 ===
def record_task_completion(subject, title):
    today = datetime.now().strftime("%Y-%m-%d")
    done_file = "done_log.json"

    # ログファイルが存在しなければ初期化
    if not os.path.exists(done_file):
        done_log = {}
    else:
        with open(done_file, "r", encoding="utf-8") as f:
            done_log = json.load(f)

    # 新規日付なら初期化
    if today not in done_log:
        done_log[today] = []

    # 重複防止
    if not any(t["subject"] == subject and t["title"] == title for t in done_log[today]):
        done_log[today].append({
            "subject": subject,
            "title": title,
            "completed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        })

        with open(done_file, "w", encoding="utf-8") as f:
            json.dump(done_log, f, indent=2, ensure_ascii=False)
        return True # 成功
    else:
        return False # 既に記録済み

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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()

    if text.startswith("☑️"):
        # 例：☑️心理学A：第3回 講義視聴
        try:
            rest = text[1:].strip()
            subject, title = rest.split(":", 1)
            success = record_task_completion(subject.strip(), title.strip())
            if success:
                reply = f"📝 記録しました！\n{subject.strip()} : {title.strip()}"
            else:
                reply = "⚠️ すでに記録済みです。"
        except Exception as e:
            reply = "❌️ 記録形式が正しくありません。\n例：☑️福祉心理学：第3回"
    else:
        reply = "📩 クエスト達成を記録したい場合は\n☑️心理学A：第3回 のように送ってください！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )