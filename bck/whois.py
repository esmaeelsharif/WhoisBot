#!/usr/bin/env python3
import logging
import subprocess
import os
import re
import json
import html
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("whois_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7802439345:AAGBzFUgO7IeApWvWRfIDMOSDfxvj2Br9Pg")
SERVER_IP = os.environ.get("SERVER_IP", "91.107.169.46")
ROOT_PASSWORD = os.environ.get("ROOT_PASSWORD", "")  # Get from environment variable
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "402031454"))
DOMAIN_REGISTER_URL = "https://www.hostinger.com/domain-name-search"

# Data directory
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# File paths
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

# Recent searches cache
recent_searches = []
MAX_RECENT_SEARCHES = 5

# User tracking
users = set()

# Conversation states
BROADCAST_MESSAGE = 1

# Function to escape HTML special characters
def escape_html(text):
    """Escape HTML special characters in text."""
    if not text:
        return ""
    
    # Convert text to string if it's not already
    text = str(text)
    
    # Use Python's built-in html.escape function
    return html.escape(text)

# Load configuration from file if exists
def load_config():
    """Load configuration from file."""
    config = {}
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            logger.info("Configuration loaded from file")
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
    return config

# Save configuration to file
def save_config(config):
    """Save configuration to file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
        logger.info("Configuration saved to file")
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")

# Define command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    user_id = user.id
    
    # Add user to the users set for tracking
    users.add(user_id)
    save_users()
    
    welcome_message = (
        f"👋 Hello, {user.first_name}!\n\n"
        f"Welcome to the Domain WHOIS Bot. I can help you look up WHOIS information for any domain.\n\n"
        f"Simply send me a domain name like 'example.com' and I'll provide options to check its details.\n\n"
        f"Type /help to see all available commands."
    )
    
    # Create keyboard with buttons
    keyboard = [
        [InlineKeyboardButton("🔍 How to use", callback_data="how_to_use")],
        [InlineKeyboardButton("ℹ️ About WHOIS", callback_data="about_whois")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "📚 <b>WHOIS Bot Commands</b>\n\n"
        "• Send any domain name (e.g., <code>example.com</code>) to see available options\n"
        "• /start - Start the bot and see welcome message\n"
        "• /help - Show this help message\n"
        "• /recent - Show your recent WHOIS lookups\n"
        "• /about - Learn more about this bot\n\n"
        "Example: Just type <code>example.com</code> (without quotes) to get started."
    )
    
    # Add admin commands if the user is an admin
    if update.effective_user.id == ADMIN_USER_ID:
        help_text += "\n\n<b>Admin Commands:</b>\n"
        help_text += "• /stats - Show bot statistics\n"
        help_text += "• /broadcast - Send a message to all users\n"
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send information about the bot."""
    about_text = (
        "🤖 <b>About WHOIS Bot</b>\n\n"
        "This bot allows you to quickly look up domain registration information (WHOIS data) "
        "for any domain name.\n\n"
        "WHOIS data typically includes:\n"
        "• Domain registrar information\n"
        "• Registration and expiration dates\n"
        "• Name servers\n"
        "• Registrant information (when available)\n\n"
        "The bot uses the server's WHOIS command for accurate, up-to-date results."
    )
    await update.message.reply_text(about_text, parse_mode=ParseMode.HTML)

async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent searches."""
    user_id = update.effective_user.id
    user_searches = [s for s in recent_searches if s["user_id"] == user_id]
    
    if not user_searches:
        await update.message.reply_text("You haven't made any WHOIS lookups yet.")
        return
    
    message = "🕒 <b>Your Recent Lookups</b>\n\n"
    for search in user_searches[:MAX_RECENT_SEARCHES]:
        time_str = search["time"].strftime("%Y-%m-%d %H:%M:%S")
        message += f"• <code>{escape_html(search['domain'])}</code> - {time_str}\n"
    
    # Add buttons to re-search these domains
    keyboard = []
    for search in user_searches[:MAX_RECENT_SEARCHES]:
        keyboard.append([InlineKeyboardButton(f"🔍 {search['domain']}", 
                                             callback_data=f"domain_{search['domain']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot statistics (admin only)."""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("Sorry, this command is only available to administrators.")
        return
    
    total_users = len(users)
    total_searches = len(recent_searches)
    
    stats_text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"• Total users: {total_users}\n"
        f"• Total searches: {total_searches}\n\n"
        f"<i>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
    )
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the broadcast message process (admin only)."""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("Sorry, this command is only available to administrators.")
        return
    
    await update.message.reply_text(
        "Please enter the message you want to send to all users:\n\n"
        "Type /cancel to cancel the broadcast."
    )
    
    return BROADCAST_MESSAGE

async def process_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the broadcast message and send to all users."""
    message_text = update.message.text
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        return ConversationHandler.END
    
    if message_text == "/cancel":
        await update.message.reply_text("Broadcast canceled.")
        return ConversationHandler.END
    
    # Send confirmation
    await update.message.reply_text(f"Sending message to {len(users)} users...")
    
    # Broadcast message to all users
    success_count = 0
    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 <b>Announcement from WHOIS Bot</b>\n\n{escape_html(message_text)}",
                parse_mode=ParseMode.HTML
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
    
    await update.message.reply_text(
        f"✅ Message sent to {success_count} out of {len(users)} users."
    )
    
    return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation."""
    await update.message.reply_text("Operation canceled.")
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "how_to_use":
        how_to_text = (
            "<b>📝 How to use this bot:</b>\n\n"
            "1. Simply type a domain name like <code>example.com</code>\n"
            "2. The bot will show you buttons to check:\n"
            "   • WHOIS information\n"
            "   • DNS information\n"
            "   • Expiration date\n"
            "3. Click on any button to see the specific information\n\n"
            "Try it now by sending a domain name!"
        )
        await query.edit_message_text(text=how_to_text, parse_mode=ParseMode.HTML)
    
    elif query.data == "about_whois":
        about_whois_text = (
            "<b>🔍 What is WHOIS?</b>\n\n"
            "WHOIS is a query and response protocol used for querying databases that store "
            "the registered users of an Internet resource, such as a domain name or IP address.\n\n"
            "When you search for a domain, you can see details like:\n"
            "• Who registered the domain\n"
            "• When it was registered\n"
            "• When it expires\n"
            "• DNS servers\n"
            "• Contact information (when public)"
        )
        await query.edit_message_text(text=about_whois_text, parse_mode=ParseMode.HTML)
    
    elif query.data.startswith("domain_"):
        domain = query.data[7:]  # Remove "domain_" prefix
        
        # Show options when domain is entered
        keyboard = [
            [InlineKeyboardButton("🔎 View WHOIS", callback_data=f"whois_{domain}")],
            [InlineKeyboardButton("🌐 View DNS Info", callback_data=f"dns_{domain}")],
            [InlineKeyboardButton("📅 View Expiry Date", callback_data=f"expiry_{domain}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=f"What would you like to know about <b>{escape_html(domain)}</b>?",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    
    elif query.data.startswith("whois_"):
        domain = query.data[6:]  # Remove "whois_" prefix
        await query.edit_message_text(text=f"Looking up WHOIS for {domain}...")
        
        try:
            whois_output = get_whois_info(domain)
            
            # Check if domain is available
            is_available = check_domain_availability(whois_output)
            
            if is_available:
                # Domain is available
                keyboard = [
                    [InlineKeyboardButton("🛒 Register This Domain", url=DOMAIN_REGISTER_URL)],
                    [InlineKeyboardButton("🔍 Search another domain", callback_data="how_to_use")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text=f"✅ <b>Good news!</b> The domain <b>{escape_html(domain)}</b> appears to be available for registration.\n\n"
                    "You can register it by clicking the button below.",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            else:
                # Domain is registered - show WHOIS info
                # Format the output
                formatted_output = format_whois_output(domain, whois_output)
                
                # Create back button
                keyboard = [
                    [InlineKeyboardButton("◀️ Back to options", callback_data=f"domain_{domain}")],
                    [InlineKeyboardButton("🔍 Search another domain", callback_data="how_to_use")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Split if necessary
                if len(formatted_output) > 4000:
                    chunks = [formatted_output[i:i+4000] for i in range(0, len(formatted_output), 4000)]
                    await query.edit_message_text(text=chunks[0], reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                    for chunk in chunks[1:]:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=chunk,
                            parse_mode=ParseMode.HTML
                        )
                else:
                    await query.edit_message_text(text=formatted_output, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                
        except Exception as e:
            logger.error(f"Error getting WHOIS for {domain}: {str(e)}")
            await query.edit_message_text(text=f"Error getting WHOIS information: {str(e)}")
    
    elif query.data.startswith("expiry_"):
        domain = query.data[7:]  # Remove "expiry_" prefix
        await query.edit_message_text(text=f"Fetching expiration date for {domain}...")
        
        try:
            whois_output = get_whois_info(domain)
            
            # Check if domain is available
            is_available = check_domain_availability(whois_output)
            
            if is_available:
                # Domain is available
                keyboard = [
                    [InlineKeyboardButton("🛒 Register This Domain", url=DOMAIN_REGISTER_URL)],
                    [InlineKeyboardButton("🔍 Search another domain", callback_data="how_to_use")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text=f"✅ <b>Good news!</b> The domain <b>{escape_html(domain)}</b> appears to be available for registration.\n\n"
                    "You can register it by clicking the button below.",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            else:
                # Domain is registered - show expiry info
                expiry_info = extract_expiry_date(domain, whois_output)
                
                # Create back button
                keyboard = [
                    [InlineKeyboardButton("◀️ Back to options", callback_data=f"domain_{domain}")],
                    [InlineKeyboardButton("🔍 Search another domain", callback_data="how_to_use")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text=expiry_info,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
                
        except Exception as e:
            logger.error(f"Error getting expiry date for {domain}: {str(e)}")
            await query.edit_message_text(text=f"Error getting expiration date: {str(e)}")
    
    elif query.data.startswith("dns_"):
        domain = query.data[4:]  # Remove "dns_" prefix
        await query.edit_message_text(text=f"Fetching DNS information for {domain}...")
        
        try:
            whois_output = get_whois_info(domain)
            
            # Check if domain is available
            is_available = check_domain_availability(whois_output)
            
            if is_available:
                # Domain is available
                keyboard = [
                    [InlineKeyboardButton("🛒 Register This Domain", url=DOMAIN_REGISTER_URL)],
                    [InlineKeyboardButton("🔍 Search another domain", callback_data="how_to_use")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text=f"✅ <b>Good news!</b> The domain <b>{escape_html(domain)}</b> appears to be available for registration.\n\n"
                    "You can register it by clicking the button below.",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            else:
                # Domain is registered - show DNS info
                dns_info = extract_dns_info(domain, whois_output)
                
                # Create back button
                keyboard = [
                    [InlineKeyboardButton("◀️ Back to options", callback_data=f"domain_{domain}")],
                    [InlineKeyboardButton("🔍 Search another domain", callback_data="how_to_use")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text=dns_info,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
                
        except Exception as e:
            logger.error(f"Error getting DNS info for {domain}: {str(e)}")
            await query.edit_message_text(text=f"Error getting DNS information: {str(e)}")
    
    elif query.data.startswith("register_"):
        domain = query.data[9:]  # Remove "register_" prefix
        # No need to do anything here, as the URL will be opened by the user's Telegram client

async def whois_domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process the domain input and show options."""
    # Get the domain from the message
    domain = update.message.text.strip().lower()
    
    # Add user to the users set for tracking
    user_id = update.effective_user.id
    users.add(user_id)
    save_users()
    
    # Basic validation for domain name
    if not is_valid_domain(domain):
        keyboard = [[InlineKeyboardButton("See examples", callback_data="how_to_use")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ Please enter a valid domain name (e.g., example.com)",
            reply_markup=reply_markup
        )
        return
    
    # Update recent searches
    update_recent_searches(user_id, domain)
    
    # Show options when domain is entered
    keyboard = [
        [InlineKeyboardButton("🔎 View WHOIS", callback_data=f"whois_{domain}")],
        [InlineKeyboardButton("🌐 View DNS Info", callback_data=f"dns_{domain}")],
        [InlineKeyboardButton("📅 View Expiry Date", callback_data=f"expiry_{domain}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"What would you like to know about <b>{escape_html(domain)}</b>?",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

def update_recent_searches(user_id: int, domain: str) -> None:
    """Update the recent searches list."""
    global recent_searches
    
    # Add the new search
    recent_searches.insert(0, {
        "user_id": user_id,
        "domain": domain,
        "time": datetime.now()
    })
    
    # Keep only the last MAX_RECENT_SEARCHES per user
    user_searches = [s for s in recent_searches if s["user_id"] == user_id]
    if len(user_searches) > MAX_RECENT_SEARCHES:
        # Find searches to remove
        to_remove = []
        count = 0
        for s in recent_searches:
            if s["user_id"] == user_id:
                count += 1
                if count > MAX_RECENT_SEARCHES:
                    to_remove.append(s)
        
        # Remove excess searches
        for s in to_remove:
            recent_searches.remove(s)

def is_valid_domain(domain: str) -> bool:
    """Validate domain names using regex."""
    # Simple regex for domain validation
    pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return bool(re.match(pattern, domain))

def check_domain_availability(whois_output: str) -> bool:
    """Check if a domain is available based on the WHOIS output."""
    # Common phrases indicating a domain is not registered
    available_patterns = [
        r'no match',
        r'not found',
        r'no entries found',
        r'no data found',
        r'domain not found',
        r'domain name is not registered',
        r'domain is available',
        r'domain not registered',
        r'domain status: available',
        r'status: free',
        r'status: available',
        r'no object found'
    ]
    
    # Check if any of the availability patterns match
    whois_lower = whois_output.lower()
    for pattern in available_patterns:
        if re.search(pattern, whois_lower):
            return True
    
    return False

def format_whois_output(domain: str, raw_output: str) -> str:
    """Format the WHOIS output for better readability."""
    # Add a header
    formatted = f"🌐 <b>WHOIS Information for {escape_html(domain)}</b>\n\n"
    
    # Instead of using <pre> tags which may cause issues with < and > in the text,
    # just escape each line and format with line breaks
    lines = raw_output.split('\n')
    for line in lines:
        if line.strip():
            formatted += f"{escape_html(line)}\n"
    
    # Add footer with timestamp
    formatted += f"\n<i>Retrieved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
    
    return formatted

def extract_expiry_date(domain: str, whois_output: str) -> str:
    """Extract and format expiration date information from WHOIS output."""
    expiry_info = f"📅 <b>Expiration Date for {escape_html(domain)}</b>\n\n"
    found = False
    
    # Common expiry date field patterns in WHOIS output
    expiry_patterns = [
        r'(?i)expir(y|ation|es).*?date',
        r'(?i)registry(\s)?expiry(\s)?date',
        r'(?i)paid-till',
        r'(?i)valid(\s)?until',
        r'(?i)expiry',
        r'(?i)expires(\s)?on'
    ]
    
    lines = whois_output.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if this line contains expiry information
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in expiry_patterns):
            found = True
            expiry_info += f"{escape_html(line)}\n"
    
    if not found:
        expiry_info += "No expiration date information found in the WHOIS data."
    
    expiry_info += f"\n<i>Retrieved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
    return expiry_info

def extract_dns_info(domain: str, whois_output: str) -> str:
    """Extract and format DNS server information from WHOIS output."""
    dns_info = f"🌐 <b>DNS Information for {escape_html(domain)}</b>\n\n"
    found = False
    
    # Common DNS field patterns in WHOIS output
    dns_patterns = [
        r'(?i)name(\s)?server',
        r'(?i)nserver',
        r'(?i)dns',
        r'(?i)name(\s)?servers'
    ]
    
    lines = whois_output.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if this line contains DNS information
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in dns_patterns):
            found = True
            dns_info += f"{escape_html(line)}\n"
    
    if not found:
        dns_info += "No DNS server information found in the WHOIS data."
    
    dns_info += f"\n<i>Retrieved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
    return dns_info

def get_whois_info(domain: str) -> str:
    """Get WHOIS information from the server using sshpass."""
    try:
        # Check if root password is set
        if not ROOT_PASSWORD:
            return "Error: Server password is not configured. Please set the ROOT_PASSWORD environment variable."
            
        # Use sshpass to handle SSH password authentication
        # Install sshpass with: apt-get install -y sshpass
        cmd = [
            'sshpass', 
            '-p', ROOT_PASSWORD, 
            'ssh', 
            '-o', 'StrictHostKeyChecking=no', 
            f'root@{SERVER_IP}', 
            f'whois {domain}'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return f"Error executing WHOIS command: {result.stderr}"
        
        return result.stdout if result.stdout else "No WHOIS information found."
    
    except Exception as e:
        return f"Failed to execute WHOIS command: {str(e)}"

def load_users():
    """Load users from file if exists."""
    global users
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                data = json.load(f)
                users = set(int(uid) for uid in data["users"] if str(uid).isdigit())
            logger.info(f"Loaded {len(users)} users from file")
    except Exception as e:
        logger.error(f"Error loading users: {e}")

def save_users():
    """Save users to file."""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump({"users": list(users)}, f)
        logger.info(f"Saved {len(users)} users to file")
    except Exception as e:
        logger.error(f"Error saving users: {e}")

def main() -> None:
    """Start the bot."""
    # Load existing users
    load_users()
    
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("recent", recent_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Add conversation handler for broadcast
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_command)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_broadcast_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )
    application.add_handler(conv_handler)
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, whois_domain))
    
    # Log startup information
    logger.info("Bot started")
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling()
    
    # Save users on shutdown
    save_users()

if __name__ == "__main__":
    main()
