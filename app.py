from flask import Flask, request
from linebot import LineBotApi
from linebot.models import TextSendMessage
import json
from datetime import datetime
import os

app = Flask(__name__)

# LINE Botの設定（トークンは環境変数または直接記述でも可）
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)

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
            message += f"📘 {q['subject']} | {q['title']} (締切：{q['deadline']})\n"

    # LINEにPush送信
    line_bot_api.push_message(
        USER_ID,
        TextSendMessage(text=message)
    )

    return "OK", 200