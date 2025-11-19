import logging
import os
import re
import hashlib
import hmac
import json
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import psycopg2
from psycopg2.extras import RealDictCursor
import sys

print("🚀 Starting Elevate Platform Bot on Railway...")

# 🔐 Environment variables from Railway
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

# Email configuration
EMAIL_HOST = os.environ.get('EMAIL_HOST')
EMAIL_PORT = os.environ.get('EMAIL_PORT')
EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# Database configuration for Railway
DATABASE_URL = os.environ.get('DATABASE_URL')

# ✅ Check essential keys
if not BOT_TOKEN:
    print("❌ ERROR: Missing BOT_TOKEN in Environment Variables")
    print("ℹ️ Please add BOT_TOKEN to Railway Variables")
    sys.exit(1)

if not DATABASE_URL:
    print("❌ ERROR: Missing DATABASE_URL in Environment Variables")
    print("ℹ️ Railway should provide DATABASE_URL automatically")
    sys.exit(1)

print("✅ Bot Token: Loaded successfully")
print("✅ Database URL: Loaded successfully")

# Check email settings
if EMAIL_HOST and EMAIL_PORT and EMAIL_USER and EMAIL_PASSWORD:
    print(f"✅ Email configured: {EMAIL_USER}")
else:
    print("⚠️ Email not fully configured - emails won't be sent")

# 🔧 Import Telegram libraries
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
    print("✅ All libraries installed successfully!")
except ImportError as e:
    print(f"❌ Error importing libraries: {e}")
    sys.exit(1)

# 🔧 AI settings
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
MAX_AI_QUESTIONS = 5

# 📅 Booking Configuration
AVAILABLE_DAYS = [0, 1, 2, 3, 4]  # Monday=0 to Friday=4 (no weekends)
AVAILABLE_TIMES = ['10:00', '11:00', '14:00', '15:00', '16:00']
CONSULTATION_DURATION_MINUTES = 30
TIMEZONE = 'Europe/Brussels'  # Belgium timezone

# 🗄️ PostgreSQL Connection Helper - UPDATED FOR RAILWAY
def get_db_connection():
    """Get PostgreSQL database connection for Railway"""
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

# 💱 Supported Currencies (Frankfurter API - ECB rates)
SUPPORTED_CURRENCIES = {
    'USD': 'US Dollar', 'EUR': 'Euro', 'GBP': 'British Pound', 'JPY': 'Japanese Yen',
    'AUD': 'Australian Dollar', 'CAD': 'Canadian Dollar', 'CHF': 'Swiss Franc', 'CNY': 'Chinese Yuan',
    'SEK': 'Swedish Krona', 'NZD': 'New Zealand Dollar', 'KRW': 'South Korean Won', 'SGD': 'Singapore Dollar',
    'NOK': 'Norwegian Krone', 'MXN': 'Mexican Peso', 'INR': 'Indian Rupee', 'BRL': 'Brazilian Real',
    'ZAR': 'South African Rand', 'TRY': 'Turkish Lira', 'HKD': 'Hong Kong Dollar', 'IDR': 'Indonesian Rupiah',
    'MYR': 'Malaysian Ringgit', 'PHP': 'Philippine Peso', 'THB': 'Thai Baht', 'PLN': 'Polish Zloty',
    'CZK': 'Czech Koruna', 'HUF': 'Hungarian Forint', 'RON': 'Romanian Leu', 'BGN': 'Bulgarian Lev',
    'DKK': 'Danish Krone', 'ISK': 'Icelandic Krona', 'ILS': 'Israeli Shekel'
}

# 💱 Popular Currencies for Quick Selection
POPULAR_CURRENCIES = [
    {'code': 'EUR', 'name_en': 'Euro', 'name_ar': 'يورو', 'flag': '🇪🇺'},
    {'code': 'USD', 'name_en': 'US Dollar', 'name_ar': 'دولار أمريكي', 'flag': '🇺🇸'},
    {'code': 'GBP', 'name_en': 'British Pound', 'name_ar': 'جنيه استرليني', 'flag': '🇬🇧'},
    {'code': 'TRY', 'name_en': 'Turkish Lira', 'name_ar': 'ليرة تركية', 'flag': '🇹🇷'},
    {'code': 'CHF', 'name_en': 'Swiss Franc', 'name_ar': 'فرنك سويسري', 'flag': '🇨🇭'},
    {'code': 'CAD', 'name_en': 'Canadian Dollar', 'name_ar': 'دولار كندي', 'flag': '🇨🇦'},
    {'code': 'AUD', 'name_en': 'Australian Dollar', 'name_ar': 'دولار أسترالي', 'flag': '🇦🇺'},
    {'code': 'SEK', 'name_en': 'Swedish Krona', 'name_ar': 'كرونة سويدية', 'flag': '🇸🇪'},
    {'code': 'NOK', 'name_en': 'Norwegian Krone', 'name_ar': 'كرونة نرويجية', 'flag': '🇳🇴'},
    {'code': 'DKK', 'name_en': 'Danish Krone', 'name_ar': 'كرونة دنماركية', 'flag': '🇩🇰'},
    {'code': 'PLN', 'name_en': 'Polish Zloty', 'name_ar': 'زلوتي بولندي', 'flag': '🇵🇱'},
    {'code': 'CZK', 'name_en': 'Czech Koruna', 'name_ar': 'كرونة تشيكية', 'flag': '🇨🇿'},
    {'code': 'HUF', 'name_en': 'Hungarian Forint', 'name_ar': 'فورنت مجري', 'flag': '🇭🇺'},
    {'code': 'RON', 'name_en': 'Romanian Leu', 'name_ar': 'ليو روماني', 'flag': '🇷🇴'},
    {'code': 'BGN', 'name_en': 'Bulgarian Lev', 'name_ar': 'ليف بلغاري', 'flag': '🇧🇬'},
    {'code': 'ILS', 'name_en': 'Israeli Shekel', 'name_ar': 'شيكل إسرائيلي', 'flag': '🇮🇱'},
    {'code': 'JPY', 'name_en': 'Japanese Yen', 'name_ar': 'ين ياباني', 'flag': '🇯🇵'},
    {'code': 'CNY', 'name_en': 'Chinese Yuan', 'name_ar': 'يوان صيني', 'flag': '🇨🇳'},
    {'code': 'INR', 'name_en': 'Indian Rupee', 'name_ar': 'روبية هندية', 'flag': '🇮🇳'},
    {'code': 'KRW', 'name_en': 'South Korean Won', 'name_ar': 'وون كوري', 'flag': '🇰🇷'},
    {'code': 'SGD', 'name_en': 'Singapore Dollar', 'name_ar': 'دولار سنغافوري', 'flag': '🇸🇬'},
    {'code': 'MYR', 'name_en': 'Malaysian Ringgit', 'name_ar': 'رينغيت ماليزي', 'flag': '🇲🇾'},
    {'code': 'THB', 'name_en': 'Thai Baht', 'name_ar': 'بات تايلندي', 'flag': '🇹🇭'},
    {'code': 'PHP', 'name_en': 'Philippine Peso', 'name_ar': 'بيزو فلبيني', 'flag': '🇵🇭'},
]

# 📅 Database Functions for Bookings - UPDATED FOR RAILWAY
def init_bookings_db():
    """Initialize bookings database on Railway"""
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to initialize database - no connection")
        return
    
    try:
        cursor = conn.cursor()
        
        # Table for consultation bookings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                service_type TEXT NOT NULL,
                country TEXT,
                booking_date TEXT,
                booking_time TEXT,
                payment_method TEXT NOT NULL,
                payment_confirmed BOOLEAN DEFAULT FALSE,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # Table for report requests (5 EUR detailed reports)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS report_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                country TEXT,
                service_type TEXT,
                conversation_summary TEXT,
                payment_method TEXT NOT NULL,
                payment_confirmed BOOLEAN DEFAULT FALSE,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                completed_at TEXT
            )
        ''')
        
        # Table for CV & Cover Letter requests
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cv_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                request_type TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                linkedin TEXT,
                location TEXT,
                work_experience TEXT,
                education TEXT,
                skills TEXT,
                certifications TEXT,
                job_title TEXT,
                company_name TEXT,
                why_job TEXT,
                achievements TEXT,
                unique_value TEXT,
                payment_method TEXT NOT NULL,
                payment_confirmed BOOLEAN DEFAULT FALSE,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                completed_at TEXT
            )
        ''')
        
        # Table for AI sessions (Free AI Assistant tracking)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                telegram_username TEXT,
                first_name TEXT,
                language TEXT,
                country TEXT,
                service_type TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                question_count INTEGER DEFAULT 0,
                report_requested BOOLEAN DEFAULT FALSE,
                report_email TEXT,
                last_message_at TEXT
            )
        ''')
        
        # Table for user activity
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_activity (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                telegram_username TEXT,
                first_name TEXT,
                action_type TEXT NOT NULL,
                action_details TEXT,
                timestamp TEXT NOT NULL
            )
        ''')
        
        conn.commit()
        print("✅ Database tables initialized successfully")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
    finally:
        conn.close()

def check_slot_available(date, time):
    """Check if a time slot is available"""
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM bookings 
            WHERE booking_date = %s AND booking_time = %s AND status != 'cancelled'
        ''', (date, time))
        count = cursor.fetchone()[0]
        return count == 0
    except Exception as e:
        print(f"❌ Error checking slot availability: {e}")
        return False
    finally:
        conn.close()

def save_booking(user_id, name, email, service_type, country, booking_date, booking_time, payment_method):
    """Save a new booking with Belgium timezone"""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor()
        belgium_tz = ZoneInfo(TIMEZONE)
        created_at = datetime.now(belgium_tz).isoformat()
        
        cursor.execute('''
            INSERT INTO bookings (user_id, name, email, service_type, country, booking_date, booking_time, payment_method, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (user_id, name, email, service_type, country, booking_date, booking_time, payment_method, created_at))
        booking_id = cursor.fetchone()[0]
        conn.commit()
        print(f"💾 Booking saved: ID={booking_id}, Date={booking_date}, Time={booking_time}, User={name}")
        return booking_id
    except Exception as e:
        print(f"❌ Error saving booking: {e}")
        return None
    finally:
        conn.close()

def save_report_request(user_id, name, email, country, service_type, conversation_summary, payment_method):
    """Save a new report request (5 EUR detailed report)"""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor()
        belgium_tz = ZoneInfo(TIMEZONE)
        created_at = datetime.now(belgium_tz).isoformat()
        
        cursor.execute('''
            INSERT INTO report_requests (user_id, name, email, country, service_type, conversation_summary, payment_method, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (user_id, name, email, country, service_type, conversation_summary, payment_method, created_at))
        request_id = cursor.fetchone()[0]
        conn.commit()
        print(f"💾 Report request saved: ID={request_id}, User={name}, Email={email}")
        return request_id
    except Exception as e:
        print(f"❌ Error saving report request: {e}")
        return None
    finally:
        conn.close()

def get_user_booking(user_id):
    """Get latest pending booking for user"""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM bookings 
            WHERE user_id = %s AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))
        booking = cursor.fetchone()
        return booking
    except Exception as e:
        print(f"❌ Error getting user booking: {e}")
        return None
    finally:
        conn.close()

def create_ai_session(user_id, telegram_username, first_name, language, country, service_type):
    """Create a new AI session when user starts free AI chat"""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor()
        belgium_tz = ZoneInfo(TIMEZONE)
        started_at = datetime.now(belgium_tz).isoformat()
        
        cursor.execute('''
            INSERT INTO ai_sessions (user_id, telegram_username, first_name, language, country, service_type, started_at, question_count, last_message_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s)
            RETURNING id
        ''', (user_id, telegram_username, first_name, language, country, service_type, started_at, started_at))
        session_id = cursor.fetchone()[0]
        conn.commit()
        print(f"💾 AI Session created: ID={session_id}, User={first_name} ({user_id}), Country={country}")
        return session_id
    except Exception as e:
        print(f"❌ Error creating AI session: {e}")
        return None
    finally:
        conn.close()

def update_ai_session(user_id, question_count):
    """Update AI session with new question count and last message time"""
    conn = get_db_connection()
    if not conn:
        return
        
    try:
        cursor = conn.cursor()
        belgium_tz = ZoneInfo(TIMEZONE)
        last_message_at = datetime.now(belgium_tz).isoformat()
        
        cursor.execute('''
            UPDATE ai_sessions 
            SET question_count = %s, last_message_at = %s
            WHERE id = (
                SELECT id FROM ai_sessions 
                WHERE user_id = %s AND completed_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            )
        ''', (question_count, last_message_at, user_id))
        conn.commit()
    except Exception as e:
        print(f"❌ Error updating AI session: {e}")
    finally:
        conn.close()

def mark_session_completed(user_id):
    """Mark AI session as completed"""
    conn = get_db_connection()
    if not conn:
        return
        
    try:
        cursor = conn.cursor()
        belgium_tz = ZoneInfo(TIMEZONE)
        completed_at = datetime.now(belgium_tz).isoformat()
        
        cursor.execute('''
            UPDATE ai_sessions 
            SET completed_at = %s
            WHERE id = (
                SELECT id FROM ai_sessions 
                WHERE user_id = %s AND completed_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            )
        ''', (completed_at, user_id))
        conn.commit()
    except Exception as e:
        print(f"❌ Error marking session completed: {e}")
    finally:
        conn.close()

def mark_report_requested(user_id, report_email):
    """Mark that user requested free report with their email"""
    conn = get_db_connection()
    if not conn:
        return
        
    try:
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE ai_sessions 
            SET report_requested = TRUE, report_email = %s
            WHERE id = (
                SELECT id FROM ai_sessions 
                WHERE user_id = %s AND completed_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            )
        ''', (report_email, user_id))
        conn.commit()
        print(f"💾 Free report requested: User={user_id}, Email={report_email}")
    except Exception as e:
        print(f"❌ Error marking report requested: {e}")
    finally:
        conn.close()

def get_active_session(user_id):
    """Get active AI session for user"""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM ai_sessions 
            WHERE user_id = %s AND completed_at IS NULL
            ORDER BY started_at DESC LIMIT 1
        ''', (user_id,))
        session = cursor.fetchone()
        return session
    except Exception as e:
        print(f"❌ Error getting active session: {e}")
        return None
    finally:
        conn.close()

def track_user_activity(user_id, telegram_username, first_name, action_type, action_details=None):
    """Track user browsing and interaction activity"""
    try:
        conn = get_db_connection()
        if not conn:
            return
            
        cursor = conn.cursor()
        belgium_tz = ZoneInfo(TIMEZONE)
        timestamp = datetime.now(belgium_tz).isoformat()
        
        cursor.execute('''
            INSERT INTO user_activity (user_id, telegram_username, first_name, action_type, action_details, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (user_id, telegram_username, first_name, action_type, action_details, timestamp))
        conn.commit()
    except Exception as e:
        print(f"⚠️ Error tracking activity: {e}")
    finally:
        if conn:
            conn.close()

# Initialize bookings database
print("🔄 Initializing database...")
init_bookings_db()

# 🔗 Affiliate links - SEPARATE LINKS FOR EACH LANGUAGE
AFFILIATE_LINKS = {
    'en': {
        'getyourguide': 'https://getyourguide.tpo.mx/SPqoxjWD',
        'klook': 'https://klook.tpo.mx/1IPQswu1',
        'booking': 'https://www.booking.com',
        'visitorscoverage': 'https://www.visitorscoverage.com'
    },
    'ar': {
        'getyourguide': 'https://getyourguide.tpo.mx/SPqoxjWD',
        'klook': 'https://klook.tpo.mx/1IPQswu1', 
        'booking': 'https://www.booking.com',
        'visitorscoverage': 'https://www.visitorscoverage.com'
    }
}

# 🔐 AI Class
class DeepSeekAI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = DEEPSEEK_API_URL

    async def get_ai_response(self, user_message, conversation_history, country, service_type, language):
        """Get response from AI"""
        try:
            print(f"🔄 Connecting to AI...")

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            messages = [
                {"role": "system", "content": "You are a helpful assistant for Elevate platform."},
                *conversation_history,
                {"role": "user", "content": user_message}
            ]

            payload = {
                "model": "deepseek-chat",
                "messages": messages,
                "max_tokens": 500,
                "temperature": 0.7
            }

            response = requests.post(
                self.base_url, 
                json=payload, 
                headers=headers, 
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                print("✅ AI response received successfully")
                return data["choices"][0]["message"]["content"]
            else:
                print(f"❌ API error: {response.status_code}")
                return "Sorry, there was an error. Please try again."

        except Exception as e:
            print(f"❌ AI error: {e}")
            return "Sorry, an unexpected error occurred. Please try again."

# Create AI assistant
ai_assistant = DeepSeekAI(DEEPSEEK_API_KEY) if DEEPSEEK_API_KEY else None

# 📧 Email sending function
async def send_email_report(recipient_email, content, language, subject_type):
    """Send email report to user"""
    try:
        if not all([EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD]):
            print("❌ Email configuration incomplete")
            return False
        
        # Create email subject
        if subject_type == "Free AI Conversation Report":
            subject = "Your Free AI Conversation Report - Elevate" if language == 'en' else "تقرير محادثة الذكاء الاصطناعي المجاني - Elevate"
        elif subject_type == "Detailed Report":
            subject = "Your Detailed Report - Elevate" if language == 'en' else "تقريرك المفصل - Elevate"
        else:
            subject = "Your Report - Elevate" if language == 'en' else "تقريرك - Elevate"
        
        # Create email body
        body = f"""
Hello,

Thank you for using Elevate Platform!

{content}

---
Best regards,
Elevate Team
info@studyua.org
""" if language == 'en' else f"""
مرحباً،

شكراً لاستخدامك منصة Elevate!

{content}

---
مع أطيب التحيات،
فريق Elevate
info@studyua.org
"""
        
        # Create message
        message = MIMEMultipart()
        message['From'] = EMAIL_USER
        message['To'] = recipient_email
        message['Subject'] = subject
        message.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Send email
        print(f"📧 Connecting to SMTP server: {EMAIL_HOST}:{EMAIL_PORT}")
        
        port = int(EMAIL_PORT)
        
        # Port 465 uses SSL, port 587 uses STARTTLS
        if port == 465:
            # Use SMTP_SSL for port 465
            with smtplib.SMTP_SSL(EMAIL_HOST, port) as server:
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(message)
        else:
            # Use SMTP with STARTTLS for port 587
            with smtplib.SMTP(EMAIL_HOST, port) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(message)
        
        print(f"✅ Email sent successfully to {recipient_email}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False

async def send_admin_notification(notification_type, user_data, conversation_summary=None):
    """Send email notification to admin about free AI usage"""
    try:
        if not all([EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD]):
            print("❌ Email configuration incomplete - skipping admin notification")
            return False
        
        admin_email = "info@studyua.org"
        
        if notification_type == "ai_session_started":
            subject = "🤖 New Free AI Session Started"
            body = f"""
New Free AI Session Started

User Details:
👤 Name: {user_data.get('first_name', 'N/A')}
🆔 User ID: {user_data.get('user_id', 'N/A')}
📱 Username: @{user_data.get('telegram_username', 'N/A')}
🌍 Country: {user_data.get('country', 'N/A')}
🎯 Service: {user_data.get('service_type', 'N/A')}
🗣️ Language: {user_data.get('language', 'N/A')}
🕒 Started: {datetime.now(ZoneInfo(TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S')}

---
Elevate Platform Admin
"""
        
        elif notification_type == "free_report_requested":
            subject = "📧 Free AI Report Requested"
            body = f"""
Free AI Report Requested

User Details:
👤 Name: {user_data.get('first_name', 'N/A')}
🆔 User ID: {user_data.get('user_id', 'N/A')}
📱 Username: @{user_data.get('telegram_username', 'N/A')}
📧 Email: {user_data.get('email', 'N/A')}
🌍 Country: {user_data.get('country', 'N/A')}
🎯 Service: {user_data.get('service_type', 'N/A')}
🗣️ Language: {user_data.get('language', 'N/A')}
❓ Questions Asked: {user_data.get('question_count', 'N/A')}
🕒 Requested: {datetime.now(ZoneInfo(TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S')}

Conversation Summary (Last 10 Messages):
{'-' * 50}
{conversation_summary if conversation_summary else 'No conversation summary available'}
{'-' * 50}

---
Elevate Platform Admin
"""
        else:
            print(f"❌ Unknown notification type: {notification_type}")
            return False
        
        # Create message
        message = MIMEMultipart()
        message['From'] = EMAIL_USER
        message['To'] = admin_email
        message['Subject'] = subject
        message.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Send email
        port = int(EMAIL_PORT)
        
        if port == 465:
            with smtplib.SMTP_SSL(EMAIL_HOST, port) as server:
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP(EMAIL_HOST, port) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(message)
        
        print(f"✅ Admin notification sent: {notification_type}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending admin notification: {e}")
        return False

# 🔐 User State Management
class UserStateManager:
    def __init__(self):
        self.user_states = {}
        self.user_conversations = {}
        self.user_languages = {}

    def set_state(self, user_id, state, data=None):
        if data is None:
            data = {}
        self.user_states[user_id] = {
            'state': state,
            'data': data,
            'timestamp': datetime.now()
        }

    def get_state(self, user_id):
        state_data = self.user_states.get(user_id)
        if state_data:
            # Clean old states (older than 1 hour)
            if datetime.now() - state_data['timestamp'] > timedelta(hours=1):
                del self.user_states[user_id]
                return None
            return state_data
        return None

    def clear_state(self, user_id):
        if user_id in self.user_states:
            del self.user_states[user_id]
        if user_id in self.user_conversations:
            del self.user_conversations[user_id]

    def add_conversation_message(self, user_id, role, content):
        if user_id not in self.user_conversations:
            self.user_conversations[user_id] = []
        self.user_conversations[user_id].append({"role": role, "content": content})
        # Keep only last 10 messages
        if len(self.user_conversations[user_id]) > 10:
            self.user_conversations[user_id] = self.user_conversations[user_id][-10:]

    def get_conversation(self, user_id):
        return self.user_conversations.get(user_id, [])

    def get_question_count(self, user_id):
        conversation = self.get_conversation(user_id)
        user_questions = [msg for msg in conversation if msg["role"] == "user"]
        return len(user_questions)

    # Language management functions
    def set_user_language(self, user_id, language):
        self.user_languages[user_id] = language
        print(f"✅ Language set to: {language} for user {user_id}")

    def get_user_language(self, user_id):
        return self.user_languages.get(user_id, 'en')

# Create state manager
user_state_manager = UserStateManager()

# 📅 Calendar Functions
def get_available_dates(days_ahead=14):
    """Get available dates for next N days (weekdays only) in Belgium timezone"""
    available_dates = []
    # Get current date in Belgium timezone
    belgium_tz = ZoneInfo(TIMEZONE)
    current_date = datetime.now(belgium_tz)
    
    for i in range(days_ahead):
        check_date = current_date + timedelta(days=i)
        if check_date.weekday() in AVAILABLE_DAYS:  # Monday=0 to Friday=4
            available_dates.append(check_date.strftime('%Y-%m-%d'))
    
    return available_dates

def generate_calendar_keyboard(language='en'):
    """Generate calendar keyboard with available dates"""
    dates = get_available_dates(14)
    keyboard = []
    
    # Show dates in rows of 3
    for i in range(0, len(dates), 3):
        row = []
        for date in dates[i:i+3]:
            # Format: Mon, Nov 15
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            if language == 'ar':
                day_name = ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة'][date_obj.weekday()]
                display = f"{day_name} {date_obj.day}/{date_obj.month}"
            else:
                display = date_obj.strftime('%a, %b %d')
            
            row.append(InlineKeyboardButton(display, callback_data=f"date_{date}"))
        keyboard.append(row)
    
    # Add back button
    keyboard.append([InlineKeyboardButton(
        "Back to Services" if language == 'en' else "العودة للخدمات",
        callback_data="back_services"
    )])
    
    return keyboard

def generate_time_keyboard(selected_date, language='en'):
    """Generate time slot keyboard for selected date"""
    keyboard = []
    
    for time_slot in AVAILABLE_TIMES:
        # Check if slot is available
        is_available = check_slot_available(selected_date, time_slot)
        
        if is_available:
            button_text = f"✅ {time_slot}" if language == 'en' else f"✅ {time_slot}"
            callback_data = f"time_{selected_date}_{time_slot}"
        else:
            button_text = f"❌ {time_slot} (Booked)" if language == 'en' else f"❌ {time_slot} (محجوز)"
            callback_data = f"booked_{selected_date}_{time_slot}"
        
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Add back button
    keyboard.append([InlineKeyboardButton(
        "⬅️ Back to Calendar" if language == 'en' else "⬅️ العودة للتقويم",
        callback_data="back_to_calendar"
    )])
    
    return keyboard

# 🌍 Available countries - ALL 28 COUNTRIES
COUNTRIES = {
    # 🌍 أوروبا (20 دولة)
    'germany': {'ar': '🇩🇪 ألمانيا', 'en': '🇩🇪 Germany'},
    'france': {'ar': '🇫🇷 فرنسا', 'en': '🇫🇷 France'},
    'italy': {'ar': '🇮🇹 إيطاليا', 'en': '🇮🇹 Italy'},
    'spain': {'ar': '🇪🇸 إسبانيا', 'en': '🇪🇸 Spain'},
    'netherlands': {'ar': '🇳🇱 هولندا', 'en': '🇳🇱 Netherlands'},
    'sweden': {'ar': '🇸🇪 السويد', 'en': '🇸🇪 Sweden'},
    'switzerland': {'ar': '🇨🇭 سويسرا', 'en': '🇨🇭 Switzerland'},
    'austria': {'ar': '🇦🇹 النمسا', 'en': '🇦🇹 Austria'},
    'belgium': {'ar': '🇧🇪 بلجيكا', 'en': '🇧🇪 Belgium'},
    'finland': {'ar': '🇫🇮 فنلندا', 'en': '🇫🇮 Finland'},
    'norway': {'ar': '🇳🇴 النرويج', 'en': '🇳🇴 Norway'},
    'denmark': {'ar': '🇩🇰 الدنمارك', 'en': '🇩🇰 Denmark'},
    'portugal': {'ar': '🇵🇹 البرتغال', 'en': '🇵🇹 Portugal'},
    'greece': {'ar': '🇬🇷 اليونان', 'en': '🇬🇷 Greece'},
    'czech': {'ar': '🇨🇿 التشيك', 'en': '🇨🇿 Czech Republic'},
    'slovakia': {'ar': '🇸🇰 سلوفاكيا', 'en': '🇸🇰 Slovakia'},
    'ukraine': {'ar': '🇺🇦 أوكرانيا', 'en': '🇺🇦 Ukraine'},
    'poland': {'ar': '🇵🇱 بولندا', 'en': '🇵🇱 Poland'},
    'romania': {'ar': '🇷🇴 رومانيا', 'en': '🇷🇴 Romania'},
    'hungary': {'ar': '🇭🇺 هنغاريا', 'en': '🇭🇺 Hungary'},

    # 🇬🇧 بريطانيا وأيرلندا (2 دولة)
    'uk': {'ar': '🇬🇧 بريطانيا', 'en': '🇬🇧 United Kingdom'},
    'ireland': {'ar': '🇮🇪 أيرلندا', 'en': '🇮🇪 Ireland'},

    # 🌏 أمريكا وأوقيانوسيا (4 دول)
    'usa': {'ar': '🇺🇸 أمريكا', 'en': '🇺🇸 United States'},
    'canada': {'ar': '🇨🇦 كندا', 'en': '🇨🇦 Canada'},
    'australia': {'ar': '🇦🇺 أستراليا', 'en': '🇦🇺 Australia'},
    'newzealand': {'ar': '🇳🇿 نيوزيلندا', 'en': '🇳🇿 New Zealand'},

    # 🆕 دول إضافية (2 دولة)
    'philippines': {'ar': '🇵🇭 الفلبين', 'en': '🇵🇭 Philippines'},
    'china': {'ar': '🇨🇳 الصين', 'en': '🇨🇳 China'}
}

# 🎯 Available services
SERVICES = {
    'study': {'ar': 'الدراسة في الخارج', 'en': 'Study Abroad'},
    'work': {'ar': 'تأشيرة العمل', 'en': 'Work Visa'},
    'activities': {'ar': 'الأنشطة والجولات', 'en': 'Activities & Tours'},
    'travel': {'ar': 'خدمات السفر', 'en': 'Travel Services'}
}

# 🎯 Multilingual texts - UPDATED WITH Elevate NAME
TEXTS = {
    'ar': {
        'welcome': "🎉 أهلاً بك {name}!\n\n**منصة Elevate** 🤖\n\nاختر اللغة:",
        'services_title': "**منصة Elevate** 🤖\n\n🌍 **الخدمات المتاحة:**",
        'service_study': "🎓 الدراسة في الخارج",
        'service_work': "💼 تأشيرة العمل",
        'service_cv': "📄 السيرة الذاتية ورسالة التغطية",
        'service_activities': "🎫 الأنشطة والجولات", 
        'service_travel': "🛫 خدمات السفر",
        'travel_essentials': "✈️ خدمات السفر الأساسية",
        'statistics': "📊 التقارير والإحصائيات",
        'help': "❓ المساعدة",
        'back_main': "🔙 القائمة الرئيسية",
        'back_services': "🔙 العودة للخدمات",
        'contact': "📞 اتصل بنا",
        'change_language': "🌐 تغيير اللغة",
        'activities_description': "🎫 **الأنشطة والجولات السياحية**\n\nاستكشف أفضل الأنشطة والجولات في وجهتك",
        'travel_description': "🛫 **خدمات السفر**\n\nاحجز فنادق وأنشطة وسياحة",
        'open_link': "🔗 فتح رابط الخدمة",
        'ai_start_button': "🤖 اسأل الذكاء الاصطناعي (مجاني)",
        'contact_info': """📞 **معلومات الاتصال**

للتواصل المباشر مع فريقنا:

📧 البريد: info@studyua.org
📞 الهاتف: ‎+32 465 69 06 37
🌐 الموقع: www.studyua.org

🕒 ساعات العمل:
من الإثنين إلى الجمعة
9:00 - 18:00""",
        'help_info': """❓ **كيفية استخدام منصة Elevate**

**🎯 كيف تعمل المنصة:**

**1️⃣ اختر الخدمة:**
• 🎓 الدراسة في الخارج
• 💼 تأشيرة العمل
• 📄 السيرة الذاتية ورسالة التغطية
• ✈️ خدمات السفر الأساسية

**2️⃣ اختر الدولة:**
لدينا 28 دولة متاحة في أوروبا وأمريكا وآسيا

**3️⃣ اختر الخيار المناسب:**

🤖 **مساعد الذكاء الاصطناعي (مجاني)**
• احصل على إجابات فورية
• تحدث عن دراستك أو عملك
• آخر 10 رسائل سترسل لبريدك

📋 **تقرير مفصل (5 يورو)**
• احصل على تقرير شامل ومفصل
• سيتم إرساله عبر البريد الإلكتروني
• يحتوي على كل التفاصيل التي تحتاجها

💬 **استشارة شخصية (20 يورو)**
• احجز موعد استشارة مباشرة
• اختر التاريخ والوقت المناسب
• مدة الاستشارة: 30 دقيقة
• الأوقات المتاحة: من الإثنين إلى الجمعة

📄 **خدمات السيرة الذاتية ورسالة التغطية**
• سيرة ذاتية احترافية (10 يورو)
• رسالة تغطية مخصصة (10 يورو)
• الباقة الكاملة (15 يورو) - وفّر 5 يورو
• التسليم خلال 48 ساعة
• مُحسّنة لسوق العمل الأوروبي

**✈️ خدمات السفر الأساسية:**
كل ما تحتاجه للسفر والانتقال:
• التحضير للرحلة
• 💱 محول العملات (أسعار حية)
• الإقامة والسكن
• بطاقة SIM دولية
• التأمين الصحي
• الأنشطة والجولات

**💱 محول العملات:**
احصل على أسعار الصرف الحية لـ 31 عملة!
أرسل: `المبلغ من إلى` (مثال: `1000 USD EUR`)

**💳 الدفع:**
جميع المدفوعات آمنة عبر Stripe أو PayPal (أنت تختار)

**📊 الإحصائيات:**
شاهد ما يطلبه المستخدمون الآخرون - شفافية كاملة!

**🌐 تغيير اللغة:**
يمكنك التبديل بين العربية والإنجليزية في أي وقت

**❓ لديك سؤال؟**
تواصل معنا عبر قسم "اتصل بنا" """
    },
    'en': {
        'welcome': "🎉 Welcome {name}!\n\n**Elevate Platform** 🤖\n\nChoose language:",
        'services_title': "**Elevate Platform** 🤖\n\n🌍 **Available Services:**",
        'service_study': "🎓 Study Abroad",
        'service_work': "💼 Work Visa",
        'service_cv': "📄 CV & Cover Letter",
        'service_activities': "🎫 Activities & Tours",
        'service_travel': "🛫 Travel Services",
        'travel_essentials': "✈️ Travel Essentials",
        'statistics': "📊 Reports & Statistics",
        'help': "❓ Help",
        'back_main': "🔙 Main Menu",
        'back_services': "🔙 Back to Services",
        'contact': "📞 Contact",
        'change_language': "🌐 Change Language",
        'activities_description': "🎫 **Activities & Tours**\n\nExplore the best activities and tours in your destination",
        'travel_description': "🛫 **Travel Services**\n\nBook hotels, activities and tourism",
        'open_link': "🔗 Open Service Link",
        'ai_start_button': "🤖 Ask AI Assistant (Free)",
        'contact_info': """📞 **Contact Information**

For direct contact with our team:

📧 Email: info@studyua.org
📞 Phone: +32 467 685 250
🌐 Website: www.studyua.org

🕒 Working Hours:
Monday to Friday
9:00 - 18:00""",
        'help_info': """❓ **How to Use Elevate Platform**

**🎯 How It Works:**

**1️⃣ Choose Your Service:**
• 🎓 Study Abroad
• 💼 Work Visa
• 📄 CV & Cover Letter
• ✈️ Travel Essentials

**2️⃣ Select Your Country:**
We cover 28 countries across Europe, Americas, and Asia

**3️⃣ Pick Your Option:**

🤖 **AI Assistant (FREE)**
• Get instant answers
• Discuss your study or work plans
• Last 10 messages sent to your email

📋 **Detailed Report (5 EUR)**
• Receive a comprehensive report
• Delivered via email
• Contains all the details you need

💬 **Personal Consultation (20 EUR)**
• Book a direct consultation appointment
• Choose your preferred date and time
• Duration: 30 minutes
• Available: Monday to Friday

📄 **CV & Cover Letter Services**
• Professional CV Writing (€10)
• Custom Cover Letter (€10)
• Bundle Package (€15) - Save €5
• Delivered within 48 hours
• Optimized for European job markets

**✈️ Travel Essentials:**
Everything you need for relocation:
• Prepare for Your Trip
• 💱 Currency Converter (live rates)
• Accommodation
• International SIM Card
• Travel Insurance
• Activities & Tours

**💱 Currency Converter:**
Get live exchange rates for 31 currencies!
Send: `amount from to` (example: `1000 USD EUR`)

**💳 Payment:**
All payments are secure via Stripe or PayPal (you choose)

**📊 Statistics:**
See what other users are asking - full transparency!

**🌐 Change Language:**
Switch between Arabic and English anytime

**❓ Have Questions?**
Contact us through the "Contact" section"""
    }
}

# 🎯 Core bot functions - FIXED COMMANDS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler - FIXED"""
    try:
        user = update.effective_user
        user_id = user.id

        print(f"🚀 /start command received from user {user_id} ({user.first_name})")
        
        # 📊 Track user activity - Bot started
        track_user_activity(user_id, user.username, user.first_name, "bot_started", "User started the bot")

        # Clear any existing state
        user_state_manager.clear_state(user_id)

        # Show language selection
        keyboard = [
            [InlineKeyboardButton("English 🇺🇸", callback_data="lang_en")],
            [InlineKeyboardButton("العربية 🇸🇦", callback_data="lang_ar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🎉 Welcome {user.first_name}!\n\n**Elevate Platform** 🤖\n\nChoose language:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        print(f"❌ Error in start command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler - NEW"""
    try:
        help_text = """
🤖 **Elevate Platform Bot Help**

Available Commands:
/start - Start the bot
/help - Show this help message
/services - Show available services
/language - Change language

For support, use the contact option in the menu.
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in help command: {e}")

async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Services command handler - NEW"""
    try:
        user_id = update.effective_user.id
        language = user_state_manager.get_user_language(user_id)

        if not language:
            # If no language set, prompt for language selection
            keyboard = [
                [InlineKeyboardButton("English 🇺🇸", callback_data="lang_en")],
                [InlineKeyboardButton("العربية 🇸🇦", callback_data="lang_ar")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Please choose your language first:",
                reply_markup=reply_markup
            )
            return

        await show_services_message(update, language)

    except Exception as e:
        print(f"❌ Error in services command: {e}")

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Language command handler - NEW"""
    try:
        keyboard = [
            [InlineKeyboardButton("English 🇺🇸", callback_data="lang_en")],
            [InlineKeyboardButton("العربية 🇸🇦", callback_data="lang_ar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🌐 **Choose Language / اختر اللغة:**",
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"❌ Error in language command: {e}")

# 🎯 Shortcut Commands for Quick Access
async def study_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick access to Study Abroad service"""
    try:
        user_id = update.effective_user.id
        language = user_state_manager.get_user_language(user_id)
        
        if not language:
            language = 'en'
            user_state_manager.set_user_language(user_id, language)
        
        # Simulate clicking Study Abroad button
        user_state_manager.set_state(user_id, 'service_selected', {
            'service_type': 'study',
            'language': language
        })
        
        # Show country selection
        keyboard = []
        for country_code, names in COUNTRIES.items():
            country_name = names[language]
            keyboard.append([InlineKeyboardButton(country_name, callback_data=f"country_{country_code}")])
        
        keyboard.append([InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "🎓 **Study Abroad**\n\nSelect your country:" if language == 'en' else "🎓 **الدراسة في الخارج**\n\nاختر الدولة:"
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in study command: {e}")

async def work_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick access to Work Visa service"""
    try:
        user_id = update.effective_user.id
        language = user_state_manager.get_user_language(user_id)
        
        if not language:
            language = 'en'
            user_state_manager.set_user_language(user_id, language)
        
        # Simulate clicking Work Visa button
        user_state_manager.set_state(user_id, 'service_selected', {
            'service_type': 'work',
            'language': language
        })
        
        # Show country selection
        keyboard = []
        for country_code, names in COUNTRIES.items():
            country_name = names[language]
            keyboard.append([InlineKeyboardButton(country_name, callback_data=f"country_{country_code}")])
        
        keyboard.append([InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "💼 **Work Visa**\n\nSelect your country:" if language == 'en' else "💼 **تأشيرة العمل**\n\nاختر الدولة:"
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in work command: {e}")

async def travel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick access to Travel Essentials"""
    try:
        user_id = update.effective_user.id
        language = user_state_manager.get_user_language(user_id)
        
        if not language:
            language = 'en'
            user_state_manager.set_user_language(user_id, language)
        
        # Show Travel Essentials menu
        if language == 'ar':
            text = """✈️ **خدمات السفر الأساسية**

كل ما تحتاجه للسفر والانتقال:"""
            keyboard = [
                [InlineKeyboardButton("✈️ التحضير للرحلة", callback_data="ess_trip_prep")],
                [InlineKeyboardButton("💱 محول العملات", callback_data="ess_currency")],
                [InlineKeyboardButton("🏨 الإقامة", callback_data="ess_accommodation")],
                [InlineKeyboardButton("📱 بطاقة SIM دولية", callback_data="ess_sim")],
                [InlineKeyboardButton("🛡️ التأمين", callback_data="ess_insurance")],
                [InlineKeyboardButton("🎫 الأنشطة والجولات", callback_data="service_activities")],
                [InlineKeyboardButton("🛫 خدمات السفر", callback_data="service_travel")],
                [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
            ]
        else:
            text = """✈️ **Travel Essentials**

Everything you need for relocation and travel:"""
            keyboard = [
                [InlineKeyboardButton("✈️ Prepare for Your Trip", callback_data="ess_trip_prep")],
                [InlineKeyboardButton("💱 Currency Converter", callback_data="ess_currency")],
                [InlineKeyboardButton("🏨 Accommodation", callback_data="ess_accommodation")],
                [InlineKeyboardButton("📱 International SIM Card", callback_data="ess_sim")],
                [InlineKeyboardButton("🛡️ Travel Insurance", callback_data="ess_insurance")],
                [InlineKeyboardButton("🎫 Activities & Tours", callback_data="service_activities")],
                [InlineKeyboardButton("🛫 Travel Services", callback_data="service_travel")],
                [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in travel command: {e}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick access to Statistics"""
    try:
        user_id = update.effective_user.id
        language = user_state_manager.get_user_language(user_id)
        
        if not language:
            language = 'en'
        
        # Get statistics from database
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
            
        cursor = conn.cursor()
        
        # Total consultations and reports
        cursor.execute("SELECT COUNT(*) FROM bookings")
        total_consultations = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM report_requests")
        total_reports = cursor.fetchone()[0]
        
        conn.close()
        
        # Build stats message
        if language == 'ar':
            text = f"""📊 **إحصائيات المنصة**

**📈 إجمالي الخدمات:**
• الاستشارات: {total_consultations}
• التقارير: {total_reports}

💡 **ملاحظة:** البيانات يتم تحديثها باستمرار"""
        else:
            text = f"""📊 **Platform Statistics**

**📈 Total Services:**
• Consultations: {total_consultations}
• Reports: {total_reports}

💡 **Note:** Data is updated continuously"""
        
        keyboard = [[InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in stats command: {e}")

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick access to Contact Info"""
    try:
        user_id = update.effective_user.id
        language = user_state_manager.get_user_language(user_id)
        
        if not language:
            language = 'en'
        
        text = TEXTS[language]['contact_info']
        keyboard = [[InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in contact command: {e}")

async def currency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick access to Currency Converter"""
    try:
        user_id = update.effective_user.id
        language = user_state_manager.get_user_language(user_id)
        
        if not language:
            language = 'en'
        
        if language == 'ar':
            text = """💱 **محول العملات**

احصل على أسعار الصرف الحية!

**💡 كيف يعمل:**
انقر على "💱 محول العملات" أو أرسل رسالة بهذا التنسيق:
`المبلغ من إلى`

**📌 أمثلة:**
• `1000 USD EUR` - دولار أمريكي إلى يورو
• `500 GBP TRY` - جنيه استرليني إلى ليرة تركية
• `100 EUR CHF` - يورو إلى فرنك سويسري

**🌍 العملات المدعومة (31 عملة إجمالاً):**
EUR, USD, GBP, TRY, CHF, CAD, AUD, SEK, NOK, DKK, PLN, CZK, HUF, RON, BGN, ILS, JPY, CNY, INR, KRW, SGD, MYR, THB, PHP, IDR, HKD, NZD, MXN, BRL, ZAR, ISK

**🕐 التحديث:** أسعار حية من البنك المركزي الأوروبي"""
        else:
            text = """💱 **Currency Converter**

Get live exchange rates instantly!

**💡 How it works:**
Click "💱 Currency Converter" or send a message in this format:
`amount from to`

**📌 Examples:**
• `1000 USD EUR` - US Dollar to Euro
• `500 GBP TRY` - British Pound to Turkish Lira
• `100 EUR CHF` - Euro to Swiss Franc

**🌍 Supported Currencies (31 total):**
EUR, USD, GBP, TRY, CHF, CAD, AUD, SEK, NOK, DKK, PLN, CZK, HUF, RON, BGN, ILS, JPY, CNY, INR, KRW, SGD, MYR, THB, PHP, IDR, HKD, NZD, MXN, BRL, ZAR, ISK

**🕐 Updated:** Live rates from European Central Bank"""
        
        keyboard = [[InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in currency command: {e}")

async def convert_currency(amount, from_currency, to_currency):
    """Convert currency using Frankfurter API (free, unlimited)"""
    try:
        url = f"https://api.frankfurter.app/latest?amount={amount}&from={from_currency.upper()}&to={to_currency.upper()}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            converted_amount = data['rates'][to_currency.upper()]
            rate = converted_amount / amount
            return {
                'success': True,
                'amount': amount,
                'from': from_currency.upper(),
                'to': to_currency.upper(),
                'result': converted_amount,
                'rate': rate,
                'date': data.get('date', 'today')
            }
        else:
            return {'success': False, 'error': 'Currency not supported or API error'}
    except Exception as e:
        print(f"❌ Currency conversion error: {e}")
        return {'success': False, 'error': str(e)}

def generate_currency_keyboard(language='en', selection_type='from'):
    """Generate currency selection keyboard with popular currencies"""
    keyboard = []
    
    # Show popular currencies (2 per row)
    for i in range(0, len(POPULAR_CURRENCIES), 2):
        row = []
        for j in range(2):
            if i + j < len(POPULAR_CURRENCIES):
                curr = POPULAR_CURRENCIES[i + j]
                name = curr['name_ar'] if language == 'ar' else curr['name_en']
                button_text = f"{curr['flag']} {curr['code']}"
                callback_data = f"curr_{selection_type}_{curr['code']}"
                row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        keyboard.append(row)
    
    # Add "View All Currencies" button
    if language == 'ar':
        keyboard.append([InlineKeyboardButton("📋 عرض جميع العملات", callback_data=f"curr_all_{selection_type}")])
        keyboard.append([InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")])
    else:
        keyboard.append([InlineKeyboardButton("📋 View All Currencies", callback_data=f"curr_all_{selection_type}")])
        keyboard.append([InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")])
    
    return keyboard

async def show_currency_converter_start(query):
    """Show initial currency converter screen"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'
    
    # 📊 Track currency converter start
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "opened_currency_converter", "User started currency conversion process")
    
    if language == 'ar':
        text = """💱 **محول العملات**

مرحبًا! سأساعدك في تحويل العملات.

**الخطوة 1:** أدخل المبلغ الذي تريد تحويله
مثال: `1000` أو `500` أو `10000`

بعد ذلك، ستختار العملة من وإلى."""
    else:
        text = """💱 **Currency Converter**

Hi! I'll help you convert currencies.

**Step 1:** Enter the amount you want to convert
Example: `1000` or `500` or `10000`

Then you'll select the currency from and to."""
    
    keyboard = [[InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Set user state waiting for amount
    user_state_manager.set_state(user_id, 'currency_waiting_amount')
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_from_currency_selection(query, amount):
    """Show FROM currency selection"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'
    
    if language == 'ar':
        text = f"""💱 **محول العملات**

المبلغ: **{amount:,}**

**الخطوة 2:** اختر العملة التي تريد التحويل **منها**:"""
    else:
        text = f"""💱 **Currency Converter**

Amount: **{amount:,}**

**Step 2:** Select the currency you want to convert **FROM**:"""
    
    keyboard = generate_currency_keyboard(language, 'from')
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_to_currency_selection(query, amount, from_currency):
    """Show TO currency selection"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'
    
    # Get currency info
    from_curr = next((c for c in POPULAR_CURRENCIES if c['code'] == from_currency), None)
    from_flag = from_curr['flag'] if from_curr else ''
    
    if language == 'ar':
        text = f"""💱 **محول العملات**

المبلغ: **{amount:,}**
من: **{from_flag} {from_currency}**

**الخطوة 3:** اختر العملة التي تريد التحويل **إليها**:"""
    else:
        text = f"""💱 **Currency Converter**

Amount: **{amount:,}**
From: **{from_flag} {from_currency}**

**Step 3:** Select the currency you want to convert **TO**:"""
    
    keyboard = generate_currency_keyboard(language, 'to')
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_all_currencies_list(query, selection_type):
    """Show complete list of all supported currencies"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'
    
    if language == 'ar':
        text = f"""💱 **جميع العملات المدعومة ({len(SUPPORTED_CURRENCIES)} عملة)**

**العملات الشائعة:**
"""
    else:
        text = f"""💱 **All Supported Currencies ({len(SUPPORTED_CURRENCIES)} currencies)**

**Popular Currencies:**
"""
    
    # Add popular currencies list
    for curr in POPULAR_CURRENCIES:
        name = curr['name_ar'] if language == 'ar' else curr['name_en']
        text += f"\n{curr['flag']} **{curr['code']}** - {name}"
    
    if language == 'ar':
        text += "\n\n**عملات إضافية:**\n"
    else:
        text += "\n\n**Additional Currencies:**\n"
    
    # Add other currencies (not in popular list)
    popular_codes = [c['code'] for c in POPULAR_CURRENCIES]
    other_currencies = {code: name for code, name in SUPPORTED_CURRENCIES.items() if code not in popular_codes}
    
    for code, name in sorted(other_currencies.items()):
        text += f"• {code} - {name}\n"
    
    if language == 'ar':
        text += "\n\n💡 **ملاحظة:** جميع الأسعار من البنك المركزي الأوروبي"
    else:
        text += "\n\n💡 **Note:** All rates from European Central Bank"
    
    keyboard = [[InlineKeyboardButton("⬅️ Back" if language == 'en' else "⬅️ رجوع", callback_data="ess_currency")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_services_message(update, language):
    """Show services as a message (not query) - NEW"""
    keyboard = [
        [InlineKeyboardButton(TEXTS[language]['service_study'], callback_data="service_study")],
        [InlineKeyboardButton(TEXTS[language]['service_work'], callback_data="service_work")],
        [InlineKeyboardButton(TEXTS[language]['service_cv'], callback_data="service_cv")],
        [InlineKeyboardButton(TEXTS[language]['travel_essentials'], callback_data="travel_essentials")],
        [InlineKeyboardButton(TEXTS[language]['help'], callback_data="help")],
        [InlineKeyboardButton(TEXTS[language]['statistics'], callback_data="statistics")],
        [InlineKeyboardButton(TEXTS[language]['contact'], callback_data="contact")],
        [InlineKeyboardButton(TEXTS[language]['change_language'], callback_data="change_lang")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        TEXTS[language]['services_title'],
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_language_selection(query, data):
    """Handle language selection - FIXED"""
    language = data.split('_')[1]
    user_id = query.from_user.id

    # ✅ Save language in memory
    user_state_manager.set_user_language(user_id, language)

    print(f"✅ Language selected: {language} for user {user_id}")
    
    # 📊 Track language selection
    language_name = "English" if language == 'en' else "Arabic"
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_language", language_name)

    await show_services_menu(query, language)

async def show_services_menu(query, language='en'):
    """Show services menu - FIXED"""
    # ✅ Ensure correct language is used
    if not language:
        language = 'en'

    print(f"🌐 Showing menu in language: {language}")

    keyboard = [
        [InlineKeyboardButton(TEXTS[language]['service_study'], callback_data="service_study")],
        [InlineKeyboardButton(TEXTS[language]['service_work'], callback_data="service_work")],
        [InlineKeyboardButton(TEXTS[language]['service_cv'], callback_data="service_cv")],
        [InlineKeyboardButton(TEXTS[language]['travel_essentials'], callback_data="travel_essentials")],
        [InlineKeyboardButton(TEXTS[language]['help'], callback_data="help")],
        [InlineKeyboardButton(TEXTS[language]['statistics'], callback_data="statistics")],
        [InlineKeyboardButton(TEXTS[language]['contact'], callback_data="contact")],
        [InlineKeyboardButton(TEXTS[language]['change_language'], callback_data="change_lang")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        TEXTS[language]['services_title'],
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_travel_essentials(query):
    """Show Travel Essentials menu with affiliate links"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'
    
    # 📊 Track viewing travel essentials menu
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "viewed_travel_essentials_menu", "User opened travel essentials")
    
    # Travel Essentials Menu - Professional order
    if language == 'ar':
        text = """✈️ **خدمات السفر الأساسية**

كل ما تحتاجه للسفر والانتقال:"""
        keyboard = [
            [InlineKeyboardButton("✈️ التحضير للرحلة", callback_data="ess_trip_prep")],
            [InlineKeyboardButton("💱 محول العملات", callback_data="ess_currency")],
            [InlineKeyboardButton("🏨 الإقامة", callback_data="ess_accommodation")],
            [InlineKeyboardButton("📱 بطاقة SIM دولية", callback_data="ess_sim")],
            [InlineKeyboardButton("🛡️ التأمين", callback_data="ess_insurance")],
            [InlineKeyboardButton("🎫 الأنشطة والجولات", callback_data="service_activities")],
            [InlineKeyboardButton("🛫 خدمات السفر", callback_data="service_travel")],
            [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
        ]
    else:
        text = """✈️ **Travel Essentials**

Everything you need for relocation and travel:"""
        keyboard = [
            [InlineKeyboardButton("✈️ Prepare for Your Trip", callback_data="ess_trip_prep")],
            [InlineKeyboardButton("💱 Currency Converter", callback_data="ess_currency")],
            [InlineKeyboardButton("🏨 Accommodation", callback_data="ess_accommodation")],
            [InlineKeyboardButton("📱 International SIM Card", callback_data="ess_sim")],
            [InlineKeyboardButton("🛡️ Travel Insurance", callback_data="ess_insurance")],
            [InlineKeyboardButton("🎫 Activities & Tours", callback_data="service_activities")],
            [InlineKeyboardButton("🛫 Travel Services", callback_data="service_travel")],
            [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_service_selection(query, data):
    """Handle service selection - FIXED"""
    service_type = data.split('_')[1]
    user_id = query.from_user.id

    # ✅ Get language from memory
    language = user_state_manager.get_user_language(user_id)

    print(f"🔍 Service selected: {service_type} in language: {language} for user {user_id}")
    
    # 📊 Track service selection
    service_names = {
        'study': 'Study Abroad',
        'work': 'Work Visa',
        'cv': 'CV & Cover Letter',
        'activities': 'Activities & Tours',
        'travel': 'Travel Services'
    }
    service_name = service_names.get(service_type, service_type)
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_service", service_name)

    # Direct services (don't need country selection)
    if service_type in ['activities', 'travel']:
        await handle_direct_services(query, service_type, language)
        return
    
    # CV & Cover Letter service (doesn't need country selection)
    if service_type == 'cv':
        await show_cv_menu(query, language)
        return

    # Save service in session
    user_state_manager.set_state(user_id, 'service_selected', {
        'service_type': service_type,
        'language': language
    })

    # Show country selection for traditional services
    await show_countries_menu(query, service_type, language)

async def handle_direct_services(query, service_type, language):
    """Handle direct services (no country needed) - FIXED LANGUAGE"""
    user_id = query.from_user.id

    # ✅ Get links for the correct language
    links = AFFILIATE_LINKS[language]

    if service_type == 'activities':
        link = links['klook']
        description = TEXTS[language]['activities_description']
        # 📊 Track activities link view
        track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "viewed_activities_link", "Activities & Tours (Klook)")
    elif service_type == 'travel':
        link = links['klook']
        description = TEXTS[language]['travel_description']
        # 📊 Track travel link view
        track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "viewed_travel_link", "Travel Services (Klook)")
    else:
        await show_services_menu(query, language)
        return

    # ✅ Use language-specific button text
    keyboard = [
        [InlineKeyboardButton(TEXTS[language]['open_link'], url=link)],
        [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        description,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_countries_menu(query, service_type, language):
    """Show countries menu - FIXED"""
    if not language:
        language = 'en'

    print(f"🌐 Showing countries in language: {language}")

    # Split countries into columns - NOW WITH ALL 28 COUNTRIES
    countries_list = list(COUNTRIES.keys())
    keyboard = []

    # Create 3 columns for better display with many countries
    for i in range(0, len(countries_list), 3):
        row = []
        for j in range(3):
            if i + j < len(countries_list):
                country = countries_list[i + j]
                country_name = COUNTRIES[country][language]
                row.append(InlineKeyboardButton(country_name, callback_data=f"country_{country}"))
        if row:  # Only add non-empty rows
            keyboard.append(row)

    # Add back button
    keyboard.append([InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    service_name = SERVICES[service_type][language]

    await query.edit_message_text(
        f"**{service_name}**\n\nChoose country:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_help_info(query):
    """Show help information - NEW"""
    user_id = query.from_user.id
    
    # 📊 Track user activity - Viewed help
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "viewed_help", "User viewed help information")

    # ✅ Get language from memory
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'

    keyboard = [
        [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        TEXTS[language]['help_info'],
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_contact_info(query):
    """Show contact information - FIXED"""
    user_id = query.from_user.id
    
    # 📊 Track user activity - Viewed contact info
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "viewed_contact", "User viewed contact information")

    # ✅ Get language from memory
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'

    keyboard = [
        [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        TEXTS[language]['contact_info'],
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_statistics(query):
    """Show public statistics - NEW"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'
    
    # 📊 Track user activity - Viewed statistics
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "viewed_statistics", "User viewed public statistics")
    
    try:
        conn = get_db_connection()
        if not conn:
            await query.edit_message_text("❌ Database connection error")
            return
            
        cursor = conn.cursor()
        
        # Get total consultations
        cursor.execute("SELECT COUNT(*) FROM bookings")
        total_consultations = cursor.fetchone()[0]
        
        # Get total detailed reports
        cursor.execute("SELECT COUNT(*) FROM report_requests")
        total_reports = cursor.fetchone()[0]
        
        # Get total AI sessions (FREE)
        cursor.execute("SELECT COUNT(*) FROM ai_sessions")
        total_ai_sessions = cursor.fetchone()[0]
        
        # Get total free reports requested
        cursor.execute("SELECT COUNT(*) FROM ai_sessions WHERE report_requested = TRUE")
        total_free_reports = cursor.fetchone()[0]
        
        conn.close()
        
        # Build statistics text
        if language == 'ar':
            stats_text = f"""📊 **إحصائيات المنصة**

📈 **الخدمات المدفوعة:**
• الاستشارات: {total_consultations}
• التقارير المفصلة: {total_reports}

🤖 **الخدمات المجانية:**
• جلسات الذكاء الاصطناعي: {total_ai_sessions}
• التقارير المجانية المطلوبة: {total_free_reports}

💡 **ملاحظة:** البيانات يتم تحديثها باستمرار"""
        else:
            stats_text = f"""📊 **Platform Statistics**

📈 **Paid Services:**
• Consultations: {total_consultations}
• Detailed Reports: {total_reports}

🤖 **Free Services:**
• AI Sessions: {total_ai_sessions}
• Free Reports Requested: {total_free_reports}

💡 **Note:** Data is updated continuously"""
        
        keyboard = [
            [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            stats_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        print(f"❌ Error showing statistics: {e}")
        await query.edit_message_text("❌ Error loading statistics.")

def escape_markdown(text):
    """Escape special Markdown characters"""
    if not text:
        return ""
    # Escape special markdown characters
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = str(text).replace(char, f'\\{char}')
    return text

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin statistics command - NEW"""
    user_id = update.effective_user.id
    
    # Check if user is admin
    ADMIN_ID = 245640981
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized. This command is only for administrators.")
        return
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
            
        cursor = conn.cursor()
        
        # Get all bookings with user details
        cursor.execute("""
            SELECT id, user_id, name, email, country, booking_date, booking_time, created_at 
            FROM bookings 
            ORDER BY created_at DESC
        """)
        bookings = cursor.fetchall()
        
        # Get all report requests with user details
        cursor.execute("""
            SELECT id, user_id, name, email, country, created_at 
            FROM report_requests 
            ORDER BY created_at DESC
        """)
        reports = cursor.fetchall()
        
        # Get all AI sessions
        cursor.execute("""
            SELECT id, user_id, telegram_username, first_name, language, country, service_type, 
                   started_at, completed_at, question_count, report_requested, report_email
            FROM ai_sessions 
            ORDER BY started_at DESC
        """)
        ai_sessions = cursor.fetchall()
        
        conn.close()
        
        # Build admin statistics
        admin_text = f"""👨‍💼 **ADMIN STATISTICS**

📊 **Overview:**
• Total Consultations: {len(bookings)}
• Total Detailed Reports: {len(reports)}
• Total AI Sessions: {len(ai_sessions)}

───────────────────

📅 **CONSULTATIONS ({len(bookings)}):**
"""
        
        if bookings:
            for booking in bookings:
                b_id, user_id_b, name, email, country, booking_date, booking_time, created = booking
                country_name = COUNTRIES.get(country, {}).get('en', country) if country in COUNTRIES else country
                admin_text += f"""
ID: {b_id} | User ID: {user_id_b}
👤 {escape_markdown(name)}
📧 {escape_markdown(email)}
🌍 {escape_markdown(country_name)}
📅 {escape_markdown(booking_date)} at ‎{escape_markdown(booking_time)}
🕒 Created: {escape_markdown(created)}
───────────────────
"""
        else:
            admin_text += "\nNo consultations yet.\n───────────────────\n"
        
        admin_text += f"\n📄 **DETAILED REPORTS ({len(reports)}):**\n"
        
        if reports:
            for report in reports:
                r_id, user_id_r, name, email, country, created = report
                country_name = COUNTRIES.get(country, {}).get('en', country) if country in COUNTRIES else country
                admin_text += f"""
ID: {r_id} | User ID: {user_id_r}
👤 {escape_markdown(name)}
📧 {escape_markdown(email)}
🌍 {escape_markdown(country_name)}
🕒 Created: {escape_markdown(created)}
───────────────────
"""
        else:
            admin_text += "\nNo detailed reports yet.\n"
        
        # Add AI Sessions section
        admin_text += f"\n\n🤖 **FREE AI SESSIONS ({len(ai_sessions)}):**\n"
        admin_text += "───────────────────\n"
        
        if ai_sessions:
            for ai_session in ai_sessions[:20]:  # Show last 20 sessions
                s_id, s_user_id, s_username, s_name, s_lang, s_country, s_service, s_started, s_completed, s_questions, s_report_req, s_email = ai_session
                country_name = COUNTRIES.get(s_country, {}).get('en', s_country) if s_country and s_country in COUNTRIES else s_country
                status = "✅ Completed" if s_completed else "🔄 Active"
                report_status = f"📧 Report Sent to: {escape_markdown(s_email)}" if s_report_req else "No report requested"
                
                admin_text += f"""
ID: {s_id} | User ID: {s_user_id} | {status}
👤 {escape_markdown(s_name)} (@{escape_markdown(s_username)})
🌍 {escape_markdown(country_name)} | 🎯 {escape_markdown(s_service)}
❓ Questions: {s_questions}/5
🗣️ Language: {escape_markdown(s_lang)}
{report_status}
🕒 Started: {escape_markdown(s_started)}
───────────────────
"""
        else:
            admin_text += "\nNo AI sessions yet.\n"
        
        # Send in chunks if too long
        if len(admin_text) > 4096:
            # Split into chunks
            chunks = [admin_text[i:i+4096] for i in range(0, len(admin_text), 4096)]
            for chunk in chunks:
                await update.message.reply_text(chunk, parse_mode='Markdown')
        else:
            await update.message.reply_text(admin_text, parse_mode='Markdown')
            
    except Exception as e:
        print(f"❌ Error in admin stats: {e}")
        await update.message.reply_text(f"❌ Error generating admin statistics: {e}")

async def export_emails_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all user emails - ADMIN ONLY"""
    user_id = update.effective_user.id
    
    # Check if user is admin
    ADMIN_ID = 245640981
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized. This command is only for administrators.")
        return
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
            
        cursor = conn.cursor()
        
        # Get all unique emails with user details
        cursor.execute("""
            SELECT DISTINCT email, name, user_id, 
                   (SELECT COUNT(*) FROM bookings WHERE email = u.email) as consultation_count,
                   (SELECT COUNT(*) FROM report_requests WHERE email = u.email) as report_count
            FROM (
                SELECT email, name, user_id FROM bookings
                UNION
                SELECT email, name, user_id FROM report_requests
            ) u
            ORDER BY email
        """)
        users = cursor.fetchall()
        
        conn.close()
        
        if not users:
            await update.message.reply_text("📭 No user emails found yet.")
            return
        
        # Build email export text
        export_text = f"""📧 **EMAIL EXPORT**

Total Unique Users: {len(users)}

─────────────────────

**Format 1: Email List (for copy/paste)**
"""
        
        # Simple email list
        email_list = []
        for email, name, uid, consultations, reports in users:
            email_list.append(email)
        
        export_text += ", ".join(email_list)
        
        export_text += "\n\n─────────────────────\n\n**Format 2: Detailed List**\n"
        
        # Detailed list
        for email, name, uid, consultations, reports in users:
            export_text += f"""
📧 {email}
👤 {name} (ID: {uid})
📊 Consultations: {consultations} | Reports: {reports}
─────────────────────
"""
        
        # Send in chunks if too long
        if len(export_text) > 4096:
            # Split into chunks
            chunks = [export_text[i:i+4096] for i in range(0, len(export_text), 4096)]
            for chunk in chunks:
                await update.message.reply_text(chunk, parse_mode='Markdown')
        else:
            await update.message.reply_text(export_text, parse_mode='Markdown')
        
        # Also send as a file
        from io import BytesIO
        email_file_content = "\n".join(email_list)
        email_file = BytesIO(email_file_content.encode('utf-8'))
        email_file.name = 'user_emails.txt'
        await update.message.reply_document(
            document=email_file,
            filename='user_emails.txt',
            caption=f"📎 All {len(users)} user emails exported"
        )
            
    except Exception as e:
        print(f"❌ Error exporting emails: {e}")
        await update.message.reply_text(f"❌ Error exporting emails: {e}")

# 🎒 Student Essentials Handlers
async def handle_student_essential(query, category):
    """Handle student essential category selection"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'
    
    # 📊 Track travel essential selection
    essential_names = {
        'banking': 'Banking & Money Transfer',
        'sim': 'International SIM Card',
        'insurance': 'Travel Insurance',
        'language': 'Language Learning',
        'accommodation': 'Accommodation',
        'currency': 'Currency Converter',
        'trip_prep': 'Trip Preparation'
    }
    essential_name = essential_names.get(category, category)
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "viewed_travel_essential", essential_name)
    
    # 💰 Banking & Money Transfer
    if category == "banking":
        if language == 'ar':
            text = """💰 **الخدمات المالية والتحويلات**

خدمات مالية موصى بها للطلاب الدوليين:

🔹 **Wise (TransferWise)**
تحويل الأموال بأفضل سعر
رسوم منخفضة جداً
✅ موثوق عالمياً

🔹 **Revolut**
حساب مصرفي دولي
بطاقة افتراضية وحقيقية
صرف عملات بدون رسوم

**💡 لماذا تحتاجها؟**
• تحويل الأموال من بلدك
• دفع الرسوم الدراسية
• الصرف اليومي في الخارج"""
            keyboard = [
                [InlineKeyboardButton("🔗 Wise - افتح حساب", url="https://wise.com/invite/u/YOUR_AFFILIATE_CODE")],
                [InlineKeyboardButton("🔗 Revolut - سجل الآن", url="https://revolut.com/referral/YOUR_AFFILIATE_CODE")],
                [InlineKeyboardButton("🔙 العودة", callback_data="travel_essentials")]
            ]
        else:
            text = """💰 **Banking & Money Transfer**

Recommended financial services for international students:

🔹 **Wise (TransferWise)**
Best exchange rates
Very low fees
✅ Trusted worldwide

🔹 **Revolut**
International bank account
Virtual & physical cards
Fee-free currency exchange

**💡 Why you need it:**
• Transfer money from your country
• Pay tuition fees
• Daily expenses abroad"""
            keyboard = [
                [InlineKeyboardButton("🔗 Open Wise Account", url="https://wise.com/invite/u/YOUR_AFFILIATE_CODE")],
                [InlineKeyboardButton("🔗 Sign up for Revolut", url="https://revolut.com/referral/YOUR_AFFILIATE_CODE")],
                [InlineKeyboardButton("🔙 Back", callback_data="travel_essentials")]
            ]
    
    # 📱 International SIM Card
    elif category == "sim":
        if language == 'ar':
            text = """📱 **بطاقة SIM دولية**

🔹 **Airalo eSIM**
✅ بطاقة eSIM فورية
✅ تغطية في أكثر من 190 دولة
✅ لا حاجة لبطاقة SIM فعلية

**💡 لماذا تحتاجها؟**
• استخدام الإنترنت فور الوصول
• لا تحتاج لتغيير البطاقة
• أسعار معقولة

**📦 باقات متنوعة:**
من 1GB إلى Unlimited Data"""
            keyboard = [
                [InlineKeyboardButton("🔗 احصل على Airalo eSIM", url="https://airalo.tpo.mx/jvfDjJ15")],
                [InlineKeyboardButton("🔙 العودة", callback_data="travel_essentials")]
            ]
        else:
            text = """📱 **International SIM Card**

🔹 **Airalo eSIM**
✅ Instant eSIM activation
✅ Coverage in 190+ countries
✅ No physical SIM card needed

**💡 Why you need it:**
• Internet upon arrival
• No SIM card swapping
• Affordable rates

**📦 Various plans:**
From 1GB to Unlimited Data"""
            keyboard = [
                [InlineKeyboardButton("🔗 Get Airalo eSIM", url="https://airalo.tpo.mx/jvfDjJ15")],
                [InlineKeyboardButton("🔙 Back", callback_data="travel_essentials")]
            ]
    
    # 🛡️ Travel Insurance
    elif category == "insurance":
        if language == 'ar':
            text = """🛡️ **التأمين الصحي للسفر**

🔹 **SafetyWing**
✅ تأمين صحي شامل
✅ يغطي 180+ دولة
✅ أسعار مناسبة للطلاب

**💡 ما يغطيه:**
• العلاج الطبي الطارئ
• الحوادث والإصابات
• فقدان الأمتعة

**📋 إلزامي** في معظم الدول الأوروبية!"""
            keyboard = [
                [InlineKeyboardButton("🔗 احصل على التأمين", url="https://safetywing.com/?referenceID=26428827&utm_source=26428827&utm_medium=Ambassador")],
                [InlineKeyboardButton("🔙 العودة", callback_data="travel_essentials")]
            ]
        else:
            text = """🛡️ **Travel Insurance**

🔹 **SafetyWing**
✅ Comprehensive health coverage
✅ Covers 180+ countries
✅ Student-friendly prices

**💡 What's covered:**
• Emergency medical treatment
• Accidents & injuries
• Lost luggage

**📋 Required** in most European countries!"""
            keyboard = [
                [InlineKeyboardButton("🔗 Get Insurance", url="https://safetywing.com/?referenceID=26428827&utm_source=26428827&utm_medium=Ambassador")],
                [InlineKeyboardButton("🔙 Back", callback_data="travel_essentials")]
            ]
    
    # 📚 Language Learning
    elif category == "language":
        if language == 'ar':
            text = """📚 **تعلم اللغات**

تعلم لغة البلد قبل السفر!

🔹 **Preply**
✅ معلمون متخصصون 1:1
✅ جداول مرنة
✅ تعلم سريع وفعال

🔹 **Duolingo Plus**
✅ تطبيق تفاعلي
✅ دروس يومية
✅ مناسب للمبتدئين

**🌍 لغات متاحة:**
الإنجليزية، الألمانية، الفرنسية، الإسبانية، الإيطالية، والمزيد!"""
            keyboard = [
                [InlineKeyboardButton("🔗 Preply - معلم خاص", url="https://preply.com/ar/?pref=YOUR_AFFILIATE_CODE")],
                [InlineKeyboardButton("🔗 Duolingo Plus", url="https://duolingo.com/plus?ref=YOUR_AFFILIATE_CODE")],
                [InlineKeyboardButton("🔙 العودة", callback_data="travel_essentials")]
            ]
        else:
            text = """📚 **Language Learning**

Learn the local language before you go!

🔹 **Preply**
✅ 1-on-1 specialized tutors
✅ Flexible schedules
✅ Fast & effective learning

🔹 **Duolingo Plus**
✅ Interactive app
✅ Daily lessons
✅ Perfect for beginners

**🌍 Available languages:**
English, German, French, Spanish, Italian, and more!"""
            keyboard = [
                [InlineKeyboardButton("🔗 Preply - Private Tutor", url="https://preply.com/?pref=YOUR_AFFILIATE_CODE")],
                [InlineKeyboardButton("🔗 Duolingo Plus", url="https://duolingo.com/plus?ref=YOUR_AFFILIATE_CODE")],
                [InlineKeyboardButton("🔙 Back", callback_data="travel_essentials")]
            ]
    
    # 🏨 Accommodation (uses Klook affiliate link)
    elif category == "accommodation":
        if language == 'ar':
            text = """🏨 **الإقامة والسكن**

احجز سكنك المثالي عبر Klook:

✅ فنادق وشقق مفروشة
✅ آلاف الخيارات حول العالم
✅ أسعار منافسة وحجز آمن

**💡 نصائح:**
• احجز مبكراً للحصول على أفضل سعر
• تحقق من المراجعات
• ابحث قرب الجامعة أو وسط المدينة"""
            keyboard = [
                [InlineKeyboardButton("🔗 ابحث عن سكن", url="https://klook.tpo.mx/1IPQswu1")],
                [InlineKeyboardButton("🔙 العودة", callback_data="travel_essentials")]
            ]
        else:
            text = """🏨 **Accommodation**

Book your perfect place via Klook:

✅ Hotels & Serviced Apartments
✅ Thousands of options worldwide
✅ Competitive prices & secure booking

**💡 Tips:**
• Book early for best prices
• Check reviews
• Look near university or city center"""
            keyboard = [
                [InlineKeyboardButton("🔗 Find Accommodation", url="https://klook.tpo.mx/1IPQswu1")],
                [InlineKeyboardButton("🔙 Back", callback_data="travel_essentials")]
            ]
    
    # 💱 Currency Converter
    elif category == "currency":
        if language == 'ar':
            text = """💱 **محول العملات**

احصل على أسعار الصرف الحية!

**💡 كيف يعمل:**
انقر على "💱 محول العملات" أو أرسل رسالة بهذا التنسيق:
`المبلغ من إلى`

**📌 أمثلة:**
• `1000 USD EUR` - دولار أمريكي إلى يورو
• `500 GBP TRY` - جنيه استرليني إلى ليرة تركية
• `100 EUR CHF` - يورو إلى فرنك سويسري

**🌍 العملات المدعومة (31 عملة إجمالاً):**
EUR, USD, GBP, TRY, CHF, CAD, AUD, SEK, NOK, DKK, PLN, CZK, HUF, RON, BGN, ILS, JPY, CNY, INR, KRW, SGD, MYR, THB, PHP, IDR, HKD, NZD, MXN, BRL, ZAR, ISK

**🕐 التحديث:** أسعار حية من البنك المركزي الأوروبي"""
            keyboard = [
                [InlineKeyboardButton("🔙 العودة", callback_data="travel_essentials")]
            ]
        else:
            text = """💱 **Currency Converter**

Get live exchange rates instantly!

**💡 How it works:**
Click "💱 Currency Converter" or send a message in this format:
`amount from to`

**📌 Examples:**
• `1000 USD EUR` - US Dollar to Euro
• `500 GBP TRY` - British Pound to Turkish Lira
• `100 EUR CHF` - Euro to Swiss Franc

**🌍 Supported Currencies (31 total):**
EUR, USD, GBP, TRY, CHF, CAD, AUD, SEK, NOK, DKK, PLN, CZK, HUF, RON, BGN, ILS, JPY, CNY, INR, KRW, SGD, MYR, THB, PHP, IDR, HKD, NZD, MXN, BRL, ZAR, ISK

**🕐 Updated:** Live rates from European Central Bank"""
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="travel_essentials")]
            ]
    
    # ✈️ Prepare for Your Trip
    elif category == "trip_prep":
        if language == 'ar':
            text = """✈️ **التحضير للرحلة**

قائمة المهام الأساسية:

**قبل السفر بشهر:**
☑️ افتح حساب Wise/Revolut
☑️ احصل على بطاقة eSIM
☑️ اشترِ التأمين الصحي

**قبل السفر بأسبوعين:**
☑️ احجز السكن
☑️ ابدأ تعلم اللغة
☑️ راجع المستندات المطلوبة

**قبل السفر بأسبوع:**
☑️ صرّف بعض المال المحلي
☑️ نزّل الخرائط Offline
☑️ راجع كل التفاصيل

**🎯 استخدم خدماتنا لتوفير المال!**"""
            keyboard = [
                [InlineKeyboardButton("💰 الخدمات المالية", callback_data="ess_banking")],
                [InlineKeyboardButton("📱 بطاقة SIM", callback_data="ess_sim")],
                [InlineKeyboardButton("🛡️ التأمين", callback_data="ess_insurance")],
                [InlineKeyboardButton("📚 تعلم اللغة", callback_data="ess_language")],
                [InlineKeyboardButton("🏨 السكن", callback_data="ess_accommodation")],
                [InlineKeyboardButton("🔙 العودة", callback_data="travel_essentials")]
            ]
        else:
            text = """✈️ **Prepare for Your Trip**

Essential checklist:

**One month before:**
☑️ Open Wise/Revolut account
☑️ Get eSIM card
☑️ Buy health insurance

**Two weeks before:**
☑️ Book accommodation
☑️ Start learning the language
☑️ Review required documents

**One week before:**
☑️ Exchange some local currency
☑️ Download offline maps
☑️ Double-check everything

**🎯 Use our services to save money!**"""
            keyboard = [
                [InlineKeyboardButton("💰 Banking Services", callback_data="ess_banking")],
                [InlineKeyboardButton("📱 SIM Card", callback_data="ess_sim")],
                [InlineKeyboardButton("🛡️ Insurance", callback_data="ess_insurance")],
                [InlineKeyboardButton("📚 Learn Language", callback_data="ess_language")],
                [InlineKeyboardButton("🏨 Accommodation", callback_data="ess_accommodation")],
                [InlineKeyboardButton("🔙 Back", callback_data="travel_essentials")]
            ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Button handler - FIXED"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    print(f"🔘 Button pressed: {data} by user {user_id}")

    try:
        # Handle different button types
        if data.startswith('lang_'):
            await handle_language_selection(query, data)
        elif data.startswith('service_'):
            await handle_service_selection(query, data)
        elif data.startswith('country_'):
            await handle_country_selection(query, data)
        elif data == 'back_services':
            # 📊 Track back to services button
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "clicked_back_services", "Returned to main services menu")
            # ✅ Get language for back button
            language = user_state_manager.get_user_language(user_id)
            await show_services_menu(query, language)
        elif data == 'travel_essentials':
            await show_travel_essentials(query)
        elif data == 'cv_cover':
            language = user_state_manager.get_user_language(user_id)
            await show_cv_menu(query, language)
        elif data.startswith('curr_from_'):
            # Handle FROM currency selection
            currency_code = data.split('_')[2]
            # 📊 Track FROM currency selection
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_currency_from", currency_code)
            state = user_state_manager.get_state(user_id)
            if state and 'amount' in state['data']:
                amount = state['data']['amount']
                # Save from currency and show TO selection
                user_state_manager.set_state(user_id, 'currency_select_to', {
                    'amount': amount,
                    'from_currency': currency_code
                })
                await show_to_currency_selection(query, amount, currency_code)
        elif data.startswith('curr_to_'):
            # Handle TO currency selection and perform conversion
            currency_code = data.split('_')[2]
            state = user_state_manager.get_state(user_id)
            if state and 'amount' in state['data'] and 'from_currency' in state['data']:
                amount = state['data']['amount']
                from_curr = state['data']['from_currency']
                # 📊 Track TO currency selection and conversion
                track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "converted_currency", f"{amount} {from_curr} to {currency_code}")
                
                # Perform conversion
                result = await convert_currency(amount, from_curr, currency_code)
                
                language = user_state_manager.get_user_language(user_id) or 'en'
                
                # Get currency info for display
                from_curr_info = next((c for c in POPULAR_CURRENCIES if c['code'] == from_curr), None)
                to_curr_info = next((c for c in POPULAR_CURRENCIES if c['code'] == currency_code), None)
                from_flag = from_curr_info['flag'] if from_curr_info else ''
                to_flag = to_curr_info['flag'] if to_curr_info else ''
                
                if result['success']:
                    if language == 'ar':
                        response_text = f"""💱 **نتيجة التحويل**

**المبلغ:** {result['amount']:,.2f} {from_flag} {result['from']}
**النتيجة:** {result['result']:,.2f} {to_flag} {result['to']}

**📊 سعر الصرف:** 1 {result['from']} = {result['rate']:.4f} {result['to']}
**📅 التاريخ:** {result['date']}

💡 لإجراء تحويل آخر، انقر على الزر أدناه:"""
                    else:
                        response_text = f"""💱 **Conversion Result**

**Amount:** {result['amount']:,.2f} {from_flag} {result['from']}
**Result:** {result['result']:,.2f} {to_flag} {result['to']}

**📊 Exchange Rate:** 1 {result['from']} = {result['rate']:.4f} {result['to']}
**📅 Date:** {result['date']}

💡 To make another conversion, click the button below:"""
                    
                    keyboard = [
                        [InlineKeyboardButton("🔄 New Conversion" if language == 'en' else "🔄 تحويل جديد", callback_data="ess_currency")],
                        [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
                    ]
                else:
                    if language == 'ar':
                        response_text = f"❌ خطأ في التحويل: {result.get('error', 'عملة غير مدعومة')}"
                    else:
                        response_text = f"❌ Conversion error: {result.get('error', 'Currency not supported')}"
                    
                    keyboard = [
                        [InlineKeyboardButton("🔄 Try Again" if language == 'en' else "🔄 حاول مرة أخرى", callback_data="ess_currency")],
                        [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
                    ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
                
                # Clear state
                user_state_manager.clear_state(user_id)
        elif data.startswith('curr_all_'):
            # Show all currencies list
            selection_type = data.split('_')[2]
            # 📊 Track view all currencies
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "viewed_all_currencies", f"Viewing all supported currencies ({selection_type})")
            await show_all_currencies_list(query, selection_type)
        elif data.startswith('ess_'):
            category = data.split('_', 1)[1]
            if category == 'currency':
                await show_currency_converter_start(query)
            else:
                await handle_student_essential(query, category)
        elif data == 'statistics':
            await show_statistics(query)
        elif data == 'help':
            await show_help_info(query)
        elif data == 'contact':
            await show_contact_info(query)
        elif data == 'change_lang':
            # 📊 Track language change click
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "clicked_change_language", "User opened language selection")
            # Show language selection again
            keyboard = [
                [InlineKeyboardButton("English 🇺🇸", callback_data="lang_en")],
                [InlineKeyboardButton("العربية 🇸🇦", callback_data="lang_ar")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "🌐 **Choose Language / اختر اللغة:**",
                reply_markup=reply_markup
            )
        elif data == 'ai_start':
            await handle_ai_selection(query, data)
        elif data == 'stop_ai_get_report':
            # 📊 Track stop AI and request report
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "requested_free_report", "User stopped AI and requested free report")
            await handle_stop_ai_get_report(query)
        elif data == 'detailed_report':
            # 📊 Track detailed report selection
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_detailed_report", "5 EUR Detailed Report")
            await handle_detailed_report(query)
        elif data == 'consultation':
            # 📊 Track consultation selection
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_consultation", "20 EUR Consultation")
            await handle_consultation(query)
        elif data.startswith('payment_'):
            await handle_payment_selection(query, data)
        elif data.startswith('date_'):
            # 📊 Track date selection
            selected_date = data.split('_')[1]
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_booking_date", selected_date)
            await handle_date_selection(query, data)
        elif data.startswith('time_'):
            # 📊 Track time selection
            parts = data.split('_')
            selected_time = parts[2] if len(parts) > 2 else "unknown"
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_booking_time", selected_time)
            await handle_time_selection(query, data)
        elif data == 'back_to_calendar':
            await handle_consultation(query)
        elif data == 'payment_confirmed':
            # 📊 Track payment confirmation
            track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "confirmed_payment", "User clicked 'I Paid' button")
            await handle_payment_confirmed(query)
        elif data.startswith('booked_'):
            # User clicked on already booked slot
            language = user_state_manager.get_user_language(user_id)
            text = "❌ This time slot is already booked. Please choose another time." if language == 'en' else "❌ هذا الوقت محجوز بالفعل. الرجاء اختيار وقت آخر."
            await query.answer(text, show_alert=True)
        elif data.startswith('cv_type_'):
            cv_type = data.split('_')[2]
            language = user_state_manager.get_user_language(user_id)
            await handle_cv_type_selection(query, cv_type, language)
        else:
            await query.edit_message_text("❌ Unknown command. Please use /start to begin.")

    except Exception as e:
        print(f"❌ Error in button handler: {e}")
        await query.edit_message_text("❌ An error occurred. Please try again.")

async def handle_country_selection(query, data):
    """Handle country selection - FIXED"""
    country = data.split('_')[1]
    user_id = query.from_user.id

    # ✅ Get language from memory
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'

    state = user_state_manager.get_state(user_id)
    service_type = state['data']['service_type'] if state else 'study'
    
    # 📊 Track country selection
    country_name = COUNTRIES.get(country, {}).get(language, country)
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_country", country_name)

    # Update user state
    user_state_manager.set_state(user_id, 'country_selected', {
        'service_type': service_type,
        'country': country,
        'language': language
    })

    # Show AI options
    await show_ai_options(query, service_type, country, language)

async def show_ai_options(query, service_type, country, language):
    """Show AI options - FIXED"""
    country_name = COUNTRIES[country][language]
    service_name = SERVICES[service_type][language]

    # Add all three options: AI, Report, Consultation
    keyboard = [
        [InlineKeyboardButton(
            "🤖 Ask AI Assistant (Free)" if language == 'en' else "🤖 مساعد الذكاء الاصطناعي (مجاني)", 
            callback_data="ai_start"
        )],
        [InlineKeyboardButton(
            "📋 Detailed Report (5 EUR)" if language == 'en' else "📋 تقرير مفصل (5 يورو)", 
            callback_data="detailed_report"
        )],
        [InlineKeyboardButton(
            "💬 Consultation (20 EUR)" if language == 'en' else "💬 استشارة (20 يورو)", 
            callback_data="consultation"
        )],
        [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"**{service_name} in {country_name}**\n\nAvailable options:" if language == 'en' else f"**{service_name} في {country_name}**\n\nالخيارات المتاحة:"

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_ai_selection(query, data):
    """Handle AI start - FIXED"""
    user_id = query.from_user.id

    # ✅ Get language from memory
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'

    state = user_state_manager.get_state(user_id)
    if not state:
        await show_services_menu(query, language)
        return

    service_type = state['data']['service_type']
    country = state['data']['country']
    country_name = COUNTRIES[country][language]
    service_name = SERVICES[service_type][language]
    
    # 📊 Track AI assistant start
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "started_ai_assistant", f"{service_name} - {country_name}")

    # Start AI conversation
    user_state_manager.set_state(user_id, 'ai_conversation', {
        'service_type': service_type,
        'country': country,
        'language': language,
        'questions_asked': 0
    })

    welcome_text = f"""
🤖 **AI Assistant**

You can now ask free questions about {service_name} in {country_name}

You have {MAX_AI_QUESTIONS} free questions remaining

Type your first question:
""" if language == 'en' else f"""
🤖 **مساعد الذكاء الاصطناعي**

يمكنك الآن طرح أسئلة مجانية عن {service_name} في {country_name}

لديك {MAX_AI_QUESTIONS} أسئلة مجانية متبقية

اكتب سؤالك الأول:
"""

    await query.edit_message_text(
        welcome_text,
        parse_mode='Markdown'
    )

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user text input - FIXED"""
    try:
        user_id = update.effective_user.id
        user_message = update.message.text

        # Check for currency conversion pattern (e.g., "1000 USD EUR")
        import re
        currency_pattern = r'^(\d+\.?\d*)\s+([A-Z]{3})\s+([A-Z]{3})$'
        match = re.match(currency_pattern, user_message.strip().upper())
        
        if match:
            amount = float(match.group(1))
            from_curr = match.group(2)
            to_curr = match.group(3)
            
            # Validate currencies are supported
            if from_curr not in SUPPORTED_CURRENCIES or to_curr not in SUPPORTED_CURRENCIES:
                language = user_state_manager.get_user_language(user_id) or 'en'
                if language == 'ar':
                    error_msg = f"""❌ **عملة غير مدعومة**

العملة {from_curr if from_curr not in SUPPORTED_CURRENCIES else to_curr} غير متوفرة.

**العملات المدعومة (31 عملة):**
EUR, USD, GBP, TRY, CHF, CAD, AUD, SEK, NOK, DKK, PLN, CZK, HUF, RON, BGN, ILS, JPY, CNY, INR, KRW, SGD, MYR, THB, PHP, IDR, HKD, NZD, MXN, BRL, ZAR, ISK

💡 **نصيحة:** استخدم زر "💱 محول العملات" لاختيار العملات بسهولة!"""
                else:
                    error_msg = f"""❌ **Currency Not Supported**

The currency {from_curr if from_curr not in SUPPORTED_CURRENCIES else to_curr} is not available.

**Supported Currencies (31 total):**
EUR, USD, GBP, TRY, CHF, CAD, AUD, SEK, NOK, DKK, PLN, CZK, HUF, RON, BGN, ILS, JPY, CNY, INR, KRW, SGD, MYR, THB, PHP, IDR, HKD, NZD, MXN, BRL, ZAR, ISK

💡 **Tip:** Use the "💱 Currency Converter" button to easily select currencies!"""
                await update.message.reply_text(error_msg, parse_mode='Markdown')
                return
            
            # 📊 Track text-based currency conversion
            track_user_activity(user_id, update.effective_user.username, update.effective_user.first_name, "converted_currency_text", f"{amount} {from_curr} to {to_curr}")
            
            # Convert currency
            result = await convert_currency(amount, from_curr, to_curr)
            
            if result['success']:
                language = user_state_manager.get_user_language(user_id) or 'en'
                if language == 'ar':
                    response = f"""💱 **تحويل العملات**

**المبلغ:** {result['amount']:,.2f} {result['from']}
**النتيجة:** {result['result']:,.2f} {result['to']}

**📊 سعر الصرف:** 1 {result['from']} = {result['rate']:.4f} {result['to']}
**📅 التاريخ:** {result['date']}

💡 لتحويل عملة أخرى، أرسل: `المبلغ من إلى`
مثال: `1000 IQD EUR`"""
                else:
                    response = f"""💱 **Currency Conversion**

**Amount:** {result['amount']:,.2f} {result['from']}
**Result:** {result['result']:,.2f} {result['to']}

**📊 Exchange Rate:** 1 {result['from']} = {result['rate']:.4f} {result['to']}
**📅 Date:** {result['date']}

💡 To convert another currency, send: `amount from to`
Example: `1000 IQD EUR`"""
                await update.message.reply_text(response, parse_mode='Markdown')
                return
            else:
                language = user_state_manager.get_user_language(user_id) or 'en'
                error_msg = "❌ Currency not supported or error occurred. Please check the currency codes." if language == 'en' else "❌ العملة غير مدعومة أو حدث خطأ. يرجى التحقق من رموز العملات."
                await update.message.reply_text(error_msg)
                return

        state = user_state_manager.get_state(user_id)

        # Check if waiting for currency amount
        if state and state['state'] == 'currency_waiting_amount':
            # Try to parse amount
            try:
                amount = float(user_message.strip().replace(',', ''))
                if amount <= 0:
                    raise ValueError("Amount must be positive")
                
                # Save amount and show FROM currency selection
                user_state_manager.set_state(user_id, 'currency_select_from', {'amount': amount})
                
                language = user_state_manager.get_user_language(user_id) or 'en'
                
                if language == 'ar':
                    text = f"""💱 **محول العملات**

المبلغ: **{amount:,}**

**الخطوة 2:** اختر العملة التي تريد التحويل **منها**:"""
                else:
                    text = f"""💱 **Currency Converter**

Amount: **{amount:,}**

**Step 2:** Select the currency you want to convert **FROM**:"""
                
                keyboard = generate_currency_keyboard(language, 'from')
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return
            except ValueError:
                language = user_state_manager.get_user_language(user_id) or 'en'
                error_msg = "❌ Please enter a valid number (e.g., 1000, 500.50)" if language == 'en' else "❌ الرجاء إدخال رقم صحيح (مثال: 1000، 500.50)"
                await update.message.reply_text(error_msg)
                return
        
        if state and state['state'] == 'ai_conversation':
            await handle_ai_conversation(update, state, user_message)
        elif state and state['state'] == 'collect_info_report':
            await handle_collect_info(update, state, user_message, 'report')
        elif state and state['state'] == 'collect_info_consultation':
            await handle_collect_info(update, state, user_message, 'consultation')
        elif state and state['state'] == 'collect_email':
            await handle_collect_email(update, state, user_message)
        elif state and state['state'] == 'collect_email_free_report':
            await handle_collect_email_free_report(update, state, user_message)
        elif state and state['state'] == 'cv_data_collection':
            await handle_cv_data_collection(update, state, user_message)
        else:
            # If no state, show main menu
            await show_main_menu_message(update)

    except Exception as e:
        print(f"❌ Error handling user input: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def handle_ai_conversation(update, state, user_message):
    """Handle AI conversation - FIXED"""
    user_id = update.effective_user.id
    data = state['data']

    # ✅ Get language from memory
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'

    # Check question count
    questions_asked = user_state_manager.get_question_count(user_id)
    
    # 📊 Track AI session in database
    if questions_asked == 0:
        # First question - create new AI session
        telegram_username = update.effective_user.username or "unknown"
        first_name = update.effective_user.first_name or "Unknown"
        country = data.get('country', 'Unknown')
        service_type = data.get('service_type', 'Unknown')
        
        create_ai_session(user_id, telegram_username, first_name, language, country, service_type)
        
        # Send admin notification for new session
        admin_user_data = {
            'user_id': user_id,
            'telegram_username': telegram_username,
            'first_name': first_name,
            'country': country,
            'service_type': service_type,
            'language': language
        }
        await send_admin_notification("ai_session_started", admin_user_data)

    if questions_asked >= MAX_AI_QUESTIONS:
        # Mark session as completed
        mark_session_completed(user_id)
        await update.message.reply_text(
            "🎉 Free questions finished!\n\nYou've used all available free questions." if language == 'en' else "🎉 انتهت الأسئلة المجانية!\n\nلقد استخدمت جميع الأسئلة المجانية المتاحة.",
            parse_mode='Markdown'
        )
        return

    # Add user question to conversation
    user_state_manager.add_conversation_message(user_id, "user", user_message)

    # Show "typing" action
    await update.message.chat.send_action(action="typing")

    # Get AI response
    conversation_history = user_state_manager.get_conversation(user_id)
    ai_response = await ai_assistant.get_ai_response(
        user_message, 
        conversation_history,
        data['country'],
        data['service_type'],
        language
    )

    # Add assistant response to conversation
    user_state_manager.add_conversation_message(user_id, "assistant", ai_response)
    
    # 📊 Update AI session with new question count
    new_question_count = questions_asked + 1
    update_ai_session(user_id, new_question_count)

    # Send response to user
    remaining_questions = MAX_AI_QUESTIONS - new_question_count

    # Escape markdown characters to prevent parsing errors
    def escape_markdown(text):
        """Escape special markdown characters"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    safe_ai_response = escape_markdown(ai_response)

    response_text = f"""
🤖 *AI Response:*

{safe_ai_response}

\-\-\-
Questions remaining: {remaining_questions}/{MAX_AI_QUESTIONS}
""" if language == 'en' else f"""
🤖 *رد الذكاء الاصطناعي:*

{safe_ai_response}

\-\-\-
الأسئلة المتبقية: {remaining_questions}/{MAX_AI_QUESTIONS}
"""

    # Add button to stop and get free report
    keyboard = [
        [InlineKeyboardButton(
            "📧 Stop & Get Free Report" if language == 'en' else "📧 توقف واحصل على تقرير مجاني",
            callback_data="stop_ai_get_report"
        )],
        [InlineKeyboardButton(
            "Back to Services" if language == 'en' else "العودة للخدمات",
            callback_data="back_services"
        )]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        response_text,
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )

async def handle_stop_ai_get_report(query):
    """Handle stopping AI and requesting free report"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id) or 'en'
    
    # Get the conversation history
    conversation = user_state_manager.get_conversation(user_id)
    
    # Save state to collect email for free report
    user_state_manager.set_state(user_id, 'collect_email_free_report', {
        'conversation': conversation,
        'language': language
    })
    
    text = """
📧 **Free Report**

Great! I'll send you a summary of our conversation.

Please enter your email address:
""" if language == 'en' else """
📧 **تقرير مجاني**

رائع! سأرسل لك ملخصاً لمحادثتنا.

الرجاء إدخال عنوان بريدك الإلكتروني:
"""
    
    await query.edit_message_text(text, parse_mode='Markdown')

async def handle_collect_info(update, state, user_message, order_type):
    """Handle collecting user name for report/consultation"""
    user_id = update.effective_user.id
    data = state['data']
    language = data.get('language', 'en')
    
    # Preserve all existing state data (including booking date/time for consultations)
    new_state_data = {
        'order_type': order_type,
        'name': user_message,
        'language': language,
        'country': data.get('country', ''),
        'service_type': data.get('service_type', 'study'),
        'conversation': data.get('conversation', [])  # Preserve conversation history
    }
    
    # For consultations, preserve booking data
    if order_type == 'consultation':
        new_state_data['selected_date'] = data.get('selected_date')
        new_state_data['selected_time'] = data.get('selected_time')
    
    # Save the name and ask for email
    user_state_manager.set_state(user_id, 'collect_email', new_state_data)
    
    text = "Thank you! Please enter your email address:" if language == 'en' else "شكراً! الرجاء إدخال عنوان بريدك الإلكتروني:"
    await update.message.reply_text(text)

async def handle_collect_email_free_report(update, state, user_message):
    """Handle collecting email for free AI conversation report"""
    try:
        print(f"🔍 Starting free report handler for user {update.effective_user.id}")
        
        user_id = update.effective_user.id
        data = state['data']
        language = data.get('language', 'en')
        conversation = data.get('conversation', [])
        
        print(f"📝 Language: {language}, Conversation length: {len(conversation)}")
        
        # Validate email (simple check)
        if '@' not in user_message or '.' not in user_message:
            text = "❌ Invalid email. Please enter a valid email address:" if language == 'en' else "❌ بريد إلكتروني غير صالح. الرجاء إدخال عنوان بريد إلكتروني صالح:"
            await update.message.reply_text(text)
            return
        
        print(f"✅ Email validated: {user_message}")
        
        # 📊 Mark report as requested in database
        try:
            mark_report_requested(user_id, user_message)
            print(f"✅ Report marked as requested in database")
        except Exception as e:
            print(f"⚠️ Database error (mark_report_requested): {e}")
        
        # 📊 Mark session as completed
        try:
            mark_session_completed(user_id)
            print(f"✅ Session marked as completed")
        except Exception as e:
            print(f"⚠️ Database error (mark_session_completed): {e}")
        
        # Clear the AI conversation state
        user_state_manager.set_state(user_id, None, {})
        print(f"✅ User state cleared")
        
        # Create conversation summary
        summary = "\n\n".join([f"Q: {msg['content']}" if msg['role'] == 'user' else f"A: {msg['content']}" 
                                for msg in conversation[-10:]])  # Last 10 messages
        print(f"✅ Conversation summary created ({len(summary)} chars)")
        
        # 📧 Send admin notification with conversation summary
        telegram_username = update.effective_user.username or "unknown"
        first_name = update.effective_user.first_name or "Unknown"
        question_count = user_state_manager.get_question_count(user_id)
        
        admin_user_data = {
            'user_id': user_id,
            'telegram_username': telegram_username,
            'first_name': first_name,
            'email': user_message,
            'country': data.get('country', 'Unknown'),
            'service_type': data.get('service_type', 'Unknown'),
            'language': language,
            'question_count': question_count
        }
        
        print(f"📧 Sending admin notification...")
        try:
            await send_admin_notification("free_report_requested", admin_user_data, summary)
            print(f"✅ Admin notification sent")
        except Exception as e:
            print(f"⚠️ Admin notification error: {e}")
        
        # Send the email with conversation summary FIRST
        print(f"📧 Sending email to user...")
        email_sent = await send_email_report(user_message, summary, language, "Free AI Conversation Report")
        
        # Show appropriate message based on email result
        if email_sent:
            print(f"✅ Free report sent to {user_message}")
            success_text = f"""
✅ **Free Report Sent!**

Your conversation summary has been sent to: {user_message}

Please check your email (including spam folder).

Thank you for using our AI Assistant!
""" if language == 'en' else f"""
✅ **تم إرسال التقرير المجاني!**

تم إرسال ملخص محادثتك إلى: {user_message}

يرجى التحقق من بريدك الإلكتروني (بما في ذلك مجلد الرسائل غير المرغوب فيها).

شكراً لاستخدامك مساعدنا الذكي!
"""
        else:
            print(f"⚠️ Failed to send email to {user_message}")
            success_text = f"""
❌ **Email Delivery Failed**

We couldn't send the email to: {user_message}

Please verify your email address is correct and try again.

Contact us if the problem persists:
📞 +32 467 685 250
📧 info@studyua.org
""" if language == 'en' else f"""
❌ **فشل إرسال البريد الإلكتروني**

لم نتمكن من إرسال البريد الإلكتروني إلى: {user_message}

يرجى التحقق من صحة عنوان بريدك الإلكتروني والمحاولة مرة أخرى.

اتصل بنا إذا استمرت المشكلة:
📞 +32 465 69 06 37
📧 info@studyua.org
"""
        
        keyboard = [
            [InlineKeyboardButton(
                "Back to Main Menu" if language == 'en' else "العودة للقائمة الرئيسية",
                callback_data="back_services"
            )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR in handle_collect_email_free_report: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        raise

async def handle_collect_email(update, state, user_message):
    """Handle collecting user email and show payment options"""
    user_id = update.effective_user.id
    data = state['data']
    language = data.get('language', 'en')
    order_type = data.get('order_type', 'report')
    name = data.get('name', '')
    
    # Validate email (simple check)
    if '@' not in user_message or '.' not in user_message:
        text = "❌ Invalid email. Please enter a valid email address:" if language == 'en' else "❌ بريد إلكتروني غير صالح. الرجاء إدخال عنوان بريد إلكتروني صالح:"
        await update.message.reply_text(text)
        return
    
    # Save email and show payment options - preserve booking data for consultations
    payment_data = {
        'order_type': order_type,
        'name': name,
        'email': user_message,
        'language': language,
        'country': data.get('country', ''),
        'service_type': data.get('service_type', 'study'),
        'conversation': data.get('conversation', [])  # Preserve conversation history
    }
    
    # For consultations, preserve booking date/time
    if order_type == 'consultation':
        payment_data['selected_date'] = data.get('selected_date')
        payment_data['selected_time'] = data.get('selected_time')
    
    user_state_manager.set_state(user_id, 'payment_pending', payment_data)
    
    price = "5 EUR" if order_type == 'report' else "20 EUR"
    text = f"""
✅ **Information Received**

Name: {name}
Email: {user_message}
Service: {"Detailed Report" if order_type == 'report' else "Consultation"}
Price: {price}

Please select your payment method:
""" if language == 'en' else f"""
✅ **تم استلام المعلومات**

الاسم: {name}
البريد الإلكتروني: {user_message}
الخدمة: {"تقرير مفصل" if order_type == 'report' else "استشارة"}
السعر: {price}

الرجاء اختيار طريقة الدفع:
"""
    
    keyboard = [
        [InlineKeyboardButton("💳 Stripe" if language == 'en' else "💳 سترايب", callback_data="payment_stripe")],
        [InlineKeyboardButton("💰 PayPal" if language == 'en' else "💰 باي بال", callback_data="payment_paypal")],
        [InlineKeyboardButton("Back to Services" if language == 'en' else "العودة للخدمات", callback_data="back_services")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_main_menu_message(update):
    """Show main menu from message - FIXED"""
    user = update.effective_user
    user_id = user.id

    # ✅ Get language from memory
    language = user_state_manager.get_user_language(user_id)
    if not language:
        language = 'en'

    keyboard = [
        [InlineKeyboardButton("English 🇺🇸", callback_data="lang_en")],
        [InlineKeyboardButton("العربية 🇸🇦", callback_data="lang_ar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Please choose your language or use /start to begin:",
        reply_markup=reply_markup
    )

async def handle_detailed_report(query):
    """Handle detailed report request"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id) or 'en'
    
    # Capture conversation history NOW before any state changes
    # Note: user_state_manager keeps last 10 messages only
    conversation = user_state_manager.get_conversation(user_id)
    print(f"📝 Capturing conversation for report: {len(conversation) if conversation else 0} messages")
    
    # Create a copy to prevent reference issues
    conversation_snapshot = list(conversation) if conversation else []
    
    # Get previous state to preserve country and service_type
    prev_state = user_state_manager.get_state(user_id)
    country = prev_state['data'].get('country', '') if prev_state and prev_state.get('data') else ''
    service_type = prev_state['data'].get('service_type', 'study') if prev_state and prev_state.get('data') else 'study'
    
    # Set state to collect user info - include conversation snapshot in state data
    user_state_manager.set_state(user_id, 'collect_info_report', {
        'order_type': 'report',
        'language': language,
        'country': country,
        'service_type': service_type,
        'conversation': conversation_snapshot  # Store conversation snapshot in state data
    })
    
    text = "📋 **Detailed Report (5 EUR)**\n\nPlease enter your full name:" if language == 'en' else "📋 **تقرير مفصل (5 يورو)**\n\nالرجاء إدخال اسمك الكامل:"
    
    keyboard = [[InlineKeyboardButton(
        "Back to Services" if language == 'en' else "العودة للخدمات", 
        callback_data="back_services"
    )]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_consultation(query):
    """Handle consultation request - Show calendar first"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id) or 'en'
    
    # Get previous state to preserve country and service_type
    prev_state = user_state_manager.get_state(user_id)
    country = prev_state['data'].get('country', '') if prev_state else ''
    service_type = prev_state['data'].get('service_type', 'study') if prev_state else 'study'
    
    # Set state to show calendar - preserve country
    user_state_manager.set_state(user_id, 'selecting_date', {
        'order_type': 'consultation',
        'language': language,
        'country': country,
        'service_type': service_type
    })
    
    text = "💬 **Consultation (20 EUR - 30 minutes)**\n\n📅 Please select a date for your consultation:\n\n" if language == 'en' else "💬 **استشارة (20 يورو - 30 دقيقة)**\n\n📅 الرجاء اختيار تاريخ للاستشارة:\n\n"
    text += "**Available:** Monday-Friday, 10:00-16:00 Belgium Time" if language == 'en' else "**متاح:** الإثنين-الجمعة، 10:00-16:00 توقيت بلجيكا"
    
    keyboard = generate_calendar_keyboard(language)
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_payment_selection(query, data):
    """Handle payment method selection"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id) or 'en'
    
    # Extract payment type (stripe/paypal)
    parts = data.split('_')
    payment_method = parts[1]  # stripe or paypal
    
    # Get order type from user state and save payment method
    state = user_state_manager.get_state(user_id)
    if state:
        state['data']['payment_method'] = payment_method
        user_state_manager.set_state(user_id, 'payment_pending', state['data'])
    
    order_type = state['data'].get('order_type', 'report') if state else 'report'
    
    # 📊 Track payment method selection
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_payment_method", f"{payment_method.title()} - {order_type}")
    
    # Payment links - Real Stripe and PayPal links
    payment_links = {
        'report': {
            'stripe': 'https://buy.stripe.com/4gM7sKchi19xeK22Wf6Zy02',  # 5 EUR Detailed Report
            'paypal': 'https://www.paypal.com/ncp/payment/KCDX8SVCNE6AY'  # 5 EUR Detailed Report
        },
        'consultation': {
            'stripe': 'https://buy.stripe.com/7sY14m6WY05tdFYfJ16Zy03',  # 20 EUR Consultation
            'paypal': 'https://www.paypal.com/ncp/payment/RVV3XKBS4HTW2'  # 20 EUR Consultation
        }
    }
    
    link = payment_links.get(order_type, {}).get(payment_method, payment_links['report']['stripe'])
    
    # Different message for consultations with booking info
    if order_type == 'consultation':
        booking_date = state['data'].get('selected_date', '')
        booking_time = state['data'].get('selected_time', '')
        
        if booking_date:
            date_obj = datetime.strptime(booking_date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%A, %B %d, %Y') if language == 'en' else f"{date_obj.day}/{date_obj.month}/{date_obj.year}"
        else:
            formatted_date = "N/A"
        
        text = f"""
✅ **Payment Information**

📅 Date: {formatted_date}
⏰ Time: {booking_time} (Belgium Time)
💰 Price: 20 EUR

Please click the button below to complete your payment via {payment_method.title()}.

After payment, click "I Paid" to confirm your booking.
""" if language == 'en' else f"""
✅ **معلومات الدفع**

📅 التاريخ: {formatted_date}
⏰ الوقت: {booking_time} (توقيت بلجيكا)
💰 السعر: 20 يورو

الرجاء النقر على الزر أدناه لإتمام الدفع عبر {payment_method.title()}.

بعد الدفع، انقر على "دفعت" لتأكيد حجزك.
"""
        keyboard = [
            [InlineKeyboardButton(f"💳 Pay via {payment_method.title()}" if language == 'en' else f"💳 الدفع عبر {payment_method.title()}", url=link)],
            [InlineKeyboardButton("✅ I Paid" if language == 'en' else "✅ دفعت", callback_data="payment_confirmed")],
            [InlineKeyboardButton("Back to Services" if language == 'en' else "العودة للخدمات", callback_data="back_services")]
        ]
    else:
        # For report - with "I Paid" button
        text = f"""
✅ **Payment Information**

💰 Price: 5 EUR
📋 Service: Detailed Report

Please click the button below to complete your payment via {payment_method.title()}.

After payment, click "I Paid" to confirm. We will send your detailed report within 24 hours.

Thank you!
""" if language == 'en' else f"""
✅ **معلومات الدفع**

💰 السعر: 5 يورو
📋 الخدمة: تقرير مفصل

الرجاء النقر على الزر أدناه لإتمام الدفع عبر {payment_method.title()}.

بعد الدفع، انقر على "دفعت" للتأكيد. سنرسل تقريرك المفصل خلال 24 ساعة.

شكراً لك!
"""
        keyboard = [
            [InlineKeyboardButton(f"💳 Pay via {payment_method.title()}" if language == 'en' else f"💳 الدفع عبر {payment_method.title()}", url=link)],
            [InlineKeyboardButton("✅ I Paid" if language == 'en' else "✅ دفعت", callback_data="payment_confirmed")],
            [InlineKeyboardButton("Back to Services" if language == 'en' else "العودة للخدمات", callback_data="back_services")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_date_selection(query, data):
    """Handle date selection - show time slots"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id) or 'en'
    
    # Extract date from callback data
    selected_date = data.split('_')[1]  # date_2025-11-15 -> 2025-11-15
    
    # Update state with selected date
    state = user_state_manager.get_state(user_id)
    if state:
        state['data']['selected_date'] = selected_date
        user_state_manager.set_state(user_id, 'selecting_time', state['data'])
    
    # Format date for display
    date_obj = datetime.strptime(selected_date, '%Y-%m-%d')
    if language == 'ar':
        day_names = ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
        formatted_date = f"{day_names[date_obj.weekday()]} {date_obj.day}/{date_obj.month}/{date_obj.year}"
    else:
        formatted_date = date_obj.strftime('%A, %B %d, %Y')
    
    text = f"📅 **Selected Date:** {formatted_date}\n\n⏰ Please select a time slot:\n\n" if language == 'en' else f"📅 **التاريخ المختار:** {formatted_date}\n\n⏰ الرجاء اختيار الوقت:\n\n"
    text += "**Belgium Time (CET/CEST)**" if language == 'en' else "**توقيت بلجيكا (CET/CEST)**"
    
    keyboard = generate_time_keyboard(selected_date, language)
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_time_selection(query, data):
    """Handle time selection - ask for name"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id) or 'en'
    
    # Extract date and time from callback data: time_2025-11-15_10:00
    parts = data.split('_')
    selected_date = parts[1]
    selected_time = parts[2]
    
    # Update state with selected time
    state = user_state_manager.get_state(user_id)
    if state:
        state['data']['selected_date'] = selected_date
        state['data']['selected_time'] = selected_time
        user_state_manager.set_state(user_id, 'collect_info_consultation', state['data'])
    
    # Format for display
    date_obj = datetime.strptime(selected_date, '%Y-%m-%d')
    formatted_date = date_obj.strftime('%A, %B %d, %Y') if language == 'en' else f"{date_obj.day}/{date_obj.month}/{date_obj.year}"
    
    text = f"""
✅ **Booking Details:**

📅 Date: {formatted_date}
⏰ Time: {selected_time} (Belgium Time)
⏱️ Duration: 30 minutes

Please enter your full name:
""" if language == 'en' else f"""
✅ **تفاصيل الحجز:**

📅 التاريخ: {formatted_date}
⏰ الوقت: {selected_time} (توقيت بلجيكا)
⏱️ المدة: 30 دقيقة

الرجاء إدخال اسمك الكامل:
"""
    
    keyboard = [[InlineKeyboardButton(
        "⬅️ Back to Calendar" if language == 'en' else "⬅️ العودة للتقويم",
        callback_data="back_to_calendar"
    )]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_payment_confirmed(query):
    """Handle payment confirmation - save booking/report and send emails"""
    user_id = query.from_user.id
    language = user_state_manager.get_user_language(user_id) or 'en'
    
    # Get details from state
    state = user_state_manager.get_state(user_id)
    if not state:
        text = "❌ Session expired. Please start again." if language == 'en' else "❌ انتهت الجلسة. الرجاء البدء من جديد."
        await query.edit_message_text(text)
        return
    
    data = state['data']
    order_type = data.get('order_type', 'report')
    name = data.get('name')
    email = data.get('email')
    payment_method = data.get('payment_method')
    
    try:
        if order_type == 'consultation':
            # Handle consultation booking
            booking_date = data.get('selected_date')
            booking_time = data.get('selected_time')
            
            booking_id = save_booking(
                user_id=user_id,
                name=name,
                email=email,
                service_type='consultation',
                country=data.get('country', ''),
                booking_date=booking_date,
                booking_time=booking_time,
                payment_method=payment_method
            )
            
            if not booking_id:
                raise Exception("Failed to save booking")
                
            # Format date for emails
            date_obj = datetime.strptime(booking_date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%A, %B %d, %Y')
            
            # Send confirmation email to client
            client_subject = "Consultation Booking Confirmed - Elevate Platform" if language == 'en' else "تم تأكيد حجز الاستشارة - منصة Elevate"
            client_content = f"""
Your consultation has been booked successfully!

Booking Details:
- Name: {name}
- Date: {formatted_date}
- Time: {booking_time} (Belgium Time - CET/CEST)
- Duration: 30 minutes
- Booking ID: #{booking_id}

We will send you the meeting link shortly via email.

Thank you for choosing Elevate Platform!
""" if language == 'en' else f"""
تم حجز استشارتك بنجاح!

تفاصيل الحجز:
- الاسم: {name}
- التاريخ: {formatted_date}
- الوقت: {booking_time} (توقيت بلجيكا - CET/CEST)
- المدة: 30 دقيقة
- رقم الحجز: #{booking_id}

سنرسل لك رابط الاجتماع قريباً عبر البريد الإلكتروني.

شكراً لاختيارك منصة Elevate!
"""
            
            await send_email_report(email, client_content, language, "Consultation Booking")
            
            # Show success message
            text = f"""
🎉 **Booking Confirmed!**

Your consultation has been successfully booked.

📧 A confirmation email has been sent to: {email}

We will send you the meeting link shortly.

Thank you! 🙏
""" if language == 'en' else f"""
🎉 **تم تأكيد الحجز!**

تم حجز استشارتك بنجاح.

📧 تم إرسال رسالة تأكيد إلى: {email}

سنرسل لك رابط الاجتماع قريباً.

شكراً لك! 🙏
"""
            
            print(f"✅ Consultation booking #{booking_id} confirmed for {name} on {booking_date} at {booking_time}")
            
        else:
            # Handle report request (5 EUR)
            country = data.get('country', '')
            service_type = data.get('service_type', 'study')
            
            # Get conversation history from state data (preserved through the flow)
            conversation = data.get('conversation', [])
            print(f"📝 Processing conversation for report: {len(conversation) if conversation else 0} messages")
            
            if conversation and len(conversation) > 0:
                # Format conversation as Q&A pairs
                formatted_messages = []
                for msg in conversation:
                    if msg['role'] == 'user':
                        formatted_messages.append(f"👤 USER: {msg['content']}")
                    else:
                        formatted_messages.append(f"🤖 AI: {msg['content']}")
                
                conversation_summary = "\n\n".join(formatted_messages)
                conversation_header = f"=== Recent AI Conversation ({len(conversation)} messages) ==="
                print(f"✅ Conversation summary created: {len(conversation_summary)} characters")
            else:
                conversation_summary = "User ordered detailed report without using AI assistant first."
                conversation_header = "=== No AI Conversation History ==="
                print(f"⚠️ No conversation history found for user {user_id}")
            
            request_id = save_report_request(
                user_id=user_id,
                name=name,
                email=email,
                country=country,
                service_type=service_type,
                conversation_summary=conversation_summary,
                payment_method=payment_method
            )
            
            if not request_id:
                raise Exception("Failed to save report request")
            
            # Send confirmation email to client
            client_subject = "Report Request Received - Elevate Platform" if language == 'en' else "تم استلام طلب التقرير - منصة Elevate"
            client_content = f"""
Thank you for your order!

Your detailed report request has been received and will be prepared by our team.

Order Details:
- Name: {name}
- Service: Detailed Report
- Country of Interest: {country if country else 'Not specified'}
- Request ID: #{request_id}

📧 You will receive your detailed report within 24 hours at this email address.

Thank you for choosing Elevate Platform!
""" if language == 'en' else f"""
شكراً لطلبك!

تم استلام طلب تقريرك المفصل وسيتم إعداده من قبل فريقنا.

تفاصيل الطلب:
- الاسم: {name}
- الخدمة: تقرير مفصل
- الدولة المهتم بها: {country if country else 'غير محدد'}
- رقم الطلب: #{request_id}

📧 ستتلقى تقريرك المفصل خلال 24 ساعة على هذا البريد الإلكتروني.

شكراً لاختيارك منصة Elevate!
"""
            
            await send_email_report(email, client_content, language, "Detailed Report")
            
            # Show success message
            text = f"""
🎉 **Report Request Confirmed!**

Your detailed report request has been received.

📧 You will receive your report within 24 hours at: {email}

Our team will prepare a comprehensive report based on your questions.

Thank you! 🙏
""" if language == 'en' else f"""
🎉 **تم تأكيد طلب التقرير!**

تم استلام طلب تقريرك المفصل.

📧 ستتلقى تقريرك خلال 24 ساعة على: {email}

سيقوم فريقنا بإعداد تقرير شامل بناءً على أسئلتك.

شكراً لك! 🙏
"""
            
            print(f"✅ Report request #{request_id} confirmed for {name}")
        
        # Clear user state
        user_state_manager.clear_state(user_id)
        
        # Common success buttons
        keyboard = [[InlineKeyboardButton(
            "Back to Main Menu" if language == 'en' else "العودة للقائمة الرئيسية",
            callback_data="back_services"
        )]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        print(f"❌ Error saving {order_type}: {e}")
        text = "❌ Error processing your request. Please contact support." if language == 'en' else "❌ خطأ في معالجة طلبك. الرجاء الاتصال بالدعم."
        await query.edit_message_text(text)

async def handle_cv_data_collection(update, state, user_message):
    """Handle CV/Cover Letter data collection and show payment"""
    user_id = update.effective_user.id
    cv_type = state['data']['cv_type']
    language = state['data']['language']
    
    # Save the user's information to database
    user_name = update.effective_user.full_name
    email = user_message.split('\n')[0] if '\n' in user_message else "Not provided"
    
    # Save to database
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Database connection error")
        return
        
    cursor = conn.cursor()
    belgium_tz = ZoneInfo(TIMEZONE)
    created_at = datetime.now(belgium_tz).isoformat()
    
    try:
        cursor.execute('''
            INSERT INTO cv_requests (user_id, request_type, full_name, email, work_experience, 
                                    payment_method, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (user_id, cv_type, user_name, email, user_message, 'pending', created_at))
        request_id = cursor.fetchone()[0]
        conn.commit()
        print(f"💾 CV Request saved: ID={request_id}, Type={cv_type}, User={user_name}")
    except Exception as e:
        print(f"❌ Error saving CV request: {e}")
        await update.message.reply_text("❌ Error saving your information. Please try again.")
        return
    finally:
        conn.close()
    
    # Show payment options
    prices = {'cv': '€10', 'cover': '€10', 'bundle': '€15'}
    price = prices[cv_type]
    
    # Payment links - Stripe and PayPal
    stripe_links = {
        'cv': 'https://buy.stripe.com/00w8wO3KMaK71XgaoH6Zy06',
        'cover': 'https://buy.stripe.com/6oU3cu0yA5pN8lE2Wf6Zy07',
        'bundle': 'https://buy.stripe.com/14A5kC0yA9G3atM54n6Zy08'
    }
    
    paypal_links = {
        'cv': 'https://www.paypal.com/ncp/payment/BZWFQ2HKVTGYY',
        'cover': 'https://www.paypal.com/ncp/payment/SKT338NRSXKTW',
        'bundle': 'https://www.paypal.com/ncp/payment/YDZWFF7YFBW4E'
    }
    
    if language == 'ar':
        text = f"""✅ **تم استلام معلوماتك بنجاح!**

📋 **الخدمة:** {cv_type.upper()}
💰 **السعر:** {price}
🔢 **رقم الطلب:** #{request_id}

**الخطوة التالية:**
اختر طريقة الدفع أدناه لإتمام طلبك

⏱️ **موعد التسليم:** خلال 48 ساعة بعد الدفع

💡 بعد الدفع، سنبدأ العمل على {cv_type} الخاص بك فوراً!"""
        
        keyboard = [
            [InlineKeyboardButton(f"💳 ادفع {price} (Stripe)", url=stripe_links[cv_type])]
        ]
        # Add PayPal button only if link exists
        if paypal_links.get(cv_type):
            keyboard.append([InlineKeyboardButton(f"💰 ادفع {price} (PayPal)", url=paypal_links[cv_type])])
        keyboard.append([InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")])
    else:
        text = f"""✅ **Your information has been received successfully!**

📋 **Service:** {cv_type.upper()}
💰 **Price:** {price}
🔢 **Order Number:** #{request_id}

**Next Step:**
Choose your payment method below to complete your order

⏱️ **Delivery:** Within 48 hours after payment

💡 After payment, we'll start working on your {cv_type} immediately!"""
        
        keyboard = [
            [InlineKeyboardButton(f"💳 Pay {price} (Stripe)", url=stripe_links[cv_type])]
        ]
        # Add PayPal button only if link exists
        if paypal_links.get(cv_type):
            keyboard.append([InlineKeyboardButton(f"💰 Pay {price} (PayPal)", url=paypal_links[cv_type])])
        keyboard.append([InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    # Clear state
    user_state_manager.clear_state(user_id)

async def handle_cv_type_selection(query, cv_type, language):
    """Handle CV type selection and collect information"""
    user_id = query.from_user.id
    
    # 📊 Track CV type selection
    cv_type_names = {'cv': 'CV Only', 'cover': 'Cover Letter Only', 'bundle': 'CV + Cover Letter Bundle'}
    cv_type_name = cv_type_names.get(cv_type, cv_type)
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "selected_cv_type", cv_type_name)
    
    # Save the CV type in state
    user_state_manager.set_state(user_id, 'cv_data_collection', {
        'cv_type': cv_type,
        'language': language
    })
    
    # Ask for basic information
    if language == 'ar':
        type_names = {'cv': 'السيرة الذاتية', 'cover': 'رسالة التغطية', 'bundle': 'الباقة (سيرة + رسالة)'}
        text = f"""📝 **{type_names[cv_type]}**

الرجاء إرسال معلوماتك بالترتيب التالي:

**1️⃣ الاسم الكامل:**
**2️⃣ البريد الإلكتروني:**
**3️⃣ رقم الهاتف:**"""
        
        if cv_type in ['cv', 'bundle']:
            text += """
**4️⃣ الخبرات العملية:** (الوظائف السابقة)
**5️⃣ التعليم:** (الشهادات والجامعات)
**6️⃣ المهارات:** (اللغات والبرامج)"""
        
        if cv_type in ['cover', 'bundle']:
            text += """
**7️⃣ الوظيفة المستهدفة:**
**8️⃣ اسم الشركة:**
**9️⃣ لماذا هذه الوظيفة؟:**"""
        
        text += """

💡 **مثال:**
الاسم: أحمد محمد
البريد: ahmed@email.com  
الهاتف: +32 123 456 789
الخبرة: مدير مبيعات في شركة ABC لمدة 3 سنوات
التعليم: بكالوريوس إدارة أعمال - جامعة القاهرة
المهارات: Excel, CRM, الإنجليزية (متقدم), العربية (أصلي)

📤 **أرسل معلوماتك الآن:**"""
    else:
        type_names = {'cv': 'CV', 'cover': 'Cover Letter', 'bundle': 'Bundle (CV + Cover Letter)'}
        text = f"""📝 **{type_names[cv_type]}**

Please send your information in the following order:

**1️⃣ Full Name:**
**2️⃣ Email:**
**3️⃣ Phone Number:**"""
        
        if cv_type in ['cv', 'bundle']:
            text += """
**4️⃣ Work Experience:** (Previous jobs)
**5️⃣ Education:** (Degrees and universities)
**6️⃣ Skills:** (Languages and software)"""
        
        if cv_type in ['cover', 'bundle']:
            text += """
**7️⃣ Target Job Title:**
**8️⃣ Company Name:**
**9️⃣ Why this job?:**"""
        
        text += """

💡 **Example:**
Name: Ahmed Mohamed
Email: ahmed@email.com
Phone: +32 123 456 789
Experience: Sales Manager at ABC Company for 3 years
Education: Bachelor in Business Administration - Cairo University
Skills: Excel, CRM, English (Advanced), Arabic (Native)

📤 **Send your information now:**"""
    
    keyboard = [
        [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_cv_menu(query, language):
    """Show CV & Cover Letter service options"""
    user_id = query.from_user.id
    
    # 📊 Track CV menu view
    track_user_activity(user_id, query.from_user.username, query.from_user.first_name, "viewed_cv_menu", "User opened CV & Cover Letter menu")
    
    if language == 'ar':
        text = """📄 **خدمات السيرة الذاتية ورسالة التغطية**

اختر الخدمة المناسبة لك:

📄 **السيرة الذاتية - 10€**
• سيرة ذاتية احترافية مصممة خصيصاً لك
• تصميم جذاب واحترافي
• جاهزة للإرسال

✉️ **رسالة التغطية - 10€**
• رسالة تغطية مخصصة للوظيفة
• محتوى احترافي ومقنع
• زيادة فرص القبول

📦 **الباقة (سيرة + رسالة) - 15€**
• وفر 5 يورو!
• سيرة ذاتية كاملة + رسالة تغطية
• الحل الأمثل للباحثين عن عمل

💡 **كيف تعمل:**
1. اختر الخدمة
2. أدخل معلوماتك
3. ادفع بشكل آمن
4. نرسل لك العمل خلال 48 ساعة"""
        
        keyboard = [
            [InlineKeyboardButton("📄 سيرة ذاتية (10€)", callback_data="cv_type_cv")],
            [InlineKeyboardButton("✉️ رسالة تغطية (10€)", callback_data="cv_type_cover")],
            [InlineKeyboardButton("📦 الباقة (15€)", callback_data="cv_type_bundle")],
            [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
        ]
    else:
        text = """📄 **CV & Cover Letter Services**

Choose the service that fits your needs:

📄 **CV Only - €10**
• Professional CV tailored for you
• Attractive & professional design
• Ready to send

✉️ **Cover Letter Only - €10**
• Customized cover letter for the job
• Professional & persuasive content
• Increase your acceptance chances

📦 **Bundle (CV + Cover Letter) - €15**
• Save €5!
• Complete CV + Cover Letter
• Best value for job seekers

💡 **How it works:**
1. Choose your service
2. Enter your information
3. Pay securely
4. Receive your work within 48 hours"""
        
        keyboard = [
            [InlineKeyboardButton("📄 CV Only (€10)", callback_data="cv_type_cv")],
            [InlineKeyboardButton("✉️ Cover Letter Only (€10)", callback_data="cv_type_cover")],
            [InlineKeyboardButton("📦 Bundle (€15)", callback_data="cv_type_bundle")],
            [InlineKeyboardButton(TEXTS[language]['back_services'], callback_data="back_services")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Error handler"""
    try:
        error = context.error
        print(f"❌ Error: {error}")

        if update and update.effective_user:
            await update.effective_message.reply_text(
                "❌ An unexpected error occurred. Please try again or contact support."
            )
    except Exception as e:
        print(f"❌ Error in error handler: {e}")

# 🔧 Main execution for Railway
def main():
    try:
        print("🔧 Initializing Elevate Bot on Railway...")
        print(f"🌍 Countries: {len(COUNTRIES)} countries available")
        print(f"🛫 Services: {len(SERVICES)} services available")
        print(f"🌐 Language System: FIXED - English/Arabic with proper links")
        print(f"🏷️  Platform Name: Elevate")

        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        print("✅ Elevate bot application created")

        # Add handlers - FIXED: Added all command handlers
        # Basic commands
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("services", services_command))
        application.add_handler(CommandHandler("language", language_command))
        
        # Quick access shortcuts
        application.add_handler(CommandHandler("study", study_command))
        application.add_handler(CommandHandler("work", work_command))
        application.add_handler(CommandHandler("travel", travel_command))
        application.add_handler(CommandHandler("currency", currency_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("contact", contact_command))
        
        # Admin commands
        application.add_handler(CommandHandler("admin_stats", admin_stats_command))
        application.add_handler(CommandHandler("export_emails", export_emails_command))
        
        # Handlers
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))

        # Add error handler
        application.add_error_handler(error_handler)
        
        # Set bot commands menu (shows in Telegram UI)
        from telegram import BotCommand
        async def post_init(application: Application) -> None:
            """Set bot commands menu"""
            commands = [
                BotCommand("start", "Start the bot"),
                BotCommand("services", "View all services"),
                BotCommand("study", "Study Abroad"),
                BotCommand("work", "Work Visa"),
                BotCommand("travel", "Travel Essentials"),
                BotCommand("currency", "Currency Converter"),
                BotCommand("stats", "View statistics"),
                BotCommand("contact", "Contact information"),
                BotCommand("language", "Change language"),
                BotCommand("help", "Help & guide"),
            ]
            await application.bot.set_my_commands(commands)
            print("✅ Bot commands menu set successfully")
        
        application.post_init = post_init

        print("🎉 Elevate Bot is ready to work on Railway!")
        print("🤖 Features: AI Assistant, Multi-language, Affiliate Links")
        print("🌐 Languages: English & Arabic - PROPERLY WORKING")
        print("🏷️  Brand: Elevate Platform")
        print("🔗 Go to Telegram and search for your bot, then type /start")
        print("📋 Available Commands: /start, /study, /work, /travel, /currency, /stats, /contact, /help")

        # Start bot on Railway
        print("🔄 Starting Elevate bot polling...")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )

    except Exception as e:
        print(f"❌ Main error: {e}")

if __name__ == '__main__':
    main()