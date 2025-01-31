import os
import re
import logging
from collections import Counter
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext, CommandHandler
from dotenv import load_dotenv
import openai
import asyncio

# ✅ 讀取 .env 檔案
load_dotenv()

# ✅ 設定環境變數
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))  # 群組 ID 必須是整數
SUMMARY_CHAT_ID = int(os.getenv("SUMMARY_CHAT_ID", "0"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ✅ 設定 OpenAI API
openai.api_key = OPENAI_API_KEY

# ✅ 設定日誌
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logging.info("📡 Bot 啟動中...")

# ✅ 儲存當日訊息
messages = []
word_counter = Counter()

def extract_tweet_info(text):
    """解析 X（Twitter）轉發的訊息"""
    match = re.search(r"(.+?) (@\w+) - (https?://\S+)", text)
    if match:
        content, username, link = match.groups()
        summary = summarize_content(content)  # 生成標題
        return f"{summary} — {username} 🔗 ({link})", content
    return None, None

def summarize_content(content):
    """簡單提取標題（10 字內）"""
    words = content.split()[:10]
    return " ".join(words)

async def handle_message(update: Update, context: CallbackContext):
    """處理所有來自群組的訊息"""
    text = update.message.text
    username = update.message.from_user.username or update.message.from_user.first_name
    chat_id = update.message.chat_id

    logging.info(f"📩 收到來自 {username} 的訊息：{text}")

    # 確保訊息來自指定的群組
    if chat_id == GROUP_ID:
        summary, content = extract_tweet_info(text)
        if summary:
            messages.append(summary)
            update_word_counter(content)
            logging.info(f"✅ 訊息已存入待摘要列表")

def update_word_counter(content):
    """統計重複出現的關鍵字"""
    common_keywords = ["AI", "比特幣", "加密", "ETH", "BTC", "Layer2"]  # 你可以修改這些關鍵字
    words = content.split()
    for word in words:
        if word in common_keywords:
            word_counter[word] += 1

def generate_summary(text):
    """使用 OpenAI API 生成摘要"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個專業的新聞摘要助手，請用簡潔的語言概括當日內容。"},
                {"role": "user", "content": f"請為以下內容生成一個 50 字內的簡短摘要：\n{text}"}
            ]
        )
        summary = response["choices"][0]["message"]["content"].strip()
        return summary
    except Exception as e:
        logging.error(f"OpenAI API 發生錯誤: {e}")
        return "（摘要生成失敗）"

async def send_summary(context: CallbackContext):
    """發送每日總結"""
    logging.info("⏰ 8PM 到了，準備發送摘要...")

    if messages:
        summary_text = "\n".join([f"{i+1}. {msg}" for i, msg in enumerate(messages)])

        # 生成 AI 總結
        ai_summary = generate_summary(summary_text)

        # 計算關鍵字統計
        total_messages = len(messages)
        most_common_words = ", ".join([f"{word} 提到 {count} 次" for word, count in word_counter.most_common(3)])

        summary_message = (
            f"📢 {datetime.now().strftime('%Y-%m-%d')} 今日摘要\n\n"
            f"{summary_text}\n\n"
            f"▬▬\n\n"
            f"• 總共 {total_messages} 則訊息，重複關鍵字為 {most_common_words}\n\n"
            f"📌 AI 總結: {ai_summary}"
        )

        await context.bot.send_message(chat_id=SUMMARY_CHAT_ID, text=summary_message)
        logging.info("✅ 今日摘要發送成功！")

        # 清空記錄
        messages.clear()
        word_counter.clear()
    else:
        await context.bot.send_message(chat_id=SUMMARY_CHAT_ID, text="📢 今日無新訊息。")
        logging.info("⚠️ 今日沒有可發送的訊息")

async def test_summary(update: Update, context: CallbackContext):
    """手動測試摘要"""
    await send_summary(context)

def main():
    """啟動 Telegram Bot"""
    app = Application.builder().token(BOT_TOKEN).build()

    # ✅ 新增 `/testsummary` 指令，手動觸發摘要
    app.add_handler(CommandHandler("testsummary", test_summary))

    # ✅ 監聽群組訊息（不限制發送者）
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & filters.TEXT, handle_message))

    # ✅ 設置定時發送摘要
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: app.create_task(send_summary(None)), "cron", hour=20, minute=0)
    scheduler.start()

    logging.info("🚀 Bot 開始監聽群組內的所有訊息...")
    app.run_polling()

if __name__ == "__main__":
    main()