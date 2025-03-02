import sqlite3
import logging
from datetime import datetime

def get_connection():
    """Get SQLite database connection"""
    try:
        conn = sqlite3.connect('shop.db')
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logging.error(f"Database connection error: {e}")
        raise

def setup_database():
    """Initialize database tables"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                growid TEXT UNIQUE NOT NULL,
                balance_wl INTEGER DEFAULT 0,
                balance_dl INTEGER DEFAULT 0,
                balance_bgl INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create trigger for users updated_at
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_users_timestamp 
            AFTER UPDATE ON users
            BEGIN
                UPDATE users SET updated_at = CURRENT_TIMESTAMP
                WHERE user_id = NEW.user_id;
            END;
        """)

        # Create user_growid table dengan schema baru
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_growid (
                discord_id TEXT PRIMARY KEY,
                growid TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (growid) REFERENCES users(growid) ON DELETE CASCADE
            )
        """)

        # Create products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                description TEXT,
                stock INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create trigger for products updated_at
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_products_timestamp 
            AFTER UPDATE ON products
            BEGIN
                UPDATE products SET updated_at = CURRENT_TIMESTAMP
                WHERE code = NEW.code;
            END;
        """)

        # Create stock table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL UNIQUE,
                status TEXT DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE', 'SOLD', 'DELETED')),
                product_code TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                added_by TEXT,
                buyer_id TEXT,
                seller_id TEXT,
                line_number INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_code) REFERENCES products(code) ON DELETE SET NULL
            )
        """)

        # Create trigger for stock updated_at
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_stock_timestamp 
            AFTER UPDATE ON stock
            BEGIN
                UPDATE stock SET updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)

        # Create transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                growid TEXT NOT NULL,
                type TEXT NOT NULL,
                details TEXT,
                old_balance TEXT,
                new_balance TEXT,
                items_count INTEGER DEFAULT 0,
                total_price INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (growid) REFERENCES users(growid) ON DELETE CASCADE
            )
        """)

        # Create world_info table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS world_info (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                world TEXT NOT NULL,
                owner TEXT NOT NULL,
                bot TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create trigger for world_info updated_at
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_world_info_timestamp 
            AFTER UPDATE ON world_info
            BEGIN
                UPDATE world_info SET updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)

        # Insert default world info if not exists
        cursor.execute("""
            INSERT OR IGNORE INTO world_info (id, world, owner, bot)
            VALUES (1, 'YOURWORLD', 'OWNER', 'BOT')
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_growid ON users(growid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_product_code ON stock(product_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_status ON stock(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_content ON stock(content)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_growid ON transactions(growid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_growid_growid ON user_growid(growid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_growid_discord ON user_growid(discord_id)")

        conn.commit()
        logging.info("Database setup completed successfully")

    except sqlite3.Error as e:
        logging.error(f"Database setup error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def migrate_database():
    """Migrate existing database to new schema"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if old table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='user_growid' 
            AND sql LIKE '%user_id INTEGER%'
        """)

        if cursor.fetchone():
            # Backup old table
            cursor.execute("ALTER TABLE user_growid RENAME TO user_growid_old")

            # Create new table with correct schema
            cursor.execute("""
                CREATE TABLE user_growid (
                    discord_id TEXT PRIMARY KEY,
                    growid TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (growid) REFERENCES users(growid) ON DELETE CASCADE
                )
            """)

            # Copy data with conversion
            cursor.execute("""
                INSERT INTO user_growid (discord_id, growid, created_at)
                SELECT CAST(user_id as TEXT), growid, created_at 
                FROM user_growid_old
            """)

            # Create new index
            cursor.execute("CREATE INDEX idx_user_growid_discord ON user_growid(discord_id)")

            # Drop old table
            cursor.execute("DROP TABLE user_growid_old")

            conn.commit()
            logging.info("Database migration completed successfully")
        else:
            logging.info("No migration needed - database schema is up to date")

    except sqlite3.Error as e:
        logging.error(f"Database migration error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    setup_database()
    migrate_database()
    logging.info("Database initialization complete")