from collections import namedtuple

# Currency rates
CURRENCY_RATES = {
    'WL': 1,
    'DL': 100,
    'BGL': 10000
}

# Balance namedtuple
Balance = namedtuple('Balance', ['wl', 'dl', 'bgl'])

# TransactionError definition
class TransactionError(Exception):
    pass

# Maximum items per message
MAX_ITEMS_PER_MESSAGE = 10

# Stock status constants
STATUS_AVAILABLE = 'AVAILABLE'
STATUS_SOLD = 'SOLD'
STATUS_DELETED = 'DELETED'
STATUS_PENDING = 'PENDING'

# Transaction type constants
TRANSACTION_PURCHASE = 'PURCHASE'
TRANSACTION_REFUND = 'REFUND'
TRANSACTION_ADMIN = 'ADMIN'
TRANSACTION_DEPOSIT = 'DEPOSIT'
TRANSACTION_WITHDRAW = 'WITHDRAW'
TRANSACTION_ADMIN_ADD = 'ADMIN_ADD'
TRANSACTION_ADMIN_REMOVE = 'ADMIN_REMOVE'
TRANSACTION_ADMIN_RESET = 'ADMIN_RESET'

# Time constants
UPDATE_INTERVAL = 55  # seconds
COOLDOWN_SECONDS = 3
PAGE_TIMEOUT = 60  # seconds

# Embed colors (in decimal)
COLOR_SUCCESS = 0x00ff00  # Green
COLOR_ERROR = 0xff0000    # Red
COLOR_INFO = 0x0000ff     # Blue
COLOR_WARNING = 0xffff00  # Yellow

# Bot response messages dictionary
MESSAGES = {
    'ERROR_GENERIC': "❌ An error occurred. Please try again later.",
    'NO_PERMISSION': "❌ You don't have permission to use this command.",
    'COOLDOWN': "⚠️ Please wait {seconds} seconds before using this command again.",
    'INVALID_AMOUNT': "❌ Please enter a valid amount.",
    'INSUFFICIENT_BALANCE': "❌ Insufficient balance.",
    'INSUFFICIENT_STOCK': "❌ Insufficient stock available.",
    'SUCCESS_PURCHASE': "✅ Purchase successful! Check your DMs for the items.",
    'SUCCESS_DEPOSIT': "✅ Deposit successful!",
    'SUCCESS_WITHDRAW': "✅ Withdrawal successful!",
    'NO_PRODUCT': "❌ Product not found!",
    'NO_USER': "❌ User not found!",
    'SUCCESS_ADD': "✅ Successfully added!",
    'SUCCESS_REMOVE': "✅ Successfully removed!",
    'SUCCESS_UPDATE': "✅ Successfully updated!",
    'INVALID_CURRENCY': "❌ Invalid currency. Use: WL, DL, or BGL",
    'FILE_TOO_LARGE': "❌ File is too large! Maximum size is 1MB.",
    'INVALID_FILE_FORMAT': "❌ Invalid file format! Please use .txt files only.",
    'NO_ITEMS_FOUND': "❌ No items found in file!",
    'STOCK_ADDED': "✅ Stock items successfully added!",
    'PROCESSING': "⏳ Processing... Please wait..."
}

# Individual message constants (backwards compatibility)
MSG_ERROR_GENERIC = MESSAGES['ERROR_GENERIC']
MSG_NO_PERMISSION = MESSAGES['NO_PERMISSION']
MSG_COOLDOWN = MESSAGES['COOLDOWN']
MSG_INVALID_AMOUNT = MESSAGES['INVALID_AMOUNT']
MSG_INSUFFICIENT_BALANCE = MESSAGES['INSUFFICIENT_BALANCE']
MSG_INSUFFICIENT_STOCK = MESSAGES['INSUFFICIENT_STOCK']
MSG_SUCCESS_PURCHASE = MESSAGES['SUCCESS_PURCHASE']
MSG_SUCCESS_DEPOSIT = MESSAGES['SUCCESS_DEPOSIT']
MSG_SUCCESS_WITHDRAW = MESSAGES['SUCCESS_WITHDRAW']

# Permission levels
PERMISSION_ADMIN = 'ADMIN'
PERMISSION_MOD = 'MOD'
PERMISSION_USER = 'USER'

# Database related
DB_FILE = 'shop.db'
DB_BACKUP_DIR = 'backups'
MAX_TRANSACTION_HISTORY = 50

# File settings
MAX_STOCK_FILE_SIZE = 1024 * 1024  # 1MB
VALID_STOCK_FORMATS = ['txt']
ITEMS_PER_PAGE = 5

# Additional settings
MIN_PURCHASE_QUANTITY = 1
MAX_PURCHASE_QUANTITY = 100

# Log settings
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_FILE = 'bot.log'

# Product Fields
VALID_PRODUCT_FIELDS = ['name', 'price', 'description']

# Admin Settings
ADMIN_CONFIRM_TIMEOUT = 30  # seconds
ADMIN_BULK_UPDATE_CHUNK = 10  # items per progress update

# File Upload Settings
ALLOWED_FILE_TYPES = {
    'stock': ['txt'],
    'backup': ['db', 'sqlite', 'backup']
}
MAX_FILE_SIZES = {
    'stock': 1024 * 1024,  # 1MB
    'backup': 10 * 1024 * 1024  # 10MB
}

# Pagination Settings
DEFAULT_PAGE_SIZE = 5
MAX_PAGE_SIZE = 20
PAGINATION_TIMEOUT = 60  # seconds
PAGINATION_EMOJIS = {
    'previous': '⬅️',
    'next': '➡️',
    'first': '⏮️',
    'last': '⏭️'
}

# Transaction Settings
MIN_TRANSACTION_AMOUNT = 1
MAX_TRANSACTION_AMOUNT = 1000000  # 1M WLs

class Balance:
    def __init__(self, wl: int = 0, dl: int = 0, bgl: int = 0):
        self.wl = wl
        self.dl = dl
        self.bgl = bgl
        self.total_wls = self.to_wls()
    
    def format(self) -> str:
        """Format balance in human readable string"""
        parts = []
        if self.bgl > 0:
            parts.append(f"{self.bgl:,} BGL")
        if self.dl > 0:
            parts.append(f"{self.dl:,} DL")
        if self.wl > 0:
            parts.append(f"{self.wl:,} WL")
        
        if not parts:
            return "0 WL"
        return " + ".join(parts)
        
    def to_wls(self) -> int:
        """Convert balance to total WLs"""
        return self.wl + (self.dl * 100) + (self.bgl * 10000)