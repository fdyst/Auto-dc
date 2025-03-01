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

# Transaction type constants
TRANSACTION_PURCHASE = 'PURCHASE'
TRANSACTION_REFUND = 'REFUND'
TRANSACTION_ADMIN = 'ADMIN'
TRANSACTION_DEPOSIT = 'DEPOSIT'
TRANSACTION_WITHDRAW = 'WITHDRAW'

# Time constants
UPDATE_INTERVAL = 55  # seconds
COOLDOWN_SECONDS = 3

# Embed colors (in decimal)
COLOR_SUCCESS = 0x00ff00  # Green
COLOR_ERROR = 0xff0000    # Red
COLOR_INFO = 0x0000ff     # Blue
COLOR_WARNING = 0xffff00  # Yellow

# Bot response messages
MSG_ERROR_GENERIC = "\u274c An error occurred. Please try again later."
MSG_NO_PERMISSION = "\u274c You don't have permission to use this command."
MSG_COOLDOWN = "\u26a0\ufe0f Please wait {seconds} seconds before using this command again."
MSG_INVALID_AMOUNT = "\u274c Please enter a valid amount."
MSG_INSUFFICIENT_BALANCE = "\u274c Insufficient balance."
MSG_INSUFFICIENT_STOCK = "\u274c Insufficient stock available."
MSG_SUCCESS_PURCHASE = "\u2705 Purchase successful! Check your DMs for the items."
MSG_SUCCESS_DEPOSIT = "\u2705 Deposit successful!"
MSG_SUCCESS_WITHDRAW = "\u2705 Withdrawal successful!"

# Permission levels
PERMISSION_ADMIN = 'ADMIN'
PERMISSION_MOD = 'MOD'
PERMISSION_USER = 'USER'

# Database related
DB_FILE = 'shop.db'
DB_BACKUP_DIR = 'backups'
MAX_TRANSACTION_HISTORY = 50