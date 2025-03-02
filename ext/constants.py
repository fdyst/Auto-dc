# File status constants
STATUS_AVAILABLE = "AVAILABLE"
STATUS_SOLD = "SOLD"
STATUS_PENDING = "PENDING"

# Transaction types
TRANSACTION_PURCHASE = "PURCHASE"
TRANSACTION_ADMIN_ADD = "ADMIN_ADD"
TRANSACTION_ADMIN_REMOVE = "ADMIN_REMOVE" 
TRANSACTION_ADMIN_RESET = "ADMIN_RESET"

# Currency rates (in WLs)
CURRENCY_RATES = {
    "WL": 1,
    "DL": 100,
    "BGL": 10000
}

# Time intervals
COOLDOWN_SECONDS = 3
UPDATE_INTERVAL = 30

# Stock file settings
MAX_STOCK_FILE_SIZE = 1024 * 1024  # 1MB
VALID_STOCK_FORMATS = ['txt']

# Admin settings
ADMIN_ROLES = []  # Add admin role IDs here if needed

# Item settings
MAX_PURCHASE_QUANTITY = 100
MIN_PURCHASE_QUANTITY = 1

# File path constants
CONFIG_FILE = "config.json"
DATABASE_FILE = "database.db"

# Pagination settings
ITEMS_PER_PAGE = 5
PAGE_TIMEOUT = 60  # seconds

# Log settings
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

class Balance:
    """Class to handle balance calculations and formatting"""
    def __init__(self, wl: int = 0, dl: int = 0, bgl: int = 0):
        self.wl = wl
        self.dl = dl
        self.bgl = bgl
        self._normalize()

    def _normalize(self):
        """Convert all to highest possible currency"""
        # Convert all to WLs first
        total_wls = (
            self.wl +
            (self.dl * CURRENCY_RATES['DL']) +
            (self.bgl * CURRENCY_RATES['BGL'])
        )

        # Convert back to individual currencies
        self.bgl = total_wls // CURRENCY_RATES['BGL']
        remaining = total_wls % CURRENCY_RATES['BGL']
        
        self.dl = remaining // CURRENCY_RATES['DL']
        self.wl = remaining % CURRENCY_RATES['DL']

    @property
    def total_wls(self) -> int:
        """Get total balance in WLs"""
        return (
            self.wl +
            (self.dl * CURRENCY_RATES['DL']) +
            (self.bgl * CURRENCY_RATES['BGL'])
        )

    def add(self, other: 'Balance') -> 'Balance':
        """Add two balances"""
        return Balance(
            wl=self.wl + other.wl,
            dl=self.dl + other.dl,
            bgl=self.bgl + other.bgl
        )

    def subtract(self, other: 'Balance') -> 'Balance':
        """Subtract balance"""
        new_total = self.total_wls - other.total_wls
        if new_total < 0:
            raise BalanceError("Insufficient balance")
            
        result = Balance()
        result.wl = new_total
        result._normalize()
        return result

    def format(self) -> str:
        """Format balance for display"""
        parts = []
        if self.bgl > 0:
            parts.append(f"{self.bgl:,} BGL")
        if self.dl > 0:
            parts.append(f"{self.dl:,} DL")
        if self.wl > 0 or not parts:  # Show WLs if there are some or if balance is 0
            parts.append(f"{self.wl:,} WL")
        return " ".join(parts)

    @classmethod
    def from_dict(cls, data: dict) -> 'Balance':
        """Create Balance instance from dictionary"""
        return cls(
            wl=data.get('wl', 0),
            dl=data.get('dl', 0),
            bgl=data.get('bgl', 0)
        )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'wl': self.wl,
            'dl': self.dl,
            'bgl': self.bgl
        }

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"Balance(wl={self.wl}, dl={self.dl}, bgl={self.bgl})"

# Custom Exceptions
class TransactionError(Exception):
    """Custom exception for transaction errors"""
    pass

class BalanceError(Exception):
    """Custom exception for balance errors"""
    pass

class ProductError(Exception):
    """Custom exception for product errors"""
    pass

# Message templates
MESSAGES = {
    'NO_PERMISSION': '❌ You don\'t have permission to use this command!',
    'INVALID_AMOUNT': '❌ Amount must be positive!',
    'INSUFFICIENT_BALANCE': '❌ Insufficient balance!',
    'INVALID_CURRENCY': '❌ Invalid currency! Use: WL, DL, or BGL',
    'PRODUCT_NOT_FOUND': '❌ Product not found!',
    'OUT_OF_STOCK': '❌ Product is out of stock!',
    'INVALID_QUANTITY': '❌ Invalid quantity!',
    'USER_NOT_FOUND': '❌ User not found!',
    'OPERATION_CANCELLED': '❌ Operation cancelled!',
    'TIMEOUT': '❌ Operation timed out!',
    'SUCCESS': '✅ Operation successful!',
    'ERROR': '❌ An error occurred!'
}

# Format functions
def format_currency(amount: int, currency: str = 'WL') -> str:
    """Format currency amount with commas"""
    return f"{amount:,} {currency}"

def format_timestamp() -> str:
    """Get current timestamp in UTC"""
    from datetime import datetime
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')