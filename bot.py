import logging
from telegram import Update, PhotoSize
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext
import google.generativeai as genai
from PIL import Image
import io

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "7839187956:AAH5zvalXGCu8aMT9O7YepHdazrM9EpHeEo"
GEMINI_API_KEY = "AIzaSyCmjsjhm5m8N51ec3Mjl13VEFwMj8C9cGc"
MODEL_NAME = "gemini-1.5.1-flash-002"

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

# Conversation History
conversation_history = {}

# Create a custom filter class
class RcmFilter(filters.MessageFilter):
    def filter(self, message):
        return message.text and message.text.startswith('/rcm ')

rcm_filter = RcmFilter()

async def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message on the /start command."""
    await update.message.reply_text(
        "Hi! I'm a chatbot powered by Gemini Flash 2. Use '/rcm <your message>' to chat with me!"
    )
    conversation_history[update.message.chat_id] = []

async def gemini_response(user_message, chat_id):
    """Gets a response from the Gemini model."""
    try:
        if chat_id not in conversation_history:
            conversation_history[chat_id] = []

        chat = model.start_chat(history=conversation_history[chat_id])
        response = chat.send_message(user_message)

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            return f"Gemini blocked this response. Reason: {response.prompt_feedback.block_reason}"

        gemini_text = response.text

        conversation_history[chat_id].append({"role": "user", "parts": [user_message]})
        conversation_history[chat_id].append({"role": "model", "parts": [gemini_text]})

        return gemini_text

    except Exception as e:
        logger.error(f"Error during Gemini API call: {e}")
        return f"Error: Unable to connect to Gemini API. Details: {e}"

async def handle_rcm(update: Update, context: CallbackContext) -> None:
    """Handles /rcm messages"""
    chat_id = update.message.chat_id
    message_text = update.message.text[5:].strip()  # Remove "/rcm " prefix
    
    if not message_text:
        await update.message.reply_text("Please provide a message after /rcm")
        return
    
    logger.info(f"Processing /rcm message from {chat_id}: {message_text}")
    response = await gemini_response(message_text, chat_id)
    await update.message.reply_text(response)

def main() -> None:
    """Starts the bot."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    
    # Custom handler for /rcm messages using the custom filter class
    application.add_handler(MessageHandler(
        filters.TEXT & rcm_filter,
        handle_rcm
    ))

    # Start the bot
    logger.info("Starting bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
