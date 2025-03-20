import requests
import random
import string
import time
from datetime import datetime
from pymongo import MongoClient
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configurations
TOKEN = "812616487:cRPquvMfuFLC3rOWiHMu3yay8WCu8E1iX6CfWF1c"
MONGO_URI = "mongodb://mongo:kYrkkbAQKdReFyOknupBPTRhRuDlDdja@switchback.proxy.rlwy.net:52220"
DB_NAME = "uploader_bot"
WHITELIST = ["zonercm", "your_username_here"]  # Add whitelisted usernames

# Initialize MongoDB with connection pooling
client = MongoClient(MONGO_URI, maxPoolSize=50)
db = client[DB_NAME]
files_collection = db["files"]

# Create indexes for better performance
files_collection.create_index("link_id")

# Telegram API URL
API_URL = f"https://tapi.bale.ai/bot{TOKEN}/"

# Cache frequently used data
link_cache = {}
session = requests.Session()

def send_request(method, data):
    """Send requests to Telegram API with session reuse"""
    url = API_URL + method
    try:
        response = session.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"API request error: {e}")
        return {"ok": False, "error": str(e)}

def generate_link():
    """Generate a random link ID"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=8))

def get_persian_time():
    """Get Persian time"""
    now = datetime.now()
    return now.strftime("%Y/%m/%d - %H:%M")

def escape_markdown(text):
    """Escape Markdown for Telegram compatibility"""
    escape_chars = "_*[]()~`>#+-=|{}.!<>"
    return "".join(f"\\{char}" if char in escape_chars else char for char in text)

def send_panel(chat_id):
    """Send Persian panel with date/time"""
    text = f"🌟 *خوش آمدید\!* 🌟\n\n📆 تاریخ: `{get_persian_time()}`\n📂 برای آپلود فایل، دکمه زیر را فشار دهید."
    keyboard = {"inline_keyboard": [[{"text": "📤 آپلود فایل", "callback_data": "upload_file"}]]}
    send_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "reply_markup": keyboard
    })

def handle_file_upload(chat_id, file_id, file_name):
    """Store file in MongoDB and instantly send the download link with like & download buttons"""
    link_id = generate_link()
    files_collection.insert_one({
        "link_id": link_id, 
        "file_id": file_id, 
        "file_name": file_name, 
        "likes": 0, 
        "downloads": 0,
        "created_at": datetime.now()
    })

    # Add to cache
    link_cache[link_id] = {"file_id": file_id, "likes": 0, "downloads": 0}

    start_link = f"/start {link_id}"
    text = f"✅ فایل شما ذخیره شد\!\n🔗 لینک دریافت:\n`{escape_markdown(start_link)}`"
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "❤️ 0", "callback_data": f"like_{link_id}"}],
            [{"text": "📥 0 دریافت", "callback_data": f"download_{link_id}"}]
        ]
    }

    send_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "reply_markup": keyboard
    })

def get_file_data(link_id):
    """Get file data from cache or database"""
    if link_id in link_cache:
        return link_cache[link_id]
    
    file_data = files_collection.find_one({"link_id": link_id})
    if file_data:
        # Cache the result
        link_cache[link_id] = {
            "file_id": file_data["file_id"], 
            "likes": file_data["likes"], 
            "downloads": file_data["downloads"]
        }
        return link_cache[link_id]
    
    return None

def send_stored_file(chat_id, link_id):
    """Retrieve and instantly send stored file, updating download count"""
    file_data = get_file_data(link_id)
    
    if file_data:
        # Update download count
        new_download_count = file_data["downloads"] + 1
        file_data["downloads"] = new_download_count
        
        files_collection.update_one(
            {"link_id": link_id}, 
            {"$set": {"downloads": new_download_count}}
        )

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

def handle_updates(updates):
    """Process multiple updates efficiently"""
    for update in updates:
        try:
            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                username = msg["from"].get("username", "")

                if "text" in msg:
                    text = msg["text"]
                    
                    if text == "پنل" and username in WHITELIST:
                        send_panel(chat_id)

                    elif text.startswith("/start "):
                        parts = text.split()
                        if len(parts) > 1:
                            link_id = parts[1]
                            send_stored_file(chat_id, link_id)

                elif "document" in msg:
                    file_id = msg["document"]["file_id"]
                    file_name = msg["document"].get("file_name", "unnamed_file")
                    handle_file_upload(chat_id, file_id, file_name)
            
            elif "callback_query" in update:
                handle_callback(update["callback_query"])
        except Exception as e:
            logger.error(f"Error handling update: {e}")

# Polling mechanism
def start_bot():
    """Start bot with optimized long polling"""
    offset = 0
    while True:
        try:
            updates = send_request("getUpdates", {
                "offset": offset, 
                "timeout": 30,
                "allowed_updates": ["message", "callback_query"]  # Only get what we need
            })
            
            if "result" in updates and updates["result"]:
                handle_updates(updates["result"])
                offset = updates["result"][-1]["update_id"] + 1
            
            # Periodic cache cleanup
            if len(link_cache) > 1000:  # Arbitrary limit
                link_cache.clear()
                
        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
            time.sleep(5)  # Wait a bit before retrying

# Start the bot
if __name__ == "__main__":
    logger.info("Bot started")
    start_bot()
