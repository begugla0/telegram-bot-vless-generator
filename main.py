import logging
import json
import os
import random
import secrets
import time
from datetime import datetime
from typing import Dict, List, Optional
import re

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)
import aiohttp
import qrcode
from io import BytesIO

# Token telegram bot
token = "TOKEN"

# Внимание! Код содержит ссылку на донат. Она находится в строке: 'success' 
# Attention! The code contains a link to the donation. It is in the line: 'success'


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States
LANGUAGE, EMAIL_CHOICE, EMAIL_INPUT, CODE_INPUT, LOCATION_CHOICE = range(5)

# Constants
EMAIL_API_ENDPOINT = "https://api.internal.temp-mail.io/api/v3/email"
AEZA_API_ENDPOINT = "https://api.aeza-security.net/v2"
USER_AGENT = "Dart/3.5 (dart:io)"

# Translations
TRANSLATIONS = {
    'en': {
        'start': '👋 Welcome to VLESS Config Generator Bot!\n\nPlease select your language:',
        #'email_choice': '📧 Would you like to use a temporary email (recommended) or enter your own?',
        'email_choice': '👤 Select the authorization method in the system:',
        'enter_email': '✉️ Please enter your email address:',
        'invalid_email': '❌ Invalid email format. Please try again.',
        'enter_code': '🔑 Please enter the confirmation code sent to your email:',
        'select_location': '🌍 Please select a location for your VLESS config:',
        'generating': '⚙️ Generating your VLESS configuration...',
        'success': '✅ Your VLESS configuration is ready!\n\n💵 Support the project: https://clck.ru/3FxiGr \n\nScan the QR code or use the config below:',
        'error': '❌ An error occurred: {}',
        'temp_email': '🔄 Temporary Email',
        'own_email': '📝 Own Email',
        'random_location': '🎲 Random Location',
        'cancelled': '❌ Operation cancelled. Send /start to begin again.'
    },
    'ru': {
        'start': '👋 Добро пожаловать в бот генерации VLESS конфигов!\n\nПожалуйста, выберите язык:',
        #'email_choice': '📧 Хотите использовать временную почту (рекомендуется) или ввести свою?',
        'email_choice': '👤 Выберите способ авторизации в системе:',
        'enter_email': '✉️ Пожалуйста, введите ваш email адрес:',
        'invalid_email': '❌ Неверный формат email. Попробуйте снова.',
        'enter_code': '🔑 Пожалуйста, введите код подтверждения, отправленный на вашу почту:',
        'select_location': '🌍 Пожалуйста, выберите локацию для вашего VLESS конфига:',
        'generating': '⚙️ Генерация VLESS конфигурации...',
        'success': '✅ Ваша VLESS конфигурация готова!\n\n💵 Поддержать проект: https://clck.ru/3FxiGr \n\nОтсканируйте QR код или используйте конфиг ниже:',
        'error': '❌ Произошла ошибка: {}',
        'temp_email': '🔄 Временная почта',
        'own_email': '📝 Своя почта',
        'random_location': '🎲 Случайная локация',
        'cancelled': '❌ Операция отменена. Отправьте /start чтобы начать заново.'
    }
}

class UserData:
    def __init__(self):
        self.email: Optional[str] = None
        self.device_id: Optional[str] = None
        self.api_token: Optional[str] = None
        self.language: Optional[str] = None

user_data_dict: Dict[int, UserData] = {}

async def make_request(session: aiohttp.ClientSession, method: str, url: str, **kwargs) -> dict:
    headers = kwargs.pop('headers', {})
    headers['User-Agent'] = USER_AGENT
    
    async with session.request(method, url, headers=headers, **kwargs) as response:
        if response.status != 200:
            raise Exception(f"Request failed with status {response.status}")
        return await response.json()

async def send_confirmation_code(session: aiohttp.ClientSession, email: str) -> None:
    await make_request(
        session,
        'POST',
        f"{AEZA_API_ENDPOINT}/auth",
        json={"email": email}
    )

async def get_temporary_email(session: aiohttp.ClientSession) -> str:
    response = await make_request(session, 'POST', f"{EMAIL_API_ENDPOINT}/new")
    return response['email']

async def get_free_locations(session: aiohttp.ClientSession) -> List[str]:
    response = await make_request(session, 'GET', f"{AEZA_API_ENDPOINT}/locations")
    return [loc.upper() for loc, data in response['response'].items() if data['free']]

async def generate_device_id() -> str:
    return secrets.token_hex(8).upper()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data_dict[user_id] = UserData()
    
    keyboard = [
        [InlineKeyboardButton("English 🇬🇧", callback_data='lang_en')],
        [InlineKeyboardButton("Русский 🇷🇺", callback_data='lang_ru')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Welcome / Добро пожаловать!\n\nPlease select your language / Пожалуйста, выберите язык:",
        reply_markup=reply_markup
    )
    return LANGUAGE

async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    language = query.data.split('_')[1]
    user_data_dict[user_id].language = language
    
    keyboard = [
        #[InlineKeyboardButton(TRANSLATIONS[language]['temp_email'], callback_data='email_temp')],
        [InlineKeyboardButton(TRANSLATIONS[language]['own_email'], callback_data='email_own')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=TRANSLATIONS[language]['email_choice'],
        reply_markup=reply_markup
    )
    return EMAIL_CHOICE

async def email_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = user_data_dict[user_id]
    choice = query.data.split('_')[1]
    
    async with aiohttp.ClientSession() as session:
        if choice == 'temp':
            user_data.email = await get_temporary_email(session)
            await send_confirmation_code(session, user_data.email)
            await query.edit_message_text(
                TRANSLATIONS[user_data.language]['enter_code']
            )
            return CODE_INPUT
        else:
            await query.edit_message_text(
                TRANSLATIONS[user_data.language]['enter_email']
            )
            return EMAIL_INPUT

async def email_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data = user_data_dict[user_id]
    email = update.message.text.strip()
    
    # Basic email validation
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text(
            TRANSLATIONS[user_data.language]['invalid_email']
        )
        return EMAIL_INPUT
    
    user_data.email = email
    async with aiohttp.ClientSession() as session:
        await send_confirmation_code(session, email)
    
    await update.message.reply_text(
        TRANSLATIONS[user_data.language]['enter_code']
    )
    return CODE_INPUT

async def code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data = user_data_dict[user_id]
    code = update.message.text.strip()
    
    # Generate device ID if not exists
    if not user_data.device_id:
        user_data.device_id = await generate_device_id()
    
    async with aiohttp.ClientSession() as session:
        try:
            # Get API token
            response = await make_request(
                session,
                'POST',
                f"{AEZA_API_ENDPOINT}/auth-confirm",
                json={"email": user_data.email, "code": code},
                headers={"Device-Id": user_data.device_id}
            )
            user_data.api_token = response['response']['token']
            
            # Get locations
            locations = await get_free_locations(session)
            keyboard = []
            for loc in locations:
                keyboard.append([InlineKeyboardButton(loc, callback_data=f'loc_{loc}')])
            keyboard.append([InlineKeyboardButton(
                TRANSLATIONS[user_data.language]['random_location'],
                callback_data='loc_random'
            )])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                TRANSLATIONS[user_data.language]['select_location'],
                reply_markup=reply_markup
            )
            return LOCATION_CHOICE
            
        except Exception as e:
            await update.message.reply_text(
                TRANSLATIONS[user_data.language]['error'].format(str(e))
            )
            return ConversationHandler.END

async def location_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = user_data_dict[user_id]
    location = query.data.split('_')[1]
    
    await query.edit_message_text(
        TRANSLATIONS[user_data.language]['generating']
    )
    
    async with aiohttp.ClientSession() as session:
        try:
            if location == 'random':
                locations = await get_free_locations(session)
                location = random.choice(locations)
            
            # Get VLESS key
            response = await make_request(
                session,
                'POST',
                f"{AEZA_API_ENDPOINT}/vpn/connect",
                json={"location": location.lower()},
                headers={
                    "Device-Id": user_data.device_id,
                    "Aeza-Token": user_data.api_token
                }
            )
            
            vless_key = response['response']['accessKey']
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(vless_key)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            bio = BytesIO()
            img.save(bio, 'PNG')
            bio.seek(0)
            
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=bio,
                caption=f"{TRANSLATIONS[user_data.language]['success']}\n\n`{vless_key}`",
                parse_mode='Markdown'
            )
            
            # Clean up user data
            del user_data_dict[user_id]
            return ConversationHandler.END
            
        except Exception as e:
            await query.edit_message_text(
                TRANSLATIONS[user_data.language]['error'].format(str(e))
            )
            return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    language = user_data_dict.get(user_id, UserData()).language or 'en'
    
    if user_id in user_data_dict:
        del user_data_dict[user_id]
    
    await update.message.reply_text(
        TRANSLATIONS[language]['cancelled'],
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    user_id = update.effective_user.id if update else None
    language = user_data_dict.get(user_id, UserData()).language or 'en'
    
    error_message = TRANSLATIONS[language]['error'].format(str(context.error))
    if update and update.effective_message:
        await update.effective_message.reply_text(error_message)

def main() -> None:
    application = Application.builder().token(token).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANGUAGE: [CallbackQueryHandler(language_choice, pattern='^lang_')],
            EMAIL_CHOICE: [CallbackQueryHandler(email_choice, pattern='^email_')],
            EMAIL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_input)],
            CODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_input)],
            LOCATION_CHOICE: [CallbackQueryHandler(location_choice, pattern='^loc_')]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    application.run_polling()

if __name__ == "__main__":
    main()