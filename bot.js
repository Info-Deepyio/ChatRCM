const TelegramBot = require('node-telegram-bot-api');
const { GoogleGenerativeAI } = require('@google/generative-ai');

// Directly defined tokens (replace with your actual keys)
const BOT_TOKEN = "7839187956:AAH5zvalXGCu8aMT9O7YepHdazrM9EpHeEo";
const GEMINI_API_KEY = "AIzaSyCmjsjhm5m8N51ec3Mjl13VEFwMj8C9cGc";
const MODEL_NAME = "gemini-1.5-flash-002";

// Initialize bot and Gemini
const bot = new TelegramBot(BOT_TOKEN, { polling: true });
const genAI = new GoogleGenerativeAI(GEMINI_API_KEY);
const model = genAI.getGenerativeModel({ model: MODEL_NAME });

// Store conversation history
const conversationHistory = {};

// Handle /start command
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;
    bot.sendMessage(chatId, "Hi! I'm a chatbot powered by Gemini Flash 2. Ask me anything or use /rcm <prompt>.");
    conversationHistory[chatId] = [];
});

// Handle /rcm command
bot.onText(/\/rcm (.+)/, async (msg, match) => {
    const chatId = msg.chat.id;
    const prompt = match[1]; // Extracts the text after /rcm

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

    // Ignore commands other than /rcm
    if (userMessage.startsWith('/')) return;

    console.log(`User ${chatId}: ${userMessage}`);

    const responseText = await getGeminiResponse(userMessage, chatId);
    bot.sendMessage(chatId, responseText);
});

// Function to get Gemini response
async function getGeminiResponse(userMessage, chatId) {
    if (!conversationHistory[chatId]) {
        conversationHistory[chatId] = [];
    }

    try {
        // Start chat with history
        const chat = model.startChat({
            history: conversationHistory[chatId]
        });

        const response = await chat.sendMessage(userMessage);

        if (response.promptFeedback?.blockReason) {
            return `Gemini blocked this response. Reason: ${response.promptFeedback.blockReason}`;
        }

        const geminiText = response.text;

        // Save conversation history
        conversationHistory[chatId].push({ role: "user", parts: [userMessage] });
        conversationHistory[chatId].push({ role: "model", parts: [geminiText] });

        return geminiText;
    } catch (error) {
        console.error("Gemini API Error:", error);
        return "Error: Unable to process your request.";
    }
}

console.log("Bot is running...");
