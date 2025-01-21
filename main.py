import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from collections import defaultdict

# API Token
TOKEN = '7605213276:AAG7xpVqnG4mxcdgvlqh91tbu_Foaw2D3Ik'
ADMIN_IDS = {5176006969, 1483826275}

# Збереження балансу користувачів та списку всіх користувачів
user_balances = defaultdict(int)
all_users = set()
pending_questions = {}
match_predictions = {}

# Функція старту
async def start(update: Update, context):
    user_id = update.message.from_user.id
    if user_id not in all_users:
        all_users.add(user_id)  # Додаємо користувача до списку
        print(f"Користувача {user_id} додано до списку.")
    await update.message.reply_text("Привіт! Очікуй питання від адміністратора!")

# Функція для адміністраторів для створення питання
async def create_question(update: Update, context):
    if update.message.from_user.id in ADMIN_IDS:
        await update.message.reply_text("Введіть запитання:")
        context.user_data['creating_question'] = {'step': 'question'}
    else:
        await update.message.reply_text("У вас немає прав для цієї команди.")

# Функція для адміністраторів для створення опитування
async def match_predict_ad(update: Update, context):
    if update.message.from_user.id in ADMIN_IDS:
        await update.message.reply_text("Введіть текст опитування:")
        context.user_data['creating_prediction'] = {'step': 'question'}
    else:
        await update.message.reply_text("У вас немає прав для цієї команди.")

# Обробка введеного тексту для питання
async def handle_message(update: Update, context):
    user_data = context.user_data

    if 'creating_question' in user_data:
        step = user_data['creating_question']

        if step['step'] == 'question':
            step['question'] = update.message.text
            step['step'] = 'wrong_answers'
            await update.message.reply_text("Тепер введіть 3 неправильні варіанти через кому:")

        elif step['step'] == 'wrong_answers':
            step['wrong_answers'] = update.message.text.split(',')
            step['step'] = 'correct_answer'
            await update.message.reply_text("Тепер введіть правильний варіант:")

        elif step['step'] == 'correct_answer':
            step['correct_answer'] = update.message.text
            await send_question_to_all(update, context, step)
            del user_data['creating_question']
            await update.message.reply_text("Запитання успішно відправлено всім користувачам!")

    elif 'creating_prediction' in user_data:
        step = user_data['creating_prediction']

        if step['step'] == 'question':
            step['question'] = update.message.text
            step['step'] = 'options'
            await update.message.reply_text("Введіть два варіанти відповіді через кому:")

        elif step['step'] == 'options':
            options = update.message.text.split(',')
            if len(options) != 2:
                await update.message.reply_text("Будь ласка, введіть рівно два варіанти відповіді.")
                return

            step['options'] = options
            await send_prediction_to_all(update, context, step)
            del user_data['creating_prediction']
            await update.message.reply_text("Опитування успішно відправлено всім користувачам!")

# Функція для розсилки питання всім користувачам
async def send_question_to_all(update: Update, context, question_data):
    question = question_data['question']
    wrong_answers = question_data['wrong_answers']
    correct_answer = question_data['correct_answer']

    options = wrong_answers + [correct_answer]
    random.shuffle(options)

    keyboard = [[InlineKeyboardButton(option, callback_data=option)] for option in options]

    message = f"❓ *{question}*\n\nВиберіть правильний варіант:"
    markup = InlineKeyboardMarkup(keyboard)

    if not all_users:
        await update.message.reply_text("❌ Немає користувачів для розсилки.")
        return

    for user_id in all_users:
        try:
            sent_message = await context.bot.send_message(chat_id=user_id, text=message, reply_markup=markup, parse_mode="Markdown")
            pending_questions[sent_message.message_id] = {
                "user_id": user_id,
                "correct": correct_answer
            }

            # Часовий ліміт на відповідь (30 секунд)
            asyncio.create_task(remove_expired_question(sent_message.message_id, context))
        except Exception as e:
            print(f"Помилка надсилання користувачу {user_id}: {e}")

# Функція для розсилки опитування всім користувачам
async def send_prediction_to_all(update: Update, context, prediction_data):
    question = prediction_data['question']
    options = prediction_data['options']

    keyboard = [[InlineKeyboardButton(option, callback_data=f"predict:{option}")] for option in options]

    message = f"📊 *{question}*\n\nОберіть свій варіант:"
    markup = InlineKeyboardMarkup(keyboard)

    if not all_users:
        await update.message.reply_text("❌ Немає користувачів для розсилки.")
        return

    for user_id in all_users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            print(f"Помилка надсилання користувачу {user_id}: {e}")

    # Надсилаємо опитування адміністратору
    admin_keyboard = [[InlineKeyboardButton(option, callback_data=f"admin_predict:{option}")] for option in options]
    admin_message = f"📊 *Опитування:* {question}\n\nОберіть правильний варіант для завершення опитування:"
    admin_markup = InlineKeyboardMarkup(admin_keyboard)

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_message, reply_markup=admin_markup, parse_mode="Markdown")
        except Exception as e:
            print(f"Помилка надсилання адміністратору {admin_id}: {e}")

# Обробка відповіді користувачів
async def answer_callback(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if data.startswith("predict:"):
        selected_option = data.split(":", 1)[1]
        match_predictions.setdefault(user_id, []).append(selected_option)
        await query.answer("Ваш вибір збережено!")

    elif data.startswith("admin_predict:"):
        correct_option = data.split(":", 1)[1]
        await finalize_prediction(context, correct_option)
        await query.message.reply_text(f"Опитування завершено. Правильний варіант: {correct_option}")

# Завершення опитування та нарахування балів
async def finalize_prediction(context, correct_option):
    for user_id, predictions in match_predictions.items():
        if correct_option in predictions:
            user_balances[user_id] += 50
            await context.bot.send_message(chat_id=user_id, text=f"✅ Ви вгадали! +50 балів. Ваш баланс: {user_balances[user_id]}")

    match_predictions.clear()

# Функція для перегляду балансу користувача
async def balance(update: Update, context):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"Ваш баланс: {user_balances[user_id]} балів")

# Функція для адміністраторів для перегляду всіх балансів
async def admin_balance(update: Update, context):
    if update.message.from_user.id in ADMIN_IDS:
        if not user_balances:
            await update.message.reply_text("Наразі жоден користувач не має балансу.")
            return
        balance_info = "\n".join([f"ID: {user} - {balance} балів" for user, balance in user_balances.items()])
        await update.message.reply_text(f"Баланс користувачів:\n{balance_info}")
    else:
        await update.message.reply_text("У вас немає прав для цієї команди.")

# Функція для видалення простроченого питання
async def remove_expired_question(message_id, context):
    await asyncio.sleep(30)
    if message_id in pending_questions:
        user_id = pending_questions[message_id]['user_id']
        await context.bot.send_message(chat_id=user_id, text="⏳ Час вийшов! Ви не встигли відповісти.")
        del pending_questions[message_id]

# Налаштування бота
app = Application.builder().token(TOKEN).build()

# Обробники команд
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("create_question", create_question))
app.add_handler(CommandHandler("balance", balance))
app.add_handler(CommandHandler("admin_balance", admin_balance))
app.add_handler(CommandHandler("match_predict_ad", match_predict_ad))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(answer_callback))

print("Бот запущено...")
app.run_polling()
