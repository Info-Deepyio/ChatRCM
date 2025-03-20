import requests
import time
import threading
import json
import datetime
from pymongo import MongoClient

# Bot Configuration
API_TOKEN = "1547814800:qz5gVdxqxhExyUwPmlUM3cK8q6E9yVdgdyuUZJDA"
BASE_URL = 'https://tapi.bale.ai/bot{TOKEN}'

# MongoDB Connection
MONGO_URI = "mongodb://mongo:LdQvOFTnDVjPCDGqCzHNSsPUyqUZBkPq@tramway.proxy.rlwy.net:27166"
client = MongoClient(MONGO_URI)
db = client['bale_bot']
audio_collection = db['audio_files']

# Whitelisted users (usernames without @)
WHITELISTED_USERS = ["zonercm"]  # Add your usernames here

# Persian numeral conversion
def to_persian_numerals(text):
    """Convert English numbers to Persian numbers"""
    persian_nums = {
        '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
        '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
    }
    for en, fa in persian_nums.items():
        text = text.replace(en, fa)
    return text

def get_persian_time():
    """Returns current time in Persian format"""
    now = datetime.datetime.now()
    weekday_map = {
        0: "دوشنبه",     # Monday
        1: "سه‌شنبه",    # Tuesday
        2: "چهارشنبه",   # Wednesday
        3: "پنج‌شنبه",   # Thursday
        4: "جمعه",       # Friday
        5: "شنبه",       # Saturday
        6: "یک‌شنبه"     # Sunday
    }
    
    weekday = weekday_map[now.weekday()]
    date_str = f"{now.year}/{now.month}/{now.day}"
    time_str = f"{now.hour}:{now.minute}:{now.second}"
    
    return f"🗓 {weekday} {to_persian_numerals(date_str)}\n⏰ ساعت {to_persian_numerals(time_str)}"

def get_updates(offset=None):
    """Get updates from Telegram API"""
    url = f'{BASE_URL}/getUpdates'
    params = {'timeout': 30, 'allowed_updates': ['message', 'callback_query']}
    if offset:
        params['offset'] = offset
    response = requests.get(url, params=params)
    return response.json()

def send_message(chat_id, text, reply_markup=None):
    """Send message to Telegram chat"""
    url = f'{BASE_URL}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup
    response = requests.post(url, json=payload)
    return response.json()

def edit_message(chat_id, message_id, text, reply_markup=None):
    """Edit existing message"""
    url = f'{BASE_URL}/editMessageText'
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup
    response = requests.post(url, json=payload)
    return response.json()

def send_audio(chat_id, file_path, caption=None):
    """Send audio file to chat"""
    url = f'{BASE_URL}/sendAudio'
    payload = {'chat_id': chat_id}
    if caption:
        payload['caption'] = caption
    
    files = {'audio': open(file_path, 'rb')}
    response = requests.post(url, data=payload, files=files)
    return response.json()

def create_inline_keyboard():
    """Create inline keyboard with two buttons"""
    keyboard = {
        'inline_keyboard': [
            [
                {'text': 'ارسال فایل صوتی', 'callback_data': 'send_audio'}
            ]
        ]
    }
    return json.dumps(keyboard)

# Dictionary to store state of which chat is waiting for audio
waiting_for_audio = {}

def main():
    print("🤖 ربات فارسی در حال اجرا شدن است...")
    offset = None
    
    while True:
        try:
            updates = get_updates(offset)
            if 'result' in updates and updates['result']:
                for update in updates['result']:
                    offset = update['update_id'] + 1
                    
                    # Handle messages
                    if 'message' in update and 'text' in update['message']:
                        message = update['message']
                        chat_id = message['chat']['id']
                        text = message['text']
                        user = message.get('from', {}).get('username', '')
                        
                        # Check for panel command
                        if text == "پنل" and user in WHITELISTED_USERS:
                            # Send greeting with Persian time
                            greeting = f"🌟 سلام {message.get('from', {}).get('first_name', 'کاربر گرامی')} عزیز!\n\n{get_persian_time()}\n\n⚙️ پنل مدیریت فایل ها:"
                            keyboard = create_inline_keyboard()
                            send_message(chat_id, greeting, keyboard)
                    
                    # Handle callback queries (inline keyboard button clicks)
                    if 'callback_query' in update:
                        callback = update['callback_query']
                        chat_id = callback['message']['chat']['id']
                        message_id = callback['message']['message_id']
                        callback_data = callback['data']
                        user = callback.get('from', {}).get('username', '')
                        
                        if user in WHITELISTED_USERS:
                            if callback_data == 'send_audio':
                                # Ask user to send audio file
                                prompt_text = "🎤 لطفاً فایل صوتی خود را ارسال کنید."
                                edit_message(chat_id, message_id, prompt_text)
                                waiting_for_audio[chat_id] = "waiting_for_audio"
            
            # Listen for audio messages from whitelisted users
            if 'message' in update and 'audio' in update['message']:
                audio_message = update['message']
                chat_id = audio_message['chat']['id']
                audio_file_id = audio_message['audio']['file_id']
                file_name = audio_message['audio']['file_name']
                
                if chat_id in waiting_for_audio and waiting_for_audio[chat_id] == "waiting_for_audio":
                    # Save audio to MongoDB
                    audio_data = {
                        'chat_id': chat_id,
                        'file_id': audio_file_id,
                        'file_name': file_name
                    }
                    audio_collection.insert_one(audio_data)
                    
                    # Send confirmation
                    send_message(chat_id, f"✅ فایل صوتی شما با نام {file_name} ذخیره شد. اکنون می‌توانید آن را برنامه‌ریزی کنید.")
                    
                    # Clear waiting state
                    del waiting_for_audio[chat_id]
            
            time.sleep(1)
            
        except Exception as e:
            print(f"خطا: {str(e)}")
            time.sleep(5)

if __name__ == "__main__":
    main()
