import logging
from telegram import Update, PhotoSize
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext
import google.generativeai as genai
from PIL import Image  # for image processing
import io  # for handling image data

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- Configuration ---
BOT_TOKEN = "7839187956:AAH5zvalXGCu8aMT9O7YepHdazrM9EpHeEo"  # Replace with your Telegram bot token
GEMINI_API_KEY = "AIzaSyCmjsjhm5m8N51ec3Mjl13VEFwMj8C9cGc"  # Replace with your Gemini API key
MODEL_NAME = "gemini-1.5-flash-002"  # Use Flash 2.0 or appropriate model.

# --- Initialize Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

# --- Simple Conversation History --- (Memory is VERY basic)
conversation_history = {}  # user_id: list of messages


async def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message on the /start command."""
    await update.message.reply_text(
        "Hi! I'm a chatbot powered by Gemini Flash 2. I can chat, and I can analyze images you send me.  Image generation is a feature for early testers only at the moment."
    )
    conversation_history[update.message.chat_id] = []


async def analyze_image(update: Update, context: CallbackContext) -> None:
    """Analyzes an image sent by the user using Gemini."""
    chat_id = update.message.chat_id
    try:
        # Get the image from the message.  Telegram sends multiple sizes, get the largest.
        photo: PhotoSize = update.message.photo[-1]  # Get the largest resolution photo

        # Download the image to memory
        image_file = await photo.get_file()
        image_bytes = await image_file.download_as_bytearray() # Download to memory

        # **CONVERT BYTEARRAY TO BYTES** - This fixes the error!
        image_bytes = bytes(image_bytes)

        # Open the image using PIL (Pillow)
        image = Image.open(io.BytesIO(image_bytes))

        # Prepare the image part for Gemini
        image_part = {"mime_type": "image/jpeg", "data": image_bytes} # Or "image/png"

        # Construct the prompt (you can customize this)
        prompt = "Describe this image in detail."

        # Send the image and prompt to Gemini
        response = model.generate_content([prompt, image_part]) # IMPORTANT: list containing both text and image

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            await update.message.reply_text(f"Gemini blocked this response. Reason: {response.prompt_feedback.block_reason}")
            return

        await update.message.reply_text(response.text)


    except Exception as e:
        logger.error(f"Error analyzing image: {e}")
        await update.message.reply_text(f"Error: Could not analyze image.  Details: {e}")


async def gemini_response(user_message, chat_id):
    """Gets a response from the Gemini model.  Now uses chat history."""
    try:
        # Retrieve or initialize chat history
        if chat_id not in conversation_history:
            conversation_history[chat_id] = []

        # Create a chat session (required for conversation history)
        chat = model.start_chat(history=conversation_history[chat_id])

        response = chat.send_message(user_message)

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            return f"Gemini blocked this response. Reason: {response.prompt_feedback.block_reason}"

        gemini_text = response.text

        # Update conversation history with user message and Gemini's response.  Crucial!
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

    gemini_text = await gemini_response(user_message, chat_id)

    await update.message.reply_text(gemini_text)


def main() -> None:
    """Starts the bot."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, analyze_image))  # Handles images
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.PHOTO, handle_message)) # Handles text

    application.run_polling()


if __name__ == "__main__":
    main()
