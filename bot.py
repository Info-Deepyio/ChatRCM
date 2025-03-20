import requests
import time
import json
import os
from datetime import datetime
import pymongo
from bson.objectid import ObjectId

# Bot configuration
TOKEN = "7435111550:AAGggKVIoyYQI-UQmpqIyB31VEM6f2sINeY"
API_URL = f"https://api.telegram.org/bot{TOKEN}"
WHITELISTED_USERS = ["zonercm", "user2", "user3"]  # Replace with actual usernames

# MongoDB setup
client = pymongo.MongoClient("mongodb://mongo:kYrkkbAQKdReFyOknupBPTRhRuDlDdja@switchback.proxy.rlwy.net:52220")
db = client["audio_bot_db"]
audio_collection = db["audio_files"]

# Create audio directory
os.makedirs("audio_files", exist_ok=True)

# User states
user_states = {}
last_update_id = 0

# Persian numbers
def to_persian_num(num):
    persian_nums = '۰۱۲۳۴۵۶۷۸۹'
    return ''.join(persian_nums[int(d)] for d in str(num))

# Get current Persian time
def get_persian_time():
    now = datetime.now()
    return f"{to_persian_num(now.hour)}:{to_persian_num(now.minute)}"

# Fast API request function
def send_request(method, data=None):
    url = f"{API_URL}/{method}"
    try:
        if data:
            response = requests.post(url, data=data, timeout=5)
        else:
            response = requests.get(url, timeout=5)
        return response.json()
    except Exception as e:
        print(f"Error in {method}: {e}")
        return {"ok": False}

# Main bot loop
def run_bot():
    global last_update_id
    print("Bot started!")
    
    while True:
        # Get updates with minimal polling time
        updates = send_request(f"getUpdates?offset={last_update_id + 1}&timeout=1")
        
        if updates.get("ok", False) and updates.get("result", []):
            for update in updates["result"]:
                last_update_id = update["update_id"]
                
                # Handle message
                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    user_id = message["from"]["id"]
                    username = message["from"].get("username", "")
                    
                    # Skip if not whitelisted
                    if username not in WHITELISTED_USERS:
                        continue
                    
                    # Handle panel command
                    if "text" in message and message["text"] == "پنل":
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "ارسال فایل صوتی", "callback_data": "audio"}]
                            ]
                        }
                        
                        text = f"""سلام {username}!
⏰ ساعت: {get_persian_time()}
به پنل مدیریت خوش آمدید!"""
                        
                        send_request("sendMessage", {
                            "chat_id": chat_id,
                            "text": text,
                            "reply_markup": json.dumps(keyboard)
                        })
                        
                        # Reset state
                        user_states[user_id] = "normal"
                    
                    # Handle audio message
                    elif user_states.get(user_id) == "waiting_audio":
                        audio_file = None
                        file_id = None
                        
                        # Check for any audio format
                        for audio_type in ["voice", "audio", "document"]:
                            if audio_type in message:
                                audio_file = message[audio_type]
                                file_id = audio_file["file_id"]
                                break
                        
                        if file_id:
                            # Get file info
                            file_info = send_request(f"getFile?file_id={file_id}")
                            
                            if file_info.get("ok", False) and "result" in file_info:
                                file_path = file_info["result"]["file_path"]
                                download_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
                                
                                # Download file
                                try:
                                    audio_content = requests.get(download_url).content
                                    timestamp = int(time.time())
                                    filename = f"{username}_{timestamp}.audio"
                                    filepath = f"audio_files/{filename}"
                                    
                                    with open(filepath, "wb") as f:
                                        f.write(audio_content)
                                    
                                    # Save to MongoDB
                                    audio_data = {
                                        "user_id": user_id,
                                        "username": username,
                                        "filepath": filepath,
                                        "timestamp": timestamp,
                                        "scheduled": False
                                    }
                                    
                                    result = audio_collection.insert_one(audio_data)
                                    audio_id = str(result.inserted_id)
                                    
                                    # Send confirmation with scheduling button
                                    keyboard = {
                                        "inline_keyboard": [
                                            [{"text": "زمانبندی پخش", "callback_data": f"schedule_{audio_id}"}]
                                        ]
                                    }
                                    
                                    send_request("sendMessage", {
                                        "chat_id": chat_id,
                                        "text": "✅ فایل صوتی با موفقیت ذخیره شد!",
                                        "reply_markup": json.dumps(keyboard)
                                    })
                                    
                                    # Reset state
                                    user_states[user_id] = "normal"
                                except Exception as e:
                                    print(f"Error downloading file: {e}")
                                    send_request("sendMessage", {
                                        "chat_id": chat_id,
                                        "text": "❌ خطا در ذخیره فایل صوتی!"
                                    })
                    
                    # Handle scheduling time input
                    elif user_states.get(user_id, "").startswith("scheduling_"):
                        if "text" in message and message["text"].isdigit():
                            audio_id = user_states[user_id].split("_")[1]
                            minutes = int(message["text"])
                            
                            # Update MongoDB
                            audio_collection.update_one(
                                {"_id": ObjectId(audio_id)},
                                {"$set": {
                                    "scheduled": True,
                                    "schedule_time": datetime.now(),
                                    "minutes": minutes
                                }}
                            )
                            
                            send_request("sendMessage", {
                                "chat_id": chat_id,
                                "text": f"✅ فایل صوتی برای پخش در {to_persian_num(minutes)} دقیقه دیگر زمانبندی شد."
                            })
                            
                            # Reset state
                            user_states[user_id] = "normal"
                
                # Handle callback queries (button clicks)
                elif "callback_query" in update:
                    query = update["callback_query"]
                    query_id = query["id"]
                    chat_id = query["message"]["chat"]["id"]
                    message_id = query["message"]["message_id"]
                    user_id = query["from"]["id"]
                    data = query["data"]
                    
                    # Audio button clicked
                    if data == "audio":
                        # Edit message
                        send_request("editMessageText", {
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": "🎵 لطفاً فایل صوتی خود را ارسال کنید."
                        })
                        
                        # Set state to waiting for audio
                        user_states[user_id] = "waiting_audio"
                    
                    # Schedule button clicked
                    elif data.startswith("schedule_"):
                        audio_id = data.split("_")[1]
                        
                        # Edit message
                        send_request("editMessageText", {
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": "⏰ لطفاً زمان پخش را به دقیقه وارد کنید (مثال: 5)"
                        })
                        
                        # Set state to waiting for schedule time
                        user_states[user_id] = f"scheduling_{audio_id}"
                    
                    # Answer callback query to remove loading state
                    send_request("answerCallbackQuery", {
                        "callback_query_id": query_id
                    })
        
        # Ultra short sleep for maximum responsiveness
        time.sleep(0.01)

if __name__ == "__main__":
    run_bot()
