import requests
import random
import string
import time
from datetime import datetime
from pymongo import MongoClient
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
likes_collection = db["likes"]  # New collection to track user likes

# Create indexes for better performance
files_collection.create_index("link_id")
likes_collection.create_index([("user_id", 1), ("link_id", 1)], unique=True)

# Telegram API URL
API_URL = f"https://tapi.bale.ai/bot{TOKEN}/"

# Cache frequently used data
link_cache = {}
session = requests.Session()

def send_request(method, data):
    """Send requests to Telegram API with session reuse"""
    url = API_URL + method
    try:
        return session.post(url, json=data, timeout=10).json()
    except Exception as e:
        logger.error(f"API request error: {e}")
        return {"ok": False, "error": str(e)}

def generate_link():
    """Generate a random link ID"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

def get_persian_time():
    """Get Persian time"""
    now = datetime.now()
    return now.strftime("%Y/%m/%d - %H:%M")

def send_panel(chat_id):
    """Send Persian panel with date/time and status"""
    # Get total stats
    total_files = files_collection.count_documents({})
    total_downloads = sum(doc["downloads"] for doc in files_collection.find({}, {"downloads": 1}))
    total_likes = sum(doc["likes"] for doc in files_collection.find({}, {"likes": 1}))
    
    text = f"🌟 *پنل مدیریت* 🌟\n\n" \
           f"📆 تاریخ و زمان: `{get_persian_time()}`\n\n" \
           f"📊 *آمار کلی*:\n" \
           f"📁 تعداد فایل‌ها: `{total_files}`\n" \
           f"📥 تعداد دانلودها: `{total_downloads}`\n" \
           f"❤️ تعداد لایک‌ها: `{total_likes}`\n\n" \
           f"برای آپلود فایل جدید، دکمه زیر را فشار دهید:"
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "📤 آپلود فایل", "callback_data": "upload_file"}]
        ]
    }

    send_request("sendMessage", {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "Markdown", 
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
    text = f"✅ فایل شما ذخیره شد!\n🔗 لینک دریافت:\n```\n{start_link}\n```"
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "❤️ 0", "callback_data": f"like_{link_id}"}],
            [{"text": f"📥 تعداد دانلود ها: 0", "callback_data": f"download_{link_id}"}]
        ]
    }

    send_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
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

        # Send file without inline keyboard in the document
        send_request("sendDocument", {
            "chat_id": chat_id,
            "document": file_data["file_id"]
        })
        
        # Send a separate message with buttons
        keyboard = {
            "inline_keyboard": [
                [{"text": f"❤️ {file_data['likes']}", "callback_data": f"like_{link_id}"}],
                [{"text": f"📥 تعداد دانلود ها: {new_download_count}", "callback_data": f"download_{link_id}"}]
            ]
        }
        
        send_request("sendMessage", {
            "chat_id": chat_id,
            "text": "📥 *فایل با موفقیت دانلود شد*\nمی‌توانید با دکمه‌های زیر فایل را لایک کرده یا مجدداً دانلود کنید:",
            "parse_mode": "Markdown",
            "reply_markup": keyboard
        })
    else:
        send_request("sendMessage", {
            "chat_id": chat_id,
            "text": "❌ لینک نامعتبر است یا فایل حذف شده است."
        })

def handle_callback(query):
    """Handle button clicks for likes & downloads with anti-spam protection"""
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    callback_id = query["id"]
    data = query["data"]
    user_id = query["from"]["id"]

    # First acknowledge the callback to prevent timeout
    send_request("answerCallbackQuery", {"callback_query_id": callback_id})

    if data.startswith("like_"):
        link_id = data.split("_")[1]
        file_data = files_collection.find_one({"link_id": link_id})

        if file_data:
            # Check if user already liked this file
            existing_like = likes_collection.find_one({"user_id": user_id, "link_id": link_id})
            
            if not existing_like:
                # Add like record
                likes_collection.insert_one({"user_id": user_id, "link_id": link_id, "created_at": datetime.now()})
                
                # Update like count
                new_likes = file_data["likes"] + 1
                files_collection.update_one({"link_id": link_id}, {"$set": {"likes": new_likes}})
                
                # Update cache
                if link_id in link_cache:
                    link_cache[link_id]["likes"] = new_likes
                
                # Update the button text
                send_request("editMessageReplyMarkup", {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reply_markup": {
                        "inline_keyboard": [
                            [{"text": f"❤️ {new_likes}", "callback_data": f"like_{link_id}"}],
                            [{"text": f"📥 تعداد دانلود ها: {file_data['downloads']}", "callback_data": f"download_{link_id}"}]
                        ]
                    }
                })
                
                # Notify user their like was counted
                send_request("answerCallbackQuery", {
                    "callback_query_id": callback_id,
                    "text": "❤️ لایک شما ثبت شد!",
                    "show_alert": False
                })
            else:
                # Notify user they already liked this file
                send_request("answerCallbackQuery", {
                    "callback_query_id": callback_id,
                    "text": "⚠️ شما قبلاً این فایل را لایک کرده‌اید!",
                    "show_alert": True
                })
    
    elif data.startswith("download_"):
        link_id = data.split("_")[1]
        send_stored_file(chat_id, link_id)
    
    elif data == "upload_file":
        send_request("sendMessage", {
            "chat_id": chat_id,
            "text": "📤 لطفاً فایل خود را برای آپلود ارسال کنید."
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
                    elif text.startswith("/start"):
                        parts = text.split()
                        if len(parts) > 1:
                            link_id = parts[1]
                            send_stored_file(chat_id, link_id)
                        else:
                            # Welcome message for new users
                            welcome_text = (
                                "🌟 *به ربات آپلودر خوش آمدید* 🌟\n\n"
                                "با این ربات می‌توانید فایل‌های خود را آپلود کرده و "
                                "لینک دانلود دریافت کنید.\n\n"
                                "📤 برای شروع، فایل خود را ارسال کنید."
                            )
                            send_request("sendMessage", {
                                "chat_id": chat_id,
                                "text": welcome_text,
                                "parse_mode": "Markdown"
                            })

                elif "document" in msg:
                    file_id = msg["document"]["file_id"]
                    file_name = msg["document"].get("file_name", "unnamed_file")
                    handle_file_upload(chat_id, file_id, file_name)
            
            elif "callback_query" in update:
                handle_callback(update["callback_query"])
        except Exception as e:
            logger.error(f"Error handling update: {e}")
            try:
                # Notify admin of error
                if "message" in update:
                    error_msg = f"❌ *خطا*: `{str(e)}`"
                    for admin in WHITELIST:
                        send_request("sendMessage", {
                            "chat_id": admin,
                            "text": error_msg,
                            "parse_mode": "Markdown"
                        })
            except:
                pass

def start_bot():
    """Start bot with optimized long polling"""
    offset = 0
    # Notify admins on startup
    startup_msg = f"🚀 *ربات آپلودر راه‌اندازی شد*\n📆 {get_persian_time()}"
    for admin in WHITELIST:
        try:
            send_request("sendMessage", {
                "chat_id": admin,
                "text": startup_msg,
                "parse_mode": "Markdown"
            })
        except:
            pass
            
    logger.info("Bot started")
    
    while True:
        try:
            updates = send_request("getUpdates", {"offset": offset, "timeout": 30})
            if "result" in updates and updates["result"]:
                handle_updates(updates["result"])
                offset = updates["result"][-1]["update_id"] + 1
            time.sleep(0.5)  # Smaller delay for better responsiveness
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(5)  # Wait before retry on error

if __name__ == "__main__":
    start_bot()
