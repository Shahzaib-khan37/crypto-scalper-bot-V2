import requests
import threading
import json
import db

def log_trade_to_sheets_async(trade):
    """
    Spawns a background thread to send the trade details to the Google Sheets Apps Script Webhook.
    Ensures network latency never blocks the bot's execution thread.
    """
    thread = threading.Thread(target=_send_webhook_request, args=(trade,))
    thread.daemon = True
    thread.start()

def _send_webhook_request(trade):
    try:
        # Load latest settings to get the webhook URL
        state = db.get()
        webhook_url = state.get("googleSheetsWebhookUrl", "")
        
        if not webhook_url or not webhook_url.strip():
            print("[Google Sheets] Webhook URL not configured. Skipped remote logging.")
            return

        payload = {
            "timestamp": trade.get("timestamp"),
            "accountName": trade.get("accountName"),
            "mode": trade.get("mode"),
            "coin": trade.get("coin"),
            "action": trade.get("action"),
            "strategy": trade.get("strategy"),
            "price": trade.get("price"),
            "size": trade.get("size"),
            "total": trade.get("total"),
            "pnl_pct": trade.get("pnl_pct", 0.0),
            "pnl_usd": trade.get("pnl_usd", 0.0),
            "reason": trade.get("reason", "N/A")
        }
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print(f"[Google Sheets] Trade logged successfully for {trade.get('coin')}")
        else:
            print(f"[Google Sheets] Webhook responded with status: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[Google Sheets] Failed to log trade via Webhook: {e}")
