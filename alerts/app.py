"""
Alert Manager - Telegram & Email notifications
"""
import logging
import smtplib
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("'requests' not installed. Telegram alerts disabled.")


class AlertManager:
    """
    Sends trade notifications via Telegram and/or Email.
    All sends are non-blocking (run in background thread).
    """

    def __init__(self, telegram_config: dict, email_config: dict):
        self.tg = telegram_config
        self.em = email_config

    # ─── PUBLIC METHODS ────────────────────────────────────────────

    def send_trade_opened(self, trade: dict):
        msg = self._format_trade_opened(trade)
        self._dispatch("🟢 Trade Opened", msg,
                       send_tg=self.tg.get("send_on_open"),
                       send_email=self.em.get("send_on_open"))

    def send_trade_closed(self, trade: dict):
        emoji = "✅" if trade.get("profit", 0) >= 0 else "❌"
        msg = self._format_trade_closed(trade)
        self._dispatch(f"{emoji} Trade Closed", msg,
                       send_tg=self.tg.get("send_on_close"),
                       send_email=self.em.get("send_on_close"))

    def send_error(self, error: str):
        msg = f"⚠️ *Bot Error*\n`{error}`\n\n_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
        self._dispatch("⚠️ Bot Error", msg,
                       send_tg=self.tg.get("send_on_error"),
                       send_email=self.em.get("send_on_error"))

    def send_daily_summary(self, stats: dict):
        msg = self._format_daily_summary(stats)
        self._dispatch("📊 Daily Summary", msg,
                       send_tg=self.tg.get("send_daily_summary"),
                       send_email=self.em.get("send_daily_summary"))

    def send_custom(self, title: str, message: str):
        self._dispatch(title, message, send_tg=True, send_email=False)

    def test_telegram(self) -> tuple:
        """Send a test message. Returns (success, message)."""
        if not self.tg.get("enabled"):
            return False, "Telegram is disabled in config"
        ok, msg = self._send_telegram("🤖 *MT5 Scalper Bot*\nTelegram alerts connected successfully!")
        return ok, msg

    def test_email(self) -> tuple:
        """Send a test email. Returns (success, message)."""
        if not self.em.get("enabled"):
            return False, "Email is disabled in config"
        ok, msg = self._send_email("MT5 Scalper - Test Email",
                                   "<p>Email alerts connected successfully!</p>")
        return ok, msg

    # ─── FORMATTING ────────────────────────────────────────────────

    def _format_trade_opened(self, t: dict) -> str:
        direction = "📈 BUY" if t.get("type") == "BUY" else "📉 SELL"
        return (
            f"*{direction}* — {t.get('symbol', '')}\n"
            f"Entry: `{t.get('price', 0):.5f}`\n"
            f"SL: `{t.get('sl', 0):.5f}`\n"
            f"TP: `{t.get('tp', 0):.5f}`\n"
            f"Volume: `{t.get('volume', 0):.2f} lots`\n"
            f"Ticket: `#{t.get('ticket', 0)}`\n"
            f"_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
        )

    def _format_trade_closed(self, t: dict) -> str:
        profit = t.get("profit", 0)
        pips = t.get("pips", 0)
        sign = "+" if profit >= 0 else ""
        return (
            f"*{'BUY' if t.get('type') == 'BUY' else 'SELL'}* — {t.get('symbol', '')}\n"
            f"Entry: `{t.get('open_price', 0):.5f}`\n"
            f"Exit:  `{t.get('close_price', 0):.5f}`\n"
            f"Pips:  `{sign}{pips:.1f}`\n"
            f"P&L:   `{sign}{profit:.2f} {t.get('currency', 'USD')}`\n"
            f"Ticket: `#{t.get('ticket', 0)}`\n"
            f"_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
        )

    def _format_daily_summary(self, s: dict) -> str:
        pnl = s.get("daily_pnl", 0)
        sign = "+" if pnl >= 0 else ""
        return (
            f"📊 *Daily Summary — {datetime.now().strftime('%Y-%m-%d')}*\n\n"
            f"Trades:      `{s.get('total_trades', 0)}`\n"
            f"Wins:        `{s.get('wins', 0)}`\n"
            f"Losses:      `{s.get('losses', 0)}`\n"
            f"Win Rate:    `{s.get('win_rate', 0):.1f}%`\n"
            f"Daily P&L:   `{sign}{pnl:.2f} {s.get('currency', 'USD')}`\n"
            f"Balance:     `{s.get('balance', 0):.2f}`\n"
            f"Equity:      `{s.get('equity', 0):.2f}`\n"
        )

    # ─── DISPATCH ──────────────────────────────────────────────────

    def _dispatch(self, title: str, message: str,
                  send_tg: bool = False, send_email: bool = False):
        """Fire-and-forget alerts in background threads."""
        if self.tg.get("enabled") and send_tg:
            threading.Thread(
                target=self._send_telegram,
                args=(message,),
                daemon=True
            ).start()

        if self.em.get("enabled") and send_email:
            html = self._markdown_to_html(message)
            threading.Thread(
                target=self._send_email,
                args=(title, html),
                daemon=True
            ).start()

    # ─── TELEGRAM ──────────────────────────────────────────────────

    def _send_telegram(self, message: str) -> tuple:
        if not REQUESTS_AVAILABLE:
            return False, "requests library not installed"

        token = self.tg.get("bot_token", "")
        chat_id = self.tg.get("chat_id", "")

        if not token or not chat_id or token == "YOUR_BOT_TOKEN":
            return False, "Telegram not configured"

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram alert sent")
                return True, "Sent"
            else:
                err = f"Telegram error {resp.status_code}: {resp.text}"
                logger.error(err)
                return False, err
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False, str(e)

    # ─── EMAIL ─────────────────────────────────────────────────────

    def _send_email(self, subject: str, html_body: str) -> tuple:
        cfg = self.em
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[MT5 Scalper] {subject}"
            msg["From"] = cfg.get("sender_email", "")
            msg["To"] = cfg.get("recipient_email", "")
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(cfg.get("smtp_server", "smtp.gmail.com"),
                              cfg.get("smtp_port", 587)) as server:
                server.ehlo()
                server.starttls()
                server.login(cfg.get("sender_email", ""),
                             cfg.get("sender_password", ""))
                server.sendmail(cfg["sender_email"],
                                cfg["recipient_email"],
                                msg.as_string())

            logger.info(f"Email sent: {subject}")
            return True, "Sent"

        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False, str(e)

    # ─── HELPER ────────────────────────────────────────────────────

    def _markdown_to_html(self, text: str) -> str:
        """Convert simple Telegram markdown to HTML for email."""
        import re
        text = re.sub(r"\*(.+?)\*", r"<b>\1</b>", text)
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        text = re.sub(r"_(.+?)_", r"<i>\1</i>", text)
        text = text.replace("\n", "<br>")
        return f"""
        <html><body style="font-family:monospace;background:#1a1a2e;color:#eee;padding:20px;">
        <div style="max-width:400px;background:#16213e;padding:20px;border-radius:10px;
                    border-left:4px solid #00d4ff;">
        {text}
        </div></body></html>
        """