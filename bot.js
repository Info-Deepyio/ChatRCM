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
    chatHistory[chatId].push({ role: "user", content: prompt });


    try {
        bot.sendMessage(chatId, 'Thinking...');

        const messages = [{"role": "system", "content": "You are a helpful and friendly chatbot."}];
        messages.push(...chatHistory[chatId]);


        const response = await axios.post('https://generativelanguage.googleapis.com/v1beta2/models/text-bison-001:generateText', { // Gemini API endpoint
            prompt: {
                text: prompt // Send the current prompt directly (Gemini doesn't use the same message structure as OpenAI)
            },
            temperature: 0.7, // Adjust temperature as needed
            top_k: 40,        // Adjust top_k as needed
            max_output_tokens: 150,
        }, {
            headers: {
                'Authorization': `Bearer ${GOOGLE_API_KEY}`,
                'Content-Type': 'application/json',
            },
        });



        const reply = response.data.candidates[0].output; // Extract the reply from Gemini's response
        chatHistory[chatId].push({ role: "assistant", content: reply });
        bot.sendMessage(chatId, reply);



    } catch (error) {
        console.error(error);
        bot.sendMessage(chatId, 'An error occurred.');
    }
});


// ... (rest of the code: /history, /clear_history commands remain the same)


console.log('Bot started.');
