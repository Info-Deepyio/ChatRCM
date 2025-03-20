import requests
import threading
import json
import datetime
import time

# Bot Configuration
API_TOKEN = "1547814800:qz5gVdxqxhExyUwPmlUM3cK8q6E9yVdgdyuUZJDA"
BASE_URL = f'https://tapi.bale.ai/bot{API_TOKEN}'

# Whitelisted users (usernames without @)
WHITELISTED_USERS = ["zonercm"]

# File paths for automation
CROSS_FILE_PATH = 'cross_audio.m4a'
MADE_FILE_PATH = 'Made.mp3'

# Scheduled tasks dictionary
scheduled_tasks = {}

def to_persian_numerals(text):
    persian_nums = {'0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
                    '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'}
    return ''.join(persian_nums.get(ch, ch) for ch in text)

def from_persian_numerals(text):
    persian_nums = {'۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
                    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9'}
    return ''.join(persian_nums.get(ch, ch) for ch in text)

def get_persian_time():
    now = datetime.datetime.now()
    weekday_map = {
        0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه",
        3: "پنج‌شنبه", 4: "جمعه", 5: "شنبه", 6: "یک‌شنبه"
    }
    return f"🗓 {weekday_map[now.weekday()]} {to_persian_numerals(f'{now.year}/{now.month}/{now.day}')}\n⏰ ساعت {to_persian_numerals(f'{now.hour}:{now.minute}')}"

def get_updates(offset=None):
    url = f'{BASE_URL}/getUpdates'
    params = {'timeout': 0, 'allowed_updates': ['message', 'callback_query']}
    if offset:
        params['offset'] = offset
    return requests.get(url, params=params).json()

def send_message(chat_id, text, reply_markup=None):
    url = f'{BASE_URL}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    requests.post(url, json=payload)

def edit_message(chat_id, message_id, text, reply_markup=None):
    url = f'{BASE_URL}/editMessageText'
    payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    requests.post(url, json=payload)

def send_audio(chat_id, file_path, caption=None):
    url = f'{BASE_URL}/sendAudio'
    payload = {'chat_id': chat_id}
    if caption:
        payload['caption'] = caption
    with open(file_path, 'rb') as audio_file:
        files = {'audio': audio_file}
        requests.post(url, data=payload, files=files)

def schedule_audio_send(chat_id, minutes, file_path, task_id):
    def send_scheduled_audio():
        send_audio(chat_id, file_path, caption="✅ فایل برنامه‌ریزی شده شما")
        scheduled_tasks.pop(task_id, None)
    
    timer = threading.Timer(int(minutes) * 60, send_scheduled_audio)
    timer.daemon = True
    timer.start()
    scheduled_tasks[task_id] = timer

def create_inline_keyboard():
    return json.dumps({
        'inline_keyboard': [
            [{'text': '✖️ Cross', 'callback_data': 'cross'},
             {'text': '🕋 Made', 'callback_data': 'made'}]
        ]
    })

def main():
    print("🤖 ربات فارسی در حال اجرا است...")
    offset = None
    waiting_for_time = {}

    while True:
        try:
            updates = get_updates(offset)
            if 'result' in updates and updates['result']:
                for update in updates['result']:
                    offset = update['update_id'] + 1

                    if 'message' in update and 'text' in update['message']:
                        message = update['message']
                        chat_id = message['chat']['id']
                        text = message['text']
                        user = message.get('from', {}).get('username', '')

                        if chat_id in waiting_for_time and user in WHITELISTED_USERS:
                            try:
                                minutes = int(from_persian_numerals(text))
                                callback_type = waiting_for_time.pop(chat_id)
                                file_path = CROSS_FILE_PATH if callback_type == 'cross' else MADE_FILE_PATH
                                task_id = f"{chat_id}_{int(time.time())}"

                                schedule_audio_send(chat_id, minutes, file_path, task_id)
                                send_message(chat_id, f"✅ فایل {'Cross' if callback_type == 'cross' else 'Made'} برای {to_persian_numerals(str(minutes))} دقیقه دیگر برنامه‌ریزی شد.")
                            except ValueError:
                                send_message(chat_id, "❌ لطفاً یک عدد معتبر وارد کنید.")

                        elif text == "پنل" and user in WHITELISTED_USERS:
                            greeting = f"🌟 سلام {message.get('from', {}).get('first_name', 'کاربر گرامی')} عزیز!\n\n{get_persian_time()}\n\n⚙️ پنل مدیریت فایل ها:"
                            send_message(chat_id, greeting, create_inline_keyboard())

                    if 'callback_query' in update:
                        callback = update['callback_query']
                        chat_id = callback['message']['chat']['id']
                        message_id = callback['message']['message_id']
                        callback_data = callback['data']
                        user = callback.get('from', {}).get('username', '')

                        if user in WHITELISTED_USERS:
                            if callback_data in ['cross', 'made']:
                                waiting_for_time[chat_id] = callback_data
                                edit_message(chat_id, message_id, f"⏱ لطفاً مدت زمان به دقیقه برای ارسال فایل {callback_data} را وارد کنید:")
        except Exception as e:
            print(f"⚠️ خطا: {str(e)}")

if __name__ == "__main__":
    main()
