import requests
import time
import json
from datetime import datetime
from pymongo import MongoClient

# Telegram Bot API Token
API_TOKEN = '1160037511:LpWEJYm4o6Jw33kEFiYXahNwdWPoHASdsIgRLVeB'

# MongoDB Connection (Update with your MongoDB URI)
mongo_client = MongoClient('')
db = mongo_client['persian_uploader_bot']
users_collection = db['users']
files_collection = db['files']
text_collection = db['texts']
images_collection = db['images']

# Channel UID (replace with your channel's actual ID)
CHANNEL_UID = 5272323810

# Whitelisted Usernames (literal list)
WHITELISTED_USERNAMES = ['zonercm', 'id_hormoz', 'user3']

# Function to get Iran's local date and time
def get_iran_time():
    iran_time = datetime.now()
    iran_time = iran_time.strftime("%Y-%m-%d %H:%M:%S")
    return iran_time

# Function to send a message
def send_message(chat_id, text, reply_markup=None):
    url = f'https://api.telegram.org/bot{API_TOKEN}/sendMessage'
    params = {
        'chat_id': chat_id,
        'text': text,
        'reply_markup': reply_markup,
    }
    response = requests.post(url, data=params)

# Function to get user information
def get_user_info(user_id):
    url = f'https://api.telegram.org/bot{API_TOKEN}/getChatMember'
    params = {
        'chat_id': CHANNEL_UID,
        'user_id': user_id
    }
    response = requests.get(url, params=params)
    return response.json()

# Function to create an inline keyboard
def create_inline_keyboard(buttons):
    keyboard = {
        'inline_keyboard': buttons
    }
    return json.dumps(keyboard)

# Greet the user and check if they joined the channel
def greet_user(update):
    user_id = update['message']['from']['id']
    user_name = update['message']['from'].get('first_name', 'User')
    iran_time = get_iran_time()

    # Check if the user is in the channel
    user_info = get_user_info(user_id)
    if user_info['result']['status'] != 'member':
        text = f"سلام {user_name}! \n\nTo proceed, please join our channel first. 🌐"
        keyboard = create_inline_keyboard([
            [{'text': 'Join Channel', 'url': f'https://t.me/{CHANNEL_UID}'}],
            [{'text': 'Check If Joined', 'callback_data': 'check_join'}]
        ])
        send_message(user_id, text, keyboard)
        return

    text = f"سلام {user_name}! \n\nCurrent Iran Date & Time: {iran_time}"
    send_message(user_id, text)

# Callback query handler for checking if the user joined
def check_join(update):
    query_id = update['callback_query']['id']
    user_id = update['callback_query']['from']['id']

    user_info = get_user_info(user_id)
    if user_info['result']['status'] == 'member':
        send_message(user_id, "You have joined the channel! ✅")
        # Handle the user's previous command if needed
    else:
        send_message(user_id, "Please join the channel first. 🌐")
        send_message(user_id, f"Click here to join: https://t.me/{CHANNEL_UID}")

# Handle admin panel
def admin_panel(update):
    user_id = update['message']['from']['id']
    user_name = update['message']['from'].get('first_name', 'Admin')
    iran_time = get_iran_time()

    if update['message']['from']['username'] not in WHITELISTED_USERNAMES:
        send_message(user_id, "You're not authorized to access the admin panel. ❌")
        return

    text = f"سلام {user_name}!\n\nAdmin Panel\n\nCurrent Iran Date & Time: {iran_time}"
    keyboard = create_inline_keyboard([
        [{'text': 'Upload File', 'callback_data': 'upload_file'}],
        [{'text': 'Upload Text', 'callback_data': 'upload_text'}],
        [{'text': 'Send Message to All Users', 'callback_data': 'send_message'}],
        [{'text': 'Send Image to All Users', 'callback_data': 'send_image'}]
    ])
    send_message(user_id, text, keyboard)

# Handle uploading files
def upload_file(update):
    user_id = update['callback_query']['from']['id']
    send_message(user_id, "Please send the file you want to upload. 📂")

# Handle file saving and generating /start link
def save_file(update):
    file_id = update['message']['document']['file_id']
    file_name = update['message']['document']['file_name']
    file_info_url = f'https://api.telegram.org/bot{API_TOKEN}/getFile'
    file_info_params = {
        'file_id': file_id
    }
    file_info = requests.get(file_info_url, params=file_info_params).json()
    file_path = file_info['result']['file_path']
    file_url = f'https://api.telegram.org/file/bot{API_TOKEN}/{file_path}'

    # Save file URL to MongoDB
    random_code = 'RANDOMCODE'  # Generate a random code as per your requirement
    files_collection.insert_one({'random_code': random_code, 'file_url': file_url})

    # Send the /start link to the admin
    send_message(user_id, f'File saved! The link to share is: /start {random_code}')

# Handle uploading text
def upload_text(update):
    user_id = update['callback_query']['from']['id']
    send_message(user_id, "Please send the text you want to upload. 📑")

# Handle saving and generating text link
def save_text(update):
    text = update['message']['text']
    random_code = 'RANDOMCODE'  # Generate a random code as per your requirement
    text_collection.insert_one({'random_code': random_code, 'text': text})

    send_message(update['message']['from']['id'], f'Text saved! The link to share is: /start {random_code}')

# Handle sending message to all users
def send_message_to_all_users(update):
    user_id = update['callback_query']['from']['id']
    message = update['message']['text']

    # Get all users from the database and send them the message
    users = users_collection.find()
    for user in users:
        send_message(user['user_id'], message)

# Handle sending image to all users
def send_image_to_all_users(update):
    user_id = update['callback_query']['from']['id']
    file_id = update['message']['photo'][0]['file_id']
    caption = update['message'].get('caption', '')

    # Get all users from the database and send them the image
    users = users_collection.find()
    for user in users:
        send_message(user['user_id'], caption)
        # Send image logic here

# Main function to process updates
def process_updates(update):
    if 'message' in update:
        if 'text' in update['message']:
            text = update['message']['text']

            if text == 'پنل':
                admin_panel(update)
            else:
                greet_user(update)
        elif 'document' in update['message']:
            save_file(update)
        elif 'photo' in update['message']:
            save_image(update)
    elif 'callback_query' in update:
        callback_data = update['callback_query']['data']
        if callback_data == 'check_join':
            check_join(update)
        elif callback_data == 'upload_file':
            upload_file(update)
        elif callback_data == 'upload_text':
            upload_text(update)
        elif callback_data == 'send_message':
            send_message_to_all_users(update)
        elif callback_data == 'send_image':
            send_image_to_all_users(update)

# Start listening for updates
def main():
    url = f'https://api.telegram.org/bot{API_TOKEN}/getUpdates'
    params = {
        'offset': -1,  # Start from the last update
    }

    while True:
        response = requests.get(url, params=params)
        updates = response.json()['result']
        
        for update in updates:
            process_updates(update)

        time.sleep(1)

if __name__ == "__main__":
    main()
