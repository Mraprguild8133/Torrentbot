import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from telegram import Update, ChatMember, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackContext, ChatMemberHandler
)

from config import config

# Set up logging
logging.basicConfig(
    format=config.LOG_FORMAT,
    level=getattr(logging, config.LOG_LEVEL)
)
logger = logging.getLogger(__name__)

class AnimeGroupManager:
    def __init__(self):
        self.warned_users: Dict[int, List[datetime]] = {}
        self.muted_users: Dict[int, datetime] = {}
        self.last_message: Dict[int, datetime] = {}
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message when the command /start is issued."""
        user = update.effective_user
        welcome_text = f"""
🌸 *Anime Guardian Bot* 🌸

Konnichiwa {user.mention_html()}! I'm your anime-themed group management bot!

*Available Commands:*
• /start - Show this welcome message
• /help - Show help information
• /quote - Get a random anime quote
• /rules - Show group rules
• /warn @user - Warn a user
• /mute @user - Mute a user
• /unmute @user - Unmute a user
• /ban @user - Ban a user
• /kick @user - Kick a user
• /warnings @user - Check user warnings

Let's keep this community awesome! ✨
        """
        await update.message.reply_text(welcome_text, parse_mode='HTML')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        help_text = """
🎌 *Anime Guardian Bot - Help* 🎌

*Admin Commands:*
/warn @user - Warn a user ({max_warnings} warnings = auto-ban)
/mute @user - Mute a user for {mute_duration} hour
/unmute @user - Unmute a user
/ban @user - Ban a user from the group
/kick @user - Kick a user from the group
/warnings @user - Check user warnings

*User Commands:*
/start - Welcome message
/help - This help message
/quote - Random anime quote
/rules - Group rules

*Features:*
• Auto-welcome new members
• Anti-spam protection
• Warning system
• Anime-themed responses
        """.format(
            max_warnings=config.MAX_WARNINGS,
            mute_duration=config.MUTE_DURATION_HOURS
        )
        await update.message.reply_text(help_text, parse_mode='HTML')
    
    async def send_quote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a random anime quote."""
        quote = random.choice(config.ANIME_QUOTES)
        await update.message.reply_text(f"💫 *Anime Quote of the Moment:*\n\n{quote}", parse_mode='HTML')
    
    async def show_rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show group rules."""
        await update.message.reply_text(config.GROUP_RULES, parse_mode='HTML')
    
    async def welcome_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome new members with anime-themed message."""
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                # Bot was added to group
                await update.message.reply_text(config.RESPONSES["welcome_bot"])
            else:
                welcome_msg = random.choice(config.ANIME_WELCOME_MESSAGES).format(
                    user=member.mention_html()
                )
                await update.message.reply_text(welcome_msg, parse_mode='HTML')
    
    async def warn_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Warn a user."""
        if not await self._is_admin(update, context):
            await update.message.reply_text(config.RESPONSES["no_permission"])
            return
        
        if not context.args:
            await update.message.reply_text(
                config.RESPONSES["no_user_mentioned"].format(usage="/warn @username")
            )
            return
        
        target_user = await self._get_mentioned_user(update, context)
        if not target_user:
            await update.message.reply_text(config.RESPONSES["user_not_found"])
            return
        
        user_id = target_user.id
        current_time = datetime.now()
        
        # Initialize warnings list for user
        if user_id not in self.warned_users:
            self.warned_users[user_id] = []
        
        # Add warning
        self.warned_users[user_id].append(current_time)
        warning_count = len(self.warned_users[user_id])
        
        warning_text = f"""
⚠️ *Warning Issued* ⚠️

User: {target_user.mention_html()}
Warnings: {warning_count}/{config.MAX_WARNINGS}
Issued by: {update.effective_user.mention_html()}

*Next step:* {f"Ban at {config.MAX_WARNINGS} warnings" if warning_count < config.MAX_WARNINGS else "BAN IMMINENT!"}
        """
        
        await update.message.reply_text(warning_text, parse_mode='HTML')
        
        # Auto-ban at max warnings
        if warning_count >= config.MAX_WARNINGS:
            await self.ban_user_manual(
                update, context, target_user, 
                f"Automatically banned for reaching {config.MAX_WARNINGS} warnings"
            )
            # Clear warnings after ban
            if user_id in self.warned_users:
                del self.warned_users[user_id]
    
    async def mute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mute a user."""
        if not await self._is_admin(update, context):
            await update.message.reply_text(config.RESPONSES["no_permission"])
            return
        
        if not context.args:
            await update.message.reply_text(
                config.RESPONSES["no_user_mentioned"].format(usage="/mute @username")
            )
            return
        
        target_user = await self._get_mentioned_user(update, context)
        if not target_user:
            await update.message.reply_text(config.RESPONSES["user_not_found"])
            return
        
        user_id = target_user.id
        mute_duration = timedelta(hours=config.MUTE_DURATION_HOURS)
        unmute_time = datetime.now() + mute_duration
        
        # Set permissions to restrict sending messages
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )
        
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=permissions,
                until_date=unmute_time
            )
            
            self.muted_users[user_id] = unmute_time
            
            mute_text = f"""
🔇 *User Muted* 🔇

User: {target_user.mention_html()}
Duration: {config.MUTE_DURATION_HOURS} hour(s)
Muted by: {update.effective_user.mention_html()}
Unmute at: {unmute_time.strftime('%Y-%m-%d %H:%M:%S')}
            """
            await update.message.reply_text(mute_text, parse_mode='HTML')
            
        except Exception as e:
            await update.message.reply_text(
                config.RESPONSES["command_failed"].format(error=str(e))
            )
    
    async def unmute_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unmute a user."""
        if not await self._is_admin(update, context):
            await update.message.reply_text(config.RESPONSES["no_permission"])
            return
        
        if not context.args:
            await update.message.reply_text(
                config.RESPONSES["no_user_mentioned"].format(usage="/unmute @username")
            )
            return
        
        target_user = await self._get_mentioned_user(update, context)
        if not target_user:
            await update.message.reply_text(config.RESPONSES["user_not_found"])
            return
        
        user_id = target_user.id
        
        # Restore normal permissions
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=permissions
            )
            
            if user_id in self.muted_users:
                del self.muted_users[user_id]
            
            await update.message.reply_text(
                f"🔊 {target_user.mention_html()} has been unmuted! Welcome back! 🎉",
                parse_mode='HTML'
            )
            
        except Exception as e:
            await update.message.reply_text(
                config.RESPONSES["command_failed"].format(error=str(e))
            )
    
    async def ban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ban a user from the group."""
        if not await self._is_admin(update, context):
            await update.message.reply_text(config.RESPONSES["no_permission"])
            return
        
        if not context.args:
            await update.message.reply_text(
                config.RESPONSES["no_user_mentioned"].format(usage="/ban @username")
            )
            return
        
        target_user = await self._get_mentioned_user(update, context)
        if not target_user:
            await update.message.reply_text(config.RESPONSES["user_not_found"])
            return
        
        await self.ban_user_manual(update, context, target_user, "Banned by admin")
    
    async def ban_user_manual(self, update: Update, context: ContextTypes.DEFAULT_TYPE, target_user, reason):
        """Manual ban function with reason."""
        try:
            await context.bot.ban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=target_user.id
            )
            
            ban_text = f"""
🚫 *User Banned* 🚫

User: {target_user.mention_html()}
Reason: {reason}
Banned by: {update.effective_user.mention_html()}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            await update.message.reply_text(ban_text, parse_mode='HTML')
            
        except Exception as e:
            await update.message.reply_text(
                config.RESPONSES["command_failed"].format(error=str(e))
            )
    
    async def kick_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Kick a user from the group."""
        if not await self._is_admin(update, context):
            await update.message.reply_text(config.RESPONSES["no_permission"])
            return
        
        if not context.args:
            await update.message.reply_text(
                config.RESPONSES["no_user_mentioned"].format(usage="/kick @username")
            )
            return
        
        target_user = await self._get_mentioned_user(update, context)
        if not target_user:
            await update.message.reply_text(config.RESPONSES["user_not_found"])
            return
        
        try:
            await context.bot.ban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=target_user.id,
                until_date=datetime.now() + timedelta(seconds=30)  # Unban after 30 seconds
            )
            
            await update.message.reply_text(
                f"👢 {target_user.mention_html()} has been kicked from the group!",
                parse_mode='HTML'
            )
            
        except Exception as e:
            await update.message.reply_text(
                config.RESPONSES["command_failed"].format(error=str(e))
            )
    
    async def check_warnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check warnings for a user."""
        if not context.args:
            await update.message.reply_text(
                config.RESPONSES["no_user_mentioned"].format(usage="/warnings @username")
            )
            return
        
        target_user = await self._get_mentioned_user(update, context)
        if not target_user:
            await update.message.reply_text(config.RESPONSES["user_not_found"])
            return
        
        user_id = target_user.id
        warning_count = len(self.warned_users.get(user_id, []))
        
        warnings_text = f"""
📊 *Warning Status* 📊

User: {target_user.mention_html()}
Total Warnings: {warning_count}
Status: {"⚠️ Close to ban!" if warning_count >= config.MAX_WARNINGS - 1 else "✅ Good standing"}
Max Warnings: {config.MAX_WARNINGS}
        """
        await update.message.reply_text(warnings_text, parse_mode='HTML')
    
    async def anti_spam(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Anti-spam protection."""
        user_id = update.effective_user.id
        current_time = datetime.now()
        
        # Check if user is sending messages too quickly
        if user_id in self.last_message:
            time_diff = (current_time - self.last_message[user_id]).total_seconds()
            if time_diff < config.ANTI_SPAM_COOLDOWN:
                # Warn user about spam
                await update.message.reply_text(
                    config.RESPONSES["spam_warning"].format(user=update.effective_user.mention_html()),
                    parse_mode='HTML'
                )
                return
        
        self.last_message[user_id] = current_time
    
    async def _is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if the user is an admin."""
        user_id = update.effective_user.id
        
        # Check if user is in admin list
        if user_id in config.ADMIN_IDS:
            return True
        
        # Check if user is admin in the group
        try:
            chat_member = await context.bot.get_chat_member(
                update.effective_chat.id,
                user_id
            )
            return chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        except:
            return False
    
    async def _get_mentioned_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Extract mentioned user from command."""
        try:
            if update.message.reply_to_message:
                return update.message.reply_to_message.from_user
            
            if context.args:
                username = context.args[0].lstrip('@')
                # This is a simplified version - in production, you'd want to implement
                # proper user resolution through Telegram's API
                return type('User', (), {'id': 0, 'mention_html': lambda: username})()
        
        except Exception as e:
            logger.error(f"Error getting mentioned user: {e}")
        
        return None
    
    def cleanup_old_data(self):
        """Clean up old warnings and mutes."""
        current_time = datetime.now()
        
        # Clean old warnings (older than configured hours)
        for user_id in list(self.warned_users.keys()):
            self.warned_users[user_id] = [
                warn_time for warn_time in self.warned_users[user_id]
                if (current_time - warn_time) < timedelta(hours=config.WARNING_EXPIRE_HOURS)
            ]
            if not self.warned_users[user_id]:
                del self.warned_users[user_id]
        
        # Clean expired mutes
        for user_id in list(self.muted_users.keys()):
            if current_time > self.muted_users[user_id]:
                del self.muted_users[user_id]

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    manager = AnimeGroupManager()
    
    # Add handlers
    application.add_handler(CommandHandler("start", manager.start))
    application.add_handler(CommandHandler("help", manager.help_command))
    application.add_handler(CommandHandler("quote", manager.send_quote))
    application.add_handler(CommandHandler("rules", manager.show_rules))
    application.add_handler(CommandHandler("warn", manager.warn_user))
    application.add_handler(CommandHandler("mute", manager.mute_user))
    application.add_handler(CommandHandler("unmute", manager.unmute_user))
    application.add_handler(CommandHandler("ban", manager.ban_user))
    application.add_handler(CommandHandler("kick", manager.kick_user))
    application.add_handler(CommandHandler("warnings", manager.check_warnings))
    
    # Welcome new members
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS, 
        manager.welcome_new_member
    ))
    
    # Anti-spam for all messages
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        manager.anti_spam
    ))
    
    # Start the Bot
    logger.info("🌸 Anime Guardian Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
