import logging
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from telegram import Update, ChatMember, ChatPermissions, Poll
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackContext, ChatMemberHandler, PollHandler
)

from config import config
from database import AnimeBotDatabase

# Set up logging
logging.basicConfig(
    format=config.LOG_FORMAT,
    level=getattr(logging, config.LOG_LEVEL)
)
logger = logging.getLogger(__name__)

class AnimeGroupManager:
    def __init__(self):
        self.db = AnimeBotDatabase(config.DATABASE_NAME)
        self.last_xp_gain: Dict[int, datetime] = {}
        self.anime_quiz = self._init_quiz()
        self.auto_delete_tasks: List[asyncio.Task] = []
        self.start_time = datetime.now()
    
    def _init_quiz(self):
        """Initialize quiz questions."""
        return {
            "questions": [
                {
                    "question": "Who is the main character in 'Attack on Titan'?",
                    "options": ["Eren Yeager", "Levi Ackerman", "Mikasa Ackerman", "Armin Arlert"],
                    "correct": 0
                },
                {
                    "question": "What is the name of Luffy's pirate crew?",
                    "options": ["Straw Hat Pirates", "Red Hair Pirates", "Whitebeard Pirates", "Blackbeard Pirates"],
                    "correct": 0
                }
            ],
            "active_quizzes": {}
        }

    # === BASIC COMMANDS ===
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message."""
        user = update.effective_user
        welcome_text = f"""
🌸 *Anime Guardian Bot* 🌸

Konnichiwa {user.mention_html()}! I'm your anime-themed group management bot!

*Database Features:*
• 🎯 Persistent Level System
• 📊 User Statistics Tracking  
• ⚠️ Warning History
• 🏆 Leaderboard Rankings

Use /help to see all commands!
        """
        await update.message.reply_text(welcome_text, parse_mode='HTML')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        help_text = """
🎌 *Anime Guardian Bot - SQLite3 Version* 🎌

*Admin Commands:*
/warn @user - Warn a user
/mute @user - Mute a user  
/unmute @user - Unmute a user
/ban @user - Ban a user
/kick @user - Kick a user
/warnings - Check warnings

*Database Features:*
/level - Check your level
/leaderboard - Show top users
/stats - Group statistics  
/userstats - User statistics
/character <name> - Character info

*Basic Commands:*
/start - Welcome message
/help - This message
/quote - Random anime quote
/rules - Group rules
        """
        await update.message.reply_text(help_text, parse_mode='HTML')
    
    async def send_quote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a random anime quote."""
        quote = random.choice(config.ANIME_QUOTES)
        await update.message.reply_text(f"💫 *Anime Quote of the Moment:*\n\n{quote}", parse_mode='HTML')
    
    async def show_rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show group rules."""
        rules_text = """
📜 *Anime Community Rules* 📜

1. 🤝 *Be Respectful* - Treat everyone with respect
2. 🎭 *Stay On Topic* - Keep discussions anime-related
3. 🚫 *No Spam* - Don't flood the chat
4. 📛 *No NSFW* - Keep content safe for work
5. 🔗 *No Unsolicited Links* - Ask before posting links
6. 👥 *No Harassment* - Bullying won't be tolerated
7. 🎨 *Credit Artists* - Always credit fan art creators

*Violations may result in warnings, mutes, or bans.*
        """
        await update.message.reply_text(rules_text, parse_mode='HTML')

    # === WELCOME SYSTEM ===
    async def welcome_new_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome new members with anime-themed message and image."""
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                await update.message.reply_text(config.RESPONSES["welcome_bot"])
            else:
                await self._send_welcome_with_image(update, context, member)
    
    async def _send_welcome_with_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE, member):
        """Send welcome message with anime image."""
        welcome_msg = random.choice(config.ANIME_WELCOME_MESSAGES).format(
            user=member.mention_html()
        )
        
        full_welcome_text = f"""
{welcome_msg}

🏮 *New Features* 🏮
• Level System: Chat to earn XP
• Anime Quizzes: Test your knowledge  
• Character Info: Learn about anime characters
• Database: All data is now saved!

Use /help to explore all features!
        """
        
        if config.ENABLE_WELCOME_IMAGE:
            try:
                image_url = random.choice(config.WELCOME_IMAGE_URLS)
                
                if config.WELCOME_IMAGE_CAPTION:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=image_url,
                        caption=full_welcome_text,
                        parse_mode='HTML'
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=image_url
                    )
                    await update.message.reply_text(full_welcome_text, parse_mode='HTML')
                    
            except Exception as e:
                logger.error(f"Failed to send welcome image: {e}")
                await update.message.reply_text(
                    f"{config.RESPONSES['image_send_failed']}\n\n{full_welcome_text}",
                    parse_mode='HTML'
                )
        else:
            await update.message.reply_text(full_welcome_text, parse_mode='HTML')

    # === LEVEL SYSTEM ===
    async def handle_level_system(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle XP gain and level system."""
        if not config.LEVEL_CONFIG["ENABLE_LEVEL_SYSTEM"]:
            return
        
        user_id = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""
        current_time = datetime.now()
        
        # Check cooldown
        if user_id in self.last_xp_gain:
            time_diff = (current_time - self.last_xp_gain[user_id]).total_seconds()
            if time_diff < config.LEVEL_CONFIG["XP_COOLDOWN"]:
                return
        
        # Add XP to database
        level, xp, leveled_up = self.db.add_user_xp(
            user_id, username, first_name, config.LEVEL_CONFIG["XP_PER_MESSAGE"]
        )
        
        self.last_xp_gain[user_id] = current_time
        
        # Send level up message
        if leveled_up:
            level_up_msg = random.choice(config.LEVEL_CONFIG["LEVEL_UP_MESSAGES"]).format(
                user=update.effective_user.mention_html(),
                level=level
            )
            await update.message.reply_text(level_up_msg, parse_mode='HTML')
    
    async def level_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check user level."""
        user_id = update.effective_user.id
        level, xp = self.db.get_user_level(user_id)
        rank = self.db.get_user_rank(user_id)
        
        # Calculate XP for next level
        next_level_xp = 100 * (level ** 2)
        xp_needed = next_level_xp - xp
        
        level_text = f"""
🎯 *Level Info* 🎯

User: {update.effective_user.mention_html()}
Level: {level} 🏅
XP: {xp} ⭐
Rank: #{rank}
XP to next level: {xp_needed}

Keep chatting to level up! 💪
        """
        await update.message.reply_text(level_text, parse_mode='HTML')
    
    async def leaderboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show leaderboard."""
        leaderboard = self.db.get_leaderboard(10)
        
        if not leaderboard:
            await update.message.reply_text("📊 No users on leaderboard yet!")
            return
        
        leaderboard_text = "🏆 *Anime Community Leaderboard* 🏆\n\n"
        for i, user in enumerate(leaderboard, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            username = user['username'] or user['first_name'] or f"User{user['user_id']}"
            leaderboard_text += f"{medal} {username} - Level {user['level']} (XP: {user['xp']})\n"
        
        await update.message.reply_text(leaderboard_text, parse_mode='HTML')

    # === CHARACTER SYSTEM ===
    async def character_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get anime character information."""
        if not context.args:
            characters_list = " | ".join([f"`{char}`" for char in config.ANIME_CHARACTERS.keys()])
            await update.message.reply_text(
                f"Available characters: {characters_list}\n"
                f"Usage: `/character naruto`"
            )
            return
        
        character_name = context.args[0].lower()
        character = config.ANIME_CHARACTERS.get(character_name)
        
        if not character:
            await update.message.reply_text("❌ Character not found! Use `/characters` to see available characters.")
            return
        
        character_text = f"""
🎭 *{character['name']}* 🎭

*Series:* {character['series']}
*Quote:* "{character['quote']}"
*Description:* {character['description']}
        """
        
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=character['image'],
                caption=character_text,
                parse_mode='HTML'
            )
        except:
            await update.message.reply_text(character_text, parse_mode='HTML')

    # === WARNING SYSTEM ===
    async def warn_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Warn a user with database storage."""
        if not await self._is_admin(update, context):
            await update.message.reply_text(config.RESPONSES["no_permission"])
            return
        
        if not context.args:
            await update.message.reply_text(
                config.RESPONSES["no_user_mentioned"].format(usage="/warn @username [reason]")
            )
            return
        
        target_user = await self._get_mentioned_user(update, context)
        if not target_user:
            await update.message.reply_text(config.RESPONSES["user_not_found"])
            return
        
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
        
        # Add warning to database
        self.db.add_warning(
            user_id=target_user.id,
            chat_id=update.effective_chat.id,
            warned_by=update.effective_user.id,
            reason=reason
        )
        
        warning_count = self.db.get_warning_count(target_user.id, update.effective_chat.id)
        
        warning_text = f"""
⚠️ *Warning Issued* ⚠️

User: {target_user.mention_html()}
Warnings: {warning_count}/{config.MAX_WARNINGS}
Reason: {reason}
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
            self.db.clear_warnings(target_user.id, update.effective_chat.id)
    
    async def warnings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check warnings for a user."""
        if not context.args:
            # Show own warnings
            user_id = update.effective_user.id
            warnings = self.db.get_user_warnings(user_id, update.effective_chat.id)
            warning_count = len(warnings)
            
            warnings_text = f"""
📊 *Your Warnings* 📊

Total Warnings: {warning_count}/{config.MAX_WARNINGS}
Status: {"⚠️ Close to ban!" if warning_count >= config.MAX_WARNINGS - 1 else "✅ Good standing"}
            """
            
            if warnings:
                warnings_text += "\n*Recent Warnings:*\n"
                for i, warn in enumerate(warnings[:5], 1):
                    warnings_text += f"{i}. {warn['reason']} ({warn['created_at'][:10]})\n"
            
            await update.message.reply_text(warnings_text, parse_mode='HTML')
            return
        
        target_user = await self._get_mentioned_user(update, context)
        if not target_user:
            await update.message.reply_text(config.RESPONSES["user_not_found"])
            return
        
        warnings = self.db.get_user_warnings(target_user.id, update.effective_chat.id)
        warning_count = len(warnings)
        
        warnings_text = f"""
📊 *Warning Status* 📊

User: {target_user.mention_html()}
Total Warnings: {warning_count}/{config.MAX_WARNINGS}
Status: {"⚠️ Close to ban!" if warning_count >= config.MAX_WARNINGS - 1 else "✅ Good standing"}
        """
        
        await update.message.reply_text(warnings_text, parse_mode='HTML')

    # === MODERATION COMMANDS ===
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
        
        # Add mute to database
        self.db.add_mute(
            user_id=user_id,
            chat_id=update.effective_chat.id,
            muted_by=update.effective_user.id,
            duration_hours=config.MUTE_DURATION_HOURS
        )
        
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
        
        # Remove from database
        self.db.remove_mute(user_id, update.effective_chat.id)
        
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
                until_date=datetime.now() + timedelta(seconds=30)
            )
            
            await update.message.reply_text(
                f"👢 {target_user.mention_html()} has been kicked from the group!",
                parse_mode='HTML'
            )
            
        except Exception as e:
            await update.message.reply_text(
                config.RESPONSES["command_failed"].format(error=str(e))
            )

    # === STATISTICS COMMANDS ===
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show group statistics."""
        chat_stats = self.db.get_chat_stats(update.effective_chat.id)
        total_users = len(self.db.get_leaderboard(1000))
        
        stats_text = f"""
📈 *Group Statistics* 📈

*Total Members:* {total_users}
*Total Warnings Issued:* {chat_stats['total_warnings']}
*Active Mutes:* {chat_stats['active_mutes']}
*Level System:* {'✅ Enabled' if config.LEVEL_CONFIG['ENABLE_LEVEL_SYSTEM'] else '❌ Disabled'}

*Bot Uptime:* {self._get_uptime()}
        """
        await update.message.reply_text(stats_text, parse_mode='HTML')
    
    async def userstats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics."""
        if context.args:
            target_user = await self._get_mentioned_user(update, context)
            if not target_user:
                await update.message.reply_text(config.RESPONSES["user_not_found"])
                return
            user_id = target_user.id
            username = target_user.first_name
        else:
            user_id = update.effective_user.id
            username = update.effective_user.first_name
        
        user_stats = self.db.get_user_stats(user_id)
        level, xp = self.db.get_user_level(user_id)
        rank = self.db.get_user_rank(user_id)
        
        stats_text = f"""
📊 *User Statistics* 📊

User: {username}
Level: {level} (Rank: #{rank})
XP: {xp}
Messages: {user_stats.get('messages_count', 0)}
Warnings: {user_stats.get('total_warnings', 0)}
Mutes: {user_stats.get('mutes_count', 0)}
        """
        await update.message.reply_text(stats_text, parse_mode='HTML')

    # === UTILITY METHODS ===
    async def ban_user_manual(self, update: Update, context: ContextTypes.DEFAULT_TYPE, target_user, reason):
        """Manual ban function."""
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
    
    async def _is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if user is admin."""
        user_id = update.effective_user.id
        
        if user_id in config.ADMIN_IDS:
            return True
        
        try:
            chat_member = await context.bot.get_chat_member(
                update.effective_chat.id,
                user_id
            )
            return chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        except:
            return False
    
    async def _get_mentioned_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Extract mentioned user."""
        try:
            if update.message.reply_to_message:
                return update.message.reply_to_message.from_user
            
            if context.args:
                # Simple implementation
                username = context.args[0].lstrip('@')
                return type('User', (), {
                    'id': hash(username),  # Simple hash for demo
                    'first_name': username,
                    'mention_html': lambda: f"@{username}"
                })()
        except Exception as e:
            logger.error(f"Error getting mentioned user: {e}")
        
        return None
    
    def _get_uptime(self) -> str:
        """Get bot uptime."""
        uptime = datetime.now() - self.start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m {seconds}s"
    
    # === ANTI-SPAM ===
    async def anti_spam(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Anti-spam protection."""
        user_id = update.effective_user.id
        current_time = datetime.now()
        
        # Check if user is sending messages too quickly
        if user_id in self.last_xp_gain:  # Reusing this dict for spam detection
            time_diff = (current_time - self.last_xp_gain[user_id]).total_seconds()
            if time_diff < config.ANTI_SPAM_COOLDOWN:
                await update.message.reply_text(
                    config.RESPONSES["spam_warning"].format(user=update.effective_user.mention_html()),
                    parse_mode='HTML'
                )
                return
        
        self.last_xp_gain[user_id] = current_time
    
    async def run_cleanup_tasks(self):
        """Run periodic database cleanup."""
        while True:
            self.db.cleanup_old_data(30)
            await asyncio.sleep(24 * 3600)

def main():
    """Start the bot."""
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    manager = AnimeGroupManager()
    
    # Add handlers
    application.add_handler(CommandHandler("start", manager.start))
    application.add_handler(CommandHandler("help", manager.help_command))
    application.add_handler(CommandHandler("quote", manager.send_quote))
    application.add_handler(CommandHandler("rules", manager.show_rules))
    
    # Database feature handlers
    application.add_handler(CommandHandler("level", manager.level_command))
    application.add_handler(CommandHandler("leaderboard", manager.leaderboard_command))
    application.add_handler(CommandHandler("character", manager.character_command))
    application.add_handler(CommandHandler("stats", manager.stats_command))
    application.add_handler(CommandHandler("userstats", manager.userstats_command))
    
    # Moderation handlers
    application.add_handler(CommandHandler("warn", manager.warn_user))
    application.add_handler(CommandHandler("warnings", manager.warnings_command))
    application.add_handler(CommandHandler("mute", manager.mute_user))
    application.add_handler(CommandHandler("unmute", manager.unmute_user))
    application.add_handler(CommandHandler("ban", manager.ban_user))
    application.add_handler(CommandHandler("kick", manager.kick_user))
    
    # Message handlers
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS, 
        manager.welcome_new_member
    ))
    
    # Level system handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        manager.handle_level_system
    ))
    
    # Anti-spam handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        manager.anti_spam
    ))
    
    # Start cleanup tasks
    asyncio.get_event_loop().create_task(manager.run_cleanup_tasks())
    
    logger.info("🌸 Anime Guardian Bot with SQLite3 is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
