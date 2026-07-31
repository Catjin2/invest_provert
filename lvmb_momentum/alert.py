import os
import requests
import threading
from dotenv import load_dotenv

class AntiGravityAlert:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # Thread-safe Singleton pattern
        with cls._lock:
            if not cls._instance:
                cls._instance = super(AntiGravityAlert, cls).__new__(cls, *args, **kwargs)
                cls._instance._init_alert()
            return cls._instance

    def _init_alert(self):
        load_dotenv()
        self.telegram_token = os.getenv("TELEGRAM_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    def _send_telegram(self, message):
        if not self.telegram_token or not self.telegram_chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=8)
            if response.status_code != 200:
                print(f"[Alert] Telegram API returned non-200 status: {response.text}")
        except Exception as e:
            print(f"[Alert] Failed to send Telegram notification: {e}")

    def _send_slack(self, message):
        if not self.slack_webhook_url:
            return
        try:
            payload = {"text": message}
            response = requests.post(self.slack_webhook_url, json=payload, timeout=8)
            if response.status_code != 200:
                print(f"[Alert] Slack Webhook returned non-200 status: {response.text}")
        except Exception as e:
            print(f"[Alert] Failed to send Slack notification: {e}")

    def _dispatch(self, message, level):
        formatted_msg = f"🔔 *[Anti-Gravity Alert]*\n*Level*: `{level}`\n\n{message}"
        
        # 1. Try Telegram first if credentials exist
        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(formatted_msg)
        # 2. Fallback to Slack Webhook
        elif self.slack_webhook_url:
            self._send_slack(formatted_msg)
        # 3. Final Fallback to standard console logger
        else:
            print(f"\n[ALERT FALLBACK] [{level}] {message}\n")

    def send_alert(self, message, level="INFO"):
        """Sends notification asynchronously in a background thread to prevent latency blocks."""
        t = threading.Thread(target=self._dispatch, args=(message, level), daemon=True)
        t.start()

# Global convenience instance
alert_system = AntiGravityAlert()

if __name__ == "__main__":
    print("Testing Alert System...")
    alert = AntiGravityAlert()
    
    # Try sending fallback alert
    alert.send_alert("This is a test INFO alert. (Check if Telegram/Slack is configured)", "INFO")
    alert.send_alert("This is a test WARNING alert. (Telemetry Fallback Simulation)", "WARNING")
    alert.send_alert("This is a test CRITICAL alert. (Portfolio Overdraft Simulation)", "CRITICAL")
    
    import time
    time.sleep(2)  # Wait for threads to finish dispatching
    print("Test finished.")
