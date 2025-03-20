import requests
import random
import string
import time
from datetime import datetime
from pymongo import MongoClient

# Configurations
TOKEN = "812616487:cRPquvMfuFLC3rOWiHMu3yay8WCu8E1iX6CfWF1c"
MONGO_URI = "mongodb://mongo:kYrkkbAQKdReFyOknupBPTRhRuDlDdja@switchback.proxy.rlwy.net:52220"
DB_NAME = "uploader_bot"
WHITELIST = ["zonercm", "your_username_here"]  # Add whitelisted usernames

# Initialize MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
files_collection = db["files"]

# Telegram API URL
API_URL = f"https://tapi.bale.ai/bot{TOKEN}/"

def send_request(method, data):
    """Send requests to Telegram API"""
    url = API_URL + method
    return requests.post(url, json=data).json()

def generate_link():
    """Generate a random link ID"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_persian_time():
    """Get Persian time"""
    now = datetime.now()
    return now.strftime("%Y/%m/%d - %H:%M")

def send_panel(chat_id):
    """Send Persian panel with date/time"""
    text = f"🌟 *خوش آمدید!* 🌟\n\n📆 تاریخ: `{get_persian_time()}`\n📂 برای آپلود فایل، دکمه زیر را فشار دهید."
    keyboard = {"inline_keyboard": [[{"text": "📤 آپلود فایل", "callback_data": "upload_file"}]]}
    send_request("sendMessage", {
        "chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": keyboard
    })

def handle_file_upload(chat_id, file_id, file_name):
    """Store file in MongoDB and instantly send the download link with like & download buttons"""
    link_id = generate_link()
    files_collection.insert_one({"link_id": link_id, "file_id": file_id, "file_name": file_name, "likes": 0, "downloads": 0})

    start_link = f"/start {link_id}"
    text = f"✅ فایل شما ذخیره شد!\n🔗 لینک دریافت:\n```\n{start_link}\n```"
    
    keyboard = {
        "inline_keyboard": [
            [{"text": f"❤️ 0", "callback_data": f"like_{link_id}"}],
            [{"text": f"📥 0 دریافت", "callback_data": f"download_{link_id}"}]
        ]
    }

    send_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    })

def send_stored_file(chat_id, link_id):
    """Retrieve and instantly send stored file, updating download count"""
    file_data = files_collection.find_one({"link_id": link_id})
    
    if file_data:
        # Update download count
        new_download_count = file_data["downloads"] + 1
        files_collection.update_one({"link_id": link_id}, {"$set": {"downloads": new_download_count}})

        # Send file with updated buttons
        keyboard = {
            "inline_keyboard": [
                [{"text": f"❤️ {file_data['likes']}", "callback_data": f"like_{link_id}"}],
                [{"text": f"📥 {new_download_count} دریافت", "callback_data": f"download_{link_id}"}]
            ]
        }

        send_request("sendDocument", {
            "chat_id": chat_id,
            "document": file_data["file_id"],
            "reply_markup": keyboard
        })
    else:
        send_request("sendMessage", {
            "chat_id": chat_id,
            "text": "❌ لینک نامعتبر است یا فایل حذف شده است."
        })

def handle_callback(query):
    """Handle button clicks for likes & downloads"""
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    data = query["data"]

    if data.startswith("like_"):
        link_id = data.split("like_")[1]
        file_data = files_collection.find_one({"link_id": link_id})

        if file_data:
            new_likes = file_data["likes"] + 1
            files_collection.update_one({"link_id": link_id}, {"$set": {"likes": new_likes}})
            new_text = f"❤️ {new_likes}"
            send_request("editMessageReplyMarkup", {
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": new_text, "callback_data": f"like_{link_id}"}],
                        [{"text": f"📥 {file_data['downloads']} دریافت", "callback_data": f"download_{link_id}"}]
                    ]
                }
            })

    elif data.startswith("download_"):
        link_id = data.split("download_")[1]
        file_data = files_collection.find_one({"link_id": link_id})

        if file_data:
            new_downloads = file_data["downloads"]
            new_text = f"📥 {new_downloads} دریافت"
            send_request("editMessageReplyMarkup", {
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": f"❤️ {file_data['likes']}", "callback_data": f"like_{link_id}"}],
                        [{"text": new_text, "callback_data": f"download_{link_id}"}]
                    ]
                }
            })

def handle_updates(update):
    """Main update handler"""
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        username = msg["from"].get("username", "")

        if "text" in msg:
            text = msg["text"]
            
            if text == "پنل" and username in WHITELIST:
                send_panel(chat_id)

            elif text.startswith("/start "):
                link_id = text.split("/start ")[1]
                send_stored_file(chat_id, link_id)

        elif "document" in msg:
            file_id = msg["document"]["file_id"]
            file_name = msg["document"]["file_name"]
            handle_file_upload(chat_id, file_id, file_name)
    
    elif "callback_query" in update:
        handle_callback(update["callback_query"])

# Polling mechanism
def start_bot():
    """Start bot with long polling"""
    offset = 0
    while True:
        updates = send_request("getUpdates", {"offset": offset, "timeout": 30})
        if "result" in updates:
            for update in updates["result"]:
                offset = update["update_id"] + 1
                handle_updates(update)
        time.sleep(1)

# Start the bot
if __name__ == "__main__":
    start_bot()
