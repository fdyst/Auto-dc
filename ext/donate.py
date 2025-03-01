import discord
from discord.ext import commands
import logging
from datetime import datetime
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from database import get_connection
from .constants import Balance, TransactionError, CURRENCY_RATES

# Load config
with open('config.json') as config_file:
    config = json.load(config_file)

DONATION_LOG_CHANNEL_ID = int(config['id_donation_log'])
PORT = 8081

class DonateHandler(BaseHTTPRequestHandler):
    def _init_logger(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            self.logger.info(f"Received donation data: {post_data}")
            
            data = json.loads(post_data)
            growid = data.get('GrowID')
            deposit = data.get('Deposit')
            
            if not growid or not deposit:
                self.send_error_response("Invalid data")
                return
                
            # Parse deposit amounts
            wl, dl, bgl = self.parse_deposit(deposit)
            
            # Process donation
            new_balance = self.process_donation(growid, wl, dl, bgl)
            
            # Send success response
            self.send_success_response(growid, wl, dl, bgl, new_balance)
            
            # Log to Discord
            self.log_to_discord(growid, wl, dl, bgl, new_balance)
            
        except json.JSONDecodeError:
            self.send_error_response("Invalid JSON data")
        except Exception as e:
            self.logger.error(f"Error processing donation: {e}")
            self.send_error_response("Internal server error")

    def parse_deposit(self, deposit: str) -> tuple[int, int, int]:
        wl = dl = bgl = 0
        
        deposits = deposit.split(',')
        for d in deposits:
            d = d.strip()
            if 'World Lock' in d:
                wl += int(d.split()[0])
            elif 'Diamond Lock' in d:
                dl += int(d.split()[0])
            elif 'Blue Gem Lock' in d:
                bgl += int(d.split()[0])
                
        return wl, dl, bgl

    def process_donation(
        self, 
        growid: str, 
        wl: int, 
        dl: int, 
        bgl: int
    ) -> Balance:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Get current balance
            cursor.execute("""
                SELECT balance_wl, balance_dl, balance_bgl 
                FROM users 
                WHERE growid = ?
            """, (growid,))
            
            result = cursor.fetchone()
            if not result:
                # Create new user
                cursor.execute("""
                    INSERT INTO users (growid, balance_wl, balance_dl, balance_bgl)
                    VALUES (?, 0, 0, 0)
                """, (growid,))
                current = Balance(0, 0, 0)
            else:
                current = Balance(*result)
            
            # Calculate new balance
            new_balance = Balance(
                current.wl + wl,
                current.dl + dl,
                current.bgl + bgl
            )
            
            # Update balance
            cursor.execute("""
                UPDATE users 
                SET balance_wl = ?,
                    balance_dl = ?,
                    balance_bgl = ?
                WHERE growid = ?
            """, (new_balance.wl, new_balance.dl, new_balance.bgl, growid))
            
            # Log transaction
            total_wls = (
                wl + 
                (dl * CURRENCY_RATES['DL']) + 
                (bgl * CURRENCY_RATES['BGL'])
            )
            
            cursor.execute("""
                INSERT INTO transaction_log 
                (growid, amount, type, details, old_balance, new_balance)
                VALUES (?, ?, 'DONATION', ?, ?, ?)
            """, (
                growid,
                total_wls,
                f"Donation: {wl} WL, {dl} DL, {bgl} BGL",
                current.format(),
                new_balance.format()
            ))
            
            conn.commit()
            return new_balance
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
            
        finally:
            if conn:
                conn.close()

    def send_success_response(
        self, 
        growid: str, 
        wl: int, 
        dl: int, 
        bgl: int, 
        new_balance: Balance
    ):
        self.send_response(200)
        self.end_headers()
        response = (
            f"\u2705 Donation received!\n"
            f"GrowID: {growid}\n"
            f"Amount: {wl} WL, {dl} DL, {bgl} BGL\n"
            f"New Balance:\n{new_balance.format()}"
        )
        self.wfile.write(response.encode())

    def send_error_response(self, message: str):
        self.send_response(400)
        self.end_headers()
        self.wfile.write(f"\u274c Error: {message}".encode())

    async def log_to_discord(
        self, 
        growid: str, 
        wl: int, 
        dl: int, 
        bgl: int, 
        new_balance: Balance
    ):
        channel = self.bot.get_channel(DONATION_LOG_CHANNEL_ID)
        if not channel:
            self.logger.error("Donation log channel not found")
            return
            
        embed = discord.Embed(
            title="\ud83d\udc8e New Donation Received",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="GrowID",
            value=growid,
            inline=True
        )
        
        embed.add_field(
            name="Amount",
            value=(
                f"\u2022 {wl:,} WL\n"
                f"\u2022 {dl:,} DL\n"
                f"\u2022 {bgl:,} BGL"
            ),
            inline=True
        )
        
        embed.add_field(
            name="New Balance",
            value=new_balance.format(),
            inline=False
        )
        
        await channel.send(embed=embed)

class DonateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._init_logger()
        self.server = None
        DonateHandler.bot = bot
        
    def _init_logger(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.server:
            try:
                self.server = HTTPServer(('0.0.0.0', PORT), DonateHandler)
                self.logger.info(f'Starting donation server on port {PORT}')
                self.bot.loop.run_in_executor(None, self.server.serve_forever)
            except Exception as e:
                self.logger.error(f"Failed to start donation server: {e}")

    def cog_unload(self):
        if self.server:
            self.server.shutdown()
            self.server = None

async def setup(bot):
    await bot.add_cog(DonateCog(bot))