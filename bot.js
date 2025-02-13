const TelegramBot = require('node-telegram-bot-api');
const { GoogleGenerativeAI } = require('@google/generative-ai');

// Directly defined tokens (replace with your actual keys)
const BOT_TOKEN = "7839187956:AAH5zvalXGCu8aMT9O7YepHdazrM9EpHeEo"; // Replace with your bot token
const GEMINI_API_KEY = "AIzaSyDVvkJHT9HRKnSo4ZYN8GNV3kt5tn-kwcc"; // Replace with your Gemini API key
const MODEL_NAME = "gemini-1.5-flash-002"; // Or another suitable model

// Initialize bot and Gemini
const bot = new TelegramBot(BOT_TOKEN, { polling: true });
const genAI = new GoogleGenerativeAI(GEMINI_API_KEY);
const model = genAI.getGenerativeModel({ model: MODEL_NAME });

// Store conversation history.  Use a Map for better key handling
const conversationHistory = new Map();

// Handle /start command
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;
    bot.sendMessage(chatId, "Hi! I'm a chatbot powered by Gemini Flash 2. Ask me anything or use /rcm <prompt>.");
    conversationHistory.set(chatId, []); // Use set for Map
});

// Handle /rcm command
bot.onText(/\/rcm (.+)/, async (msg, match) => {
    const chatId = msg.chat.id;
    const prompt = match[1];

    if (!prompt) {
        bot.sendMessage(chatId, "Usage: /rcm <prompt>");
        return;
    }

    console.log(`User ${chatId} used /rcm: ${prompt}`);

    const responseText = await getGeminiResponse(prompt, chatId);
    bot.sendMessage(chatId, responseText);
});

// Handle normal text messages
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const userMessage = msg.text;

    if (!userMessage) return; // Handle messages without text (e.g., images)

    // Ignore commands other than /rcm
    if (userMessage.startsWith('/')) return;

    console.log(`User ${chatId}: ${userMessage}`);

    const responseText = await getGeminiResponse(userMessage, chatId);
    bot.sendMessage(chatId, responseText);
});

// Function to get Gemini response
async function getGeminiResponse(userMessage, chatId) {
    // Get history from Map, or create a new array if none exists
    let history = conversationHistory.get(chatId) || [];

    try {
        const chat = model.startChat({
            history: history
        });

        const response = await chat.sendMessage(userMessage);

        if (response.promptFeedback?.blockReason) {
            return `Gemini blocked this response. Reason: ${response.promptFeedback.blockReason}`;
        }

        const geminiText = response.text;

        // Update conversation history in the Map
        history.push({ role: "user", parts: [userMessage] });
        history.push({ role: "model", parts: [geminiText] });
        conversationHistory.set(chatId, history); // Important: Update the Map!

        return geminiText;
    } catch (error) {
        console.error("Gemini API Error:", error);
        return "Error: Unable to process your request.";
    }
}

console.log("Bot is running...");
