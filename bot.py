import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext
import google.generativeai as genai

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration ---
BOT_TOKEN = "7839187956:AAH5zvalXGCu8aMT9O7YepHdazrM9EpHeEo"  # Keep the original bot token
GEMINI_API_KEY = "AIzaSyCmjsjhm5m8N51ec3Mjl13VEFwMj8C9cGc"  # Keep the original Gemini API key
MODEL_NAME = "gemini-1.5-flash-002"

# --- Initialize Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

# --- Simple Conversation History ---
conversation_history = {}

async def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message on the /start command."""
    await update.message.reply_text(
        "Hi! I'm a chatbot powered by Gemini Flash 2. Just type /rcm followed by a prompt to get a response."
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

async def handle_message(update: Update, context: CallbackContext) -> None:
    """Handles incoming text messages."""
    user_message = update.message.text
    chat_id = update.message.chat_id

    logger.info(f"User {chat_id} says: {user_message}")

    # Only process messages that start with "/rcm "
    if user_message.startswith("/rcm "):
        prompt = user_message[5:].strip()  # Remove "/rcm " part and strip extra spaces
        gemini_text = await gemini_response(prompt, chat_id)
        await update.message.reply_text(gemini_text)

def main() -> None:
    """Starts the bot."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.PHOTO, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()
