import os
import logging
import tempfile
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import aria2p
import requests
from urllib.parse import urlparse
import re
import magic
from pathlib import Path

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = "8326289617:AAGl1Lu0r3-HAgfVQHNTR--n-3X1C5v_51k"
ADMIN_IDS = [6300568870]  # Replace with your Telegram ID

# Aria2 Configuration
ARIA2_HOST = "localhost"
ARIA2_PORT = 6800
ARIA2_SECRET = ""  # Leave empty if no secret

class TorrentBot:
    def __init__(self):
        self.aria2 = None
        self.download_dir = "downloads"
        self.max_file_size = 50 * 1024 * 1024  # 50MB Telegram limit
        
        # Create download directory
        os.makedirs(self.download_dir, exist_ok=True)
        
    async def initialize_aria2(self):
        """Initialize Aria2 connection"""
        try:
            self.aria2 = aria2p.API(
                aria2p.Client(
                    host=ARIA2_HOST,
                    port=ARIA2_PORT,
                    secret=ARIA2_SECRET
                )
            )
            # Test connection
            self.aria2.get_version()
            logger.info("Aria2 connection established")
            return True
        except Exception as e:
            logger.error(f"Aria2 connection failed: {e}")
            return False

    def is_magnet_link(self, text):
        """Check if text is a magnet link"""
        return text.startswith('magnet:?')

    def is_torrent_url(self, text):
        """Check if text is a torrent URL"""
        return text.endswith('.torrent') or 'torrent' in text.lower()

    def is_valid_url(self, text):
        """Check if text is a valid URL"""
        try:
            result = urlparse(text)
            return all([result.scheme, result.netloc])
        except:
            return False

    async def start(self, update: Update, context: CallbackContext):
        """Send welcome message"""
        welcome_text = """
🤖 **Torrent Download Bot**

**Features:**
• Download from magnet links 🧲
• Download from torrent URLs 🌐
• Convert to Telegram documents 📄
• Real-time download progress 📊

**Commands:**
/start - Show this message
/help - Get help
/download - Download from magnet or URL
/status - Check download status
/cancel - Cancel current download

**How to use:**
1. Send a magnet link
2. Send a torrent URL
3. Use /download command

**Supported formats:** MP4, MP3, PDF, DOC, TXT, and more!
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    async def help_command(self, update: Update, context: CallbackContext):
        """Send help message"""
        help_text = """
📖 **Help Guide**

**Supported Inputs:**
- Magnet links: `magnet:?xt=urn:btih:...`
- Torrent URLs: `http://example.com/file.torrent`
- Direct file URLs

**Download Process:**
1. Send magnet link or torrent URL
2. Bot will start downloading
3. Select files to send to Telegram
4. Receive your files!

**File Limits:**
- Maximum file size: 50MB (Telegram limit)
- Supported formats: Most common file types

**Need help?** Contact the admin!
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def handle_message(self, update: Update, context: CallbackContext):
        """Handle incoming messages"""
        user_id = update.message.from_user.id
        text = update.message.text.strip()

        # Check if message contains magnet or URL
        if self.is_magnet_link(text) or self.is_torrent_url(text) or self.is_valid_url(text):
            await self.start_download(update, context, text)
        else:
            await update.message.reply_text(
                "❌ Please send a valid magnet link or torrent URL.\n"
                "Use /help for more information."
            )

    async def start_download(self, update: Update, context: CallbackContext, link: str):
        """Start download process"""
        user_id = update.message.from_user.id
        
        # Initialize Aria2 if not connected
        if not self.aria2:
            if not await self.initialize_aria2():
                await update.message.reply_text("❌ Download service unavailable. Please try again later.")
                return

        try:
            # Send initial message
            status_msg = await update.message.reply_text("⏳ Starting download...")
            
            # Start download
            if self.is_magnet_link(link):
                download = self.aria2.add_magnet(link)
            else:
                download = self.aria2.add_uris([link])
            
            context.user_data['current_download'] = download.gid
            context.user_data['status_message'] = status_msg
            
            # Start progress tracking
            asyncio.create_task(self.track_progress(update, context, download.gid))
            
        except Exception as e:
            logger.error(f"Download start error: {e}")
            await update.message.reply_text(f"❌ Download failed: {str(e)}")

    async def track_progress(self, update: Update, context: CallbackContext, gid: str):
        """Track download progress"""
        try:
            download = self.aria2.get_download(gid)
            last_progress = 0
            
            while download.is_active:
                await asyncio.sleep(2)
                download = self.aria2.get_download(gid)
                
                if download.status == "active":
                    progress = int(download.progress)
                    if progress != last_progress:
                        # Update progress message every 10% or when complete
                        if progress % 10 == 0 or progress == 100:
                            status_text = (
                                f"📥 Downloading: {progress}%\n"
                                f"📊 Speed: {download.download_speed / 1024 / 1024:.2f} MB/s\n"
                                f"⏰ ETA: {download.eta}"
                            )
                            await context.user_data['status_message'].edit_text(status_text)
                        last_progress = progress
                
                elif download.status == "complete":
                    await context.user_data['status_message'].edit_text("✅ Download complete! Processing files...")
                    await self.process_downloaded_files(update, context, download)
                    break
                
                elif download.status == "error":
                    await context.user_data['status_message'].edit_text("❌ Download failed")
                    break
                    
        except Exception as e:
            logger.error(f"Progress tracking error: {e}")
            await context.user_data['status_message'].edit_text("❌ Download error occurred")

    async def process_downloaded_files(self, update: Update, context: CallbackContext, download):
        """Process downloaded files and send to user"""
        try:
            files = []
            for file in download.files:
                file_path = file.path
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    
                    if file_size <= self.max_file_size:
                        files.append({
                            'path': file_path,
                            'name': os.path.basename(file_path),
                            'size': file_size
                        })
            
            if not files:
                await update.message.reply_text("❌ No suitable files found or files are too large.")
                return
            
            # Send files one by one
            for file_info in files:
                if file_info['size'] <= self.max_file_size:
                    await self.send_file(update, file_info['path'], file_info['name'])
                    await asyncio.sleep(1)  # Rate limiting
            
            await update.message.reply_text("✅ All files sent successfully!")
            
            # Cleanup
            self.cleanup_download(download)
            
        except Exception as e:
            logger.error(f"File processing error: {e}")
            await update.message.reply_text("❌ Error processing files")

    async def send_file(self, update: Update, file_path: str, filename: str):
        """Send file to user"""
        try:
            # Detect file type
            mime = magic.Magic(mime=True)
            file_type = mime.from_file(file_path)
            
            with open(file_path, 'rb') as file:
                if file_type.startswith('video/'):
                    await update.message.reply_video(
                        video=file,
                        caption=f"🎥 {filename}",
                        filename=filename
                    )
                elif file_type.startswith('audio/'):
                    await update.message.reply_audio(
                        audio=file,
                        caption=f"🎵 {filename}",
                        filename=filename,
                        title=os.path.splitext(filename)[0]
                    )
                elif file_type.startswith('image/'):
                    await update.message.reply_photo(
                        photo=file,
                        caption=f"🖼️ {filename}"
                    )
                elif file_type in ['application/pdf', 'application/msword', 
                                 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                    await update.message.reply_document(
                        document=file,
                        caption=f"📄 {filename}",
                        filename=filename
                    )
                else:
                    await update.message.reply_document(
                        document=file,
                        caption=f"📁 {filename}",
                        filename=filename
                    )
                    
        except Exception as e:
            logger.error(f"File send error: {e}")
            await update.message.reply_text(f"❌ Failed to send {filename}")

    def cleanup_download(self, download):
        """Clean up downloaded files"""
        try:
            # Remove files
            for file in download.files:
                if os.path.exists(file.path):
                    os.remove(file.path)
            
            # Remove from aria2
            self.aria2.remove([download])
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def cancel_download(self, update: Update, context: CallbackContext):
        """Cancel current download"""
        user_id = update.message.from_user.id
        
        if 'current_download' in context.user_data:
            try:
                download = self.aria2.get_download(context.user_data['current_download'])
                self.aria2.remove([download])
                del context.user_data['current_download']
                await update.message.reply_text("✅ Download cancelled")
            except Exception as e:
                await update.message.reply_text("❌ Error cancelling download")
        else:
            await update.message.reply_text("❌ No active download to cancel")

    async def status_command(self, update: Update, context: CallbackContext):
        """Check download status"""
        if 'current_download' in context.user_data:
            try:
                download = self.aria2.get_download(context.user_data['current_download'])
                status_text = (
                    f"📊 Download Status:\n"
                    f"Progress: {int(download.progress)}%\n"
                    f"Speed: {download.download_speed / 1024 / 1024:.2f} MB/s\n"
                    f"ETA: {download.eta}\n"
                    f"Status: {download.status}"
                )
                await update.message.reply_text(status_text)
            except Exception as e:
                await update.message.reply_text("❌ Error getting download status")
        else:
            await update.message.reply_text("❌ No active downloads")

def main():
    """Start the bot"""
    bot = TorrentBot()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("download", bot.handle_message))
    application.add_handler(CommandHandler("cancel", bot.cancel_download))
    application.add_handler(CommandHandler("status", bot.status_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    # Start bot
    logger.info("Bot starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
