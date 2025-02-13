const TelegramBot = require('node-telegram-bot-api');
const axios = require('axios');

const TELEGRAM_BOT_TOKEN = '7839187956:AAH5zvalXGCu8aMT9O7YepHdazrM9EpHeEo';
const GOOGLE_API_KEY = 'AIzaSyDVvkJHT9HRKnSo4ZYN8GNV3kt5tn-kwcc';

const bot = new TelegramBot(TELEGRAM_BOT_TOKEN, { polling: true });
const chatHistory = {};

bot.onText(/\/rcm (.+)/, async (msg, match) => {
    const chatId = msg.chat.id;
    const prompt = match[1];

    if (!chatHistory[chatId]) {
        chatHistory[chatId] = [];
    }


    try {
        bot.sendMessage(chatId, 'Thinking...');

        const messages = [{"role": "system", "content": "You are a helpful and friendly chatbot."}];
        //  Build messages array for context
        chatHistory[chatId].forEach(message => {
            messages.push(message)
        });

        const response = await axios.post('https://generativelanguage.googleapis.com/v1beta2/models/text-bison-001:generateText', {
            prompt: {
                messages: messages // Gemini uses the "messages" field within the prompt
            },
            temperature: 0.7, 
            top_k: 40,        
            max_output_tokens: 150,
        }, {
            headers: {
                'Authorization': `Bearer ${GOOGLE_API_KEY}`,
                'Content-Type': 'application/json',
            },
        });

        if (response.data && response.data.candidates && response.data.candidates[0] && response.data.candidates[0].output) {  // Check if the response is in the expected format
            const reply = response.data.candidates[0].output;
            chatHistory[chatId].push({ role: "user", content: prompt }); // Store user message *after* getting a successful response
            chatHistory[chatId].push({ role: "assistant", content: reply });
            bot.sendMessage(chatId, reply);
        } else {
            console.error("Unexpected response format:", response.data);
            bot.sendMessage(chatId, 'An error occurred. Unexpected response format.');
        }



    } catch (error) {
        console.error(error);
        bot.sendMessage(chatId, 'An error occurred.');
    }
});


// ... (rest of the code: /history, /clear_history commands remain the same)

console.log('Bot started.');
