"""
Telegram Bot для обработки обращений.
Класс-обёртка для интеграции с WebSocket клиентом.
"""

import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from telegram.error import TelegramError

from rate_limiter import get_limiter
from ticket_counter import get_counter

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
NICKNAME, CATEGORY, MESSAGE = range(3)


class TelegramFeedbackBot:
    """
    Telegram бот для обработки обращений.
    
    Функции:
    1. Отправка обращений с сайта в Telegram группу (вызывается из WebSocket)
    2. Приём обращений напрямую в ЛС бота (команда /feedback)
    3. Управление статусами через inline кнопки
    """
    
    def __init__(self):
        """Инициализация бота."""
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.channel_id = os.getenv('FEEDBACK_TELEGRAM_CHANNEL_ID')
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")
        
        if not self.channel_id:
            raise ValueError("FEEDBACK_TELEGRAM_CHANNEL_ID not set in environment")
        
        self.application = None
        self.bot = Bot(token=self.bot_token)
        
        logger.info("✅ TelegramFeedbackBot initialized")
    
    async def send_feedback_to_telegram(
        self,
        feedback_id: int,
        telegram_id: int,
        telegram_username: str,
        telegram_first_name: str,
        nickname: str,
        category: str,
        message: str,
        created_at: Optional[str] = None,
        source: str = 'website'
    ) -> Dict:
        """
        Отправить обращение в Telegram группу.
        Вызывается из WebSocket клиента.
        
        Args:
            feedback_id: ID обращения (0 для auto-gen)
            telegram_id: Telegram ID пользователя
            telegram_username: Username (без @)
            telegram_first_name: Имя пользователя
            nickname: Ник в игре
            category: Категория (bug, wish, question, other)
            message: Текст обращения
            created_at: Дата создания (ISO format)
            source: Источник (website или telegram_bot)
        
        Returns:
            Dict с ticket_id, message_id, sent_at
        """
        # Генерируем ticket_id
        counter = get_counter()
        
        if source == 'telegram_bot':
            ticket_id = counter.get_next_tg()
        else:
            if feedback_id > 0:
                ticket_id = f"ticket_site_{feedback_id}"
            else:
                ticket_id = counter.get_next_site()
        
        # Форматируем сообщение
        formatted_message = self._format_feedback_message(
            ticket_id=ticket_id,
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            telegram_first_name=telegram_first_name,
            nickname=nickname,
            category=category,
            message=message,
            created_at=created_at,
            source=source
        )
        
        # Создаём inline кнопки для статусов
        keyboard = [
            [
                InlineKeyboardButton("👀 Прочитано", callback_data=f"status_{ticket_id}_read"),
                InlineKeyboardButton("⚙️ В работе", callback_data=f"status_{ticket_id}_in_progress"),
            ],
            [
                InlineKeyboardButton("✅ Ответили", callback_data=f"status_{ticket_id}_replied"),
                InlineKeyboardButton("🔒 Закрыто", callback_data=f"status_{ticket_id}_closed"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем в группу
        try:
            sent_message = await self.bot.send_message(
                chat_id=self.channel_id,
                text=formatted_message,
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=reply_markup
            )
            
            logger.info(f"✅ Ticket {ticket_id} sent to Telegram (message_id={sent_message.message_id})")
            
            return {
                'ticket_id': ticket_id,
                'message_id': sent_message.message_id,
                'sent_at': datetime.now().isoformat()
            }
        
        except TelegramError as e:
            logger.error(f"❌ Telegram error for ticket {ticket_id}: {e}")
            # Flood control - не прерываем работу
            if "Flood control" in str(e) or "Too Many Requests" in str(e):
                logger.warning(f"Flood control hit for {ticket_id}, queued")
                return {
                    'ticket_id': ticket_id,
                    'message_id': 0,
                    'sent_at': datetime.now().isoformat()
                }
            raise
    
    def _format_feedback_message(
        self,
        ticket_id: str,
        telegram_id: int,
        telegram_username: str,
        telegram_first_name: str,
        nickname: str,
        category: str,
        message: str,
        created_at: Optional[str],
        source: str
    ) -> str:
        """Форматирует сообщение для Telegram."""
        # Иконки категорий
        category_icons = {
            'bug': '🐛',
            'wish': '💡',
            'question': '❓',
            'other': '💬'
        }
        
        category_names = {
            'bug': 'Сообщить о баге',
            'wish': 'Пожелания',
            'question': 'Задать вопрос',
            'other': 'Просто спросить'
        }
        
        # Информация о пользователе
        if telegram_username:
            username = f"@{telegram_username}"
        else:
            username = f"ID{telegram_id}"
        
        if telegram_first_name:
            name = f" ({telegram_first_name})"
        else:
            name = ""
        
        user_info = f"{username}{name}"
        
        # Ник в игре
        nickname_text = nickname if nickname else "не указан"
        
        # Категория с иконкой
        icon = category_icons.get(category, '💬')
        category_text = category_names.get(category, category)
        
        # Дата в московской таймзоне
        moscow_tz = ZoneInfo("Europe/Moscow")
        
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                dt_moscow = dt.astimezone(moscow_tz)
                date_str = dt_moscow.strftime('%d.%m.%Y %H:%M')
            except:
                date_str = created_at
        else:
            dt_moscow = datetime.now(moscow_tz)
            date_str = dt_moscow.strftime('%d.%m.%Y %H:%M')
        
        # Определяем источник
        source_icons = {
            'website': '🌐',
            'telegram_bot': '💬'
        }
        source_names = {
            'website': 'Сайт',
            'telegram_bot': 'ЛС с ботом'
        }
        source_icon = source_icons.get(source, '📱')
        source_name = source_names.get(source, source or 'Неизвестно')
        
        # HTML escape
        message_escaped = (message
                          .replace('&', '&amp;')
                          .replace('<', '&lt;')
                          .replace('>', '&gt;'))
        
        # Формируем сообщение
        msg = f"""🆕 <b>Новое обращение {ticket_id}</b>

👤 <b>От:</b> {user_info}
📝 <b>Ник в игре:</b> {nickname_text}
🏷️ <b>Тема:</b> {icon} {category_text}
{source_icon} <b>Источник:</b> {source_name}

💬 <b>Сообщение:</b>
───────────────────────
{message_escaped}
───────────────────────

📅 <b>Дата:</b> {date_str}

#{category} #new"""
        
        return msg
    
    async def _callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на inline кнопки статусов."""
        query = update.callback_query
        
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Failed to answer query: {e}")
            return
        
        callback_data = query.data
        logger.info(f"Received callback: {callback_data}")
        
        # Парсим callback data: "status_{ticket_id}_{new_status}"
        if not callback_data.startswith('status_'):
            logger.warning(f"Invalid callback format: {callback_data}")
            return
        
        rest = callback_data[7:]  # убираем "status_"
        
        # Статусы
        possible_statuses = ['new', 'read', 'in_progress', 'replied', 'closed']
        
        ticket_id = None
        new_status = None
        
        for status in possible_statuses:
            if rest.endswith('_' + status):
                new_status = status
                ticket_id = rest[:-(len(status) + 1)]
                break
        
        if not ticket_id or not new_status:
            logger.warning(f"Could not parse callback: {callback_data}")
            return
        
        logger.info(f"Parsed: ticket_id={ticket_id}, new_status={new_status}")
        
        # Обновляем текст сообщения
        try:
            status_icons = {
                'new': '🆕',
                'read': '👀',
                'in_progress': '⚙️',
                'replied': '✅',
                'closed': '🔒'
            }
            
            status_names = {
                'new': 'Новое',
                'read': 'Прочитано',
                'in_progress': 'В работе',
                'replied': 'Ответили',
                'closed': 'Закрыто'
            }
            
            icon = status_icons.get(new_status, '📝')
            name = status_names.get(new_status, new_status)
            
            old_text = query.message.text or query.message.caption
            
            # Заменяем хештег статуса
            import re
            new_text = re.sub(r'#(new|read|in_progress|replied|closed)$', f'#{new_status}', old_text)
            new_text = re.sub(r'🆕 <b>Новое обращение', f'{icon} <b>Обращение', new_text)
            
            await query.edit_message_text(
                text=new_text,
                parse_mode='HTML',
                reply_markup=query.message.reply_markup
            )
            
            await query.answer(f"✅ Статус изменён: {name}")
            logger.info(f"Ticket {ticket_id} status changed to {new_status}")
        
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            await query.answer(f"❌ Ошибка: {str(e)}")
    
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start."""
        user = update.effective_user
        
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"Я бот для обработки обращений TZReloaded.\n\n"
            f"📝 Чтобы создать обращение, используйте команду /feedback\n"
            f"❓ Помощь: /help"
        )
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help."""
        await update.message.reply_text(
            "📚 <b>Доступные команды:</b>\n\n"
            "/start - Начало работы\n"
            "/feedback - Создать обращение\n"
            "/cancel - Отменить текущее действие\n"
            "/help - Эта справка\n\n"
            "<b>Как создать обращение:</b>\n"
            "1. Отправьте /feedback\n"
            "2. Укажите ник в игре (или пропустите)\n"
            "3. Выберите категорию\n"
            "4. Напишите ваше сообщение\n\n"
            "Обращение будет отправлено администраторам!",
            parse_mode='HTML'
        )
    
    async def _feedback_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало создания обращения."""
        user = update.effective_user
        
        # Rate limiting
        limiter = get_limiter()
        allowed, remaining, reset_in = limiter.check(user.id)
        
        if not allowed:
            await update.message.reply_text(
                "⏱️ От вас было много заявок за последнее время.\n"
                "Пожалуйста, подождите 10 минут.",
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "📝 <b>Создание обращения</b>\n\n"
            "Укажите ваш ник в игре или нажмите /skip чтобы пропустить.",
            parse_mode='HTML'
        )
        return NICKNAME
    
    async def _skip_nickname(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Пропуск ника."""
        context.user_data['nickname'] = ''
        return await self._ask_category(update, context)
    
    async def _receive_nickname(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение ника."""
        context.user_data['nickname'] = update.message.text.strip()
        return await self._ask_category(update, context)
    
    async def _ask_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запрос категории."""
        keyboard = [
            [
                InlineKeyboardButton("🐛 Сообщить о баге", callback_data="cat_bug"),
                InlineKeyboardButton("💡 Пожелания", callback_data="cat_wish"),
            ],
            [
                InlineKeyboardButton("❓ Задать вопрос", callback_data="cat_question"),
                InlineKeyboardButton("💬 Просто спросить", callback_data="cat_other"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🏷️ <b>Выберите категорию обращения:</b>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return CATEGORY
    
    async def _receive_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение категории."""
        query = update.callback_query
        await query.answer()
        
        category = query.data.replace('cat_', '')
        context.user_data['category'] = category
        
        category_names = {
            'bug': '🐛 Сообщить о баге',
            'wish': '💡 Пожелания',
            'question': '❓ Задать вопрос',
            'other': '💬 Просто спросить'
        }
        
        await query.edit_message_text(
            f"✅ Выбрано: {category_names.get(category, category)}\n\n"
            f"💬 <b>Теперь напишите ваше обращение:</b>\n"
            f"(от 10 до 2000 символов)",
            parse_mode='HTML'
        )
        return MESSAGE
    
    async def _receive_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение текста обращения и отправка."""
        message_text = update.message.text.strip()
        
        # Валидация
        if len(message_text) < 10:
            await update.message.reply_text(
                "❌ Сообщение слишком короткое. Минимум 10 символов.\n"
                "Пожалуйста, напишите подробнее:"
            )
            return MESSAGE
        
        if len(message_text) > 2000:
            await update.message.reply_text(
                "❌ Сообщение слишком длинное. Максимум 2000 символов.\n"
                "Пожалуйста, сократите:"
            )
            return MESSAGE
        
        user = update.effective_user
        
        # Отправляем через тот же метод что используется для WebSocket
        try:
            result = await self.send_feedback_to_telegram(
                feedback_id=0,
                telegram_id=user.id,
                telegram_username=user.username or '',
                telegram_first_name=user.first_name or '',
                nickname=context.user_data.get('nickname', ''),
                category=context.user_data['category'],
                message=message_text,
                created_at=None,
                source='telegram_bot'
            )
            
            # Записываем в rate limiter
            limiter = get_limiter()
            limiter.record(user.id)
            
            ticket_id = result['ticket_id']
            
            await update.message.reply_text(
                f"✅ <b>Обращение отправлено!</b>\n\n"
                f"Номер обращения: <code>{ticket_id}</code>\n\n"
                f"Ваше обращение получено и отправлено администраторам.\n"
                f"Мы свяжемся с вами в ближайшее время.\n\n"
                f"Спасибо за обращение! 🙏",
                parse_mode='HTML'
            )
            logger.info(f"Ticket {ticket_id} from LS user {user.id} sent successfully")
        
        except Exception as e:
            await update.message.reply_text(
                "❌ Произошла ошибка при отправке обращения.\n"
                "Пожалуйста, попробуйте позже."
            )
            logger.exception(f"Error sending feedback from LS: {e}")
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def _cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена создания обращения."""
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Создание обращения отменено.\n\n"
            "Чтобы создать новое обращение, используйте /feedback"
        )
        return ConversationHandler.END
    
    async def start(self):
        """Запуск Telegram бота (polling)."""
        logger.info("🚀 Starting Telegram bot polling...")
        
        # Создаём приложение
        self.application = Application.builder().token(self.bot_token).build()
        
        # ConversationHandler для создания обращений
        feedback_conv = ConversationHandler(
            entry_points=[CommandHandler('feedback', self._feedback_start)],
            states={
                NICKNAME: [
                    CommandHandler('skip', self._skip_nickname),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_nickname)
                ],
                CATEGORY: [
                    CallbackQueryHandler(self._receive_category, pattern='^cat_')
                ],
                MESSAGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_message)
                ]
            },
            fallbacks=[CommandHandler('cancel', self._cancel_command)],
            allow_reentry=True
        )
        
        # Регистрируем обработчики
        self.application.add_handler(CommandHandler('start', self._start_command))
        self.application.add_handler(CommandHandler('help', self._help_command))
        self.application.add_handler(CallbackQueryHandler(self._callback_handler, pattern='^status_'))
        self.application.add_handler(feedback_conv)
        
        logger.info("✅ Telegram bot handlers registered")
        logger.info("   - Commands: /start, /help, /feedback, /cancel")
        logger.info("   - Status management via inline buttons")
        
        # Запускаем polling
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        # Держим бота запущенным
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("🛑 Telegram bot polling stopped")
    
    async def stop(self):
        """Остановка бота."""
        logger.info("🛑 Stopping Telegram bot...")
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        logger.info("✅ Telegram bot stopped")


# Для обратной совместимости со старым кодом
import asyncio

