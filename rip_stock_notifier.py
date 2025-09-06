#!/usr/bin/env python3
"""
Rip.fun Stock Notifier
======================

This script monitors the Rip.fun store page for available Pokémon card packs
and sends Discord notifications when new stock appears.

How it works
------------

The script scrapes the Rip.fun store page every 4 minutes to check for
available pack inventory. It parses the SvelteKit JavaScript data to find
packs with token_id (actual sellable inventory) and filters out promotional
"Featured Sets" that are just marketplace links.

When new packs appear or significant stock increases occur, it sends
notifications to Discord with @here mentions.

Configuration
-------------

Set the DISCORD_WEBHOOK_URL environment variable or edit the default below:
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"

Running
-------

The script runs continuously, checking every 4 minutes. Use Ctrl+C to stop.

For testing: python3 rip_stock_notifier.py --test
"""

import json
import os
import time
import logging
import re
from typing import Dict
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Discord webhook URL for stock notifications
# Set via environment variable: export DISCORD_WEBHOOK_URL="your_webhook_url"
DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")

# How often to check for new stock (in seconds). 240 seconds = 4 minutes.
POLL_INTERVAL_SECONDS: int = 240

# Enable Discord notifications
ENABLE_DISCORD_NOTIFICATIONS: bool = True

# Enable email notifications (disabled by default)
ENABLE_EMAIL_NOTIFICATIONS: bool = False

# Email settings (only needed if email notifications are enabled)
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 465,
    "username": "your_email@example.com",
    "password": "app_specific_password",
    "from_address": "your_email@example.com",
    "to_address": "recipient@example.com",
}

# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------

def fetch_available_packs_from_store() -> Dict[str, int]:
    """Scrape the store page to find available packs by set.

    Returns a dictionary mapping set names to pack counts.
    Only includes actual inventory (packs with token_id), not featured sets.
    """
    url = "https://rip.fun/store"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        html = response.text
        logging.debug("Fetched store page (%d characters)", len(html))
        
        # Look for actual inventory packs (not featured sets)
        # Pattern: Look for objects with token_id AND name together (real inventory)
        # This avoids the featured sets which don't have token_id
        inventory_pattern = r'token_id:"(\d+)"[^}]*?name:"([^"]+Booster Pack[^"]*)"'
        inventory_matches = re.findall(inventory_pattern, html, re.DOTALL)
        
        # Count packs by set name
        pack_counts = {}
        for token_id, pack_name in inventory_matches:
            set_name = pack_name.replace(" Booster Pack", "").strip()
            pack_counts[set_name] = pack_counts.get(set_name, 0) + 1
        
        logging.info("Found packs in store: %s", pack_counts)
        return pack_counts
        
    except requests.RequestException as exc:
        logging.error("Failed to fetch store page: %s", exc)
        return {}
    except Exception as exc:
        logging.error("Error parsing store data: %s", exc)
        return {}


def send_discord_notification(message: str) -> None:
    """Send a notification to Discord via webhook."""
    if not ENABLE_DISCORD_NOTIFICATIONS:
        return
    
    if not DISCORD_WEBHOOK_URL:
        logging.warning("Discord notifications enabled but no webhook URL configured")
        return
    
    try:
        payload = {"content": message}
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        logging.info("Sent Discord notification")
    except Exception as exc:
        logging.error("Failed to send Discord notification: %s", exc)


def send_email(subject: str, body: str) -> None:
    """Send an email notification."""
    if not ENABLE_EMAIL_NOTIFICATIONS:
        return
        
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = EMAIL_CONFIG["from_address"]
    msg["To"] = EMAIL_CONFIG["to_address"]
    msg["Subject"] = subject
    msg.set_content(body)
    
    try:
        with smtplib.SMTP_SSL(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as smtp:
            smtp.login(EMAIL_CONFIG["username"], EMAIL_CONFIG["password"])
            smtp.send_message(msg)
        logging.info("Sent email notification to %s", EMAIL_CONFIG["to_address"])
    except Exception as exc:
        logging.error("Failed to send email notification: %s", exc)


# Global variable to track previously seen stock to avoid spam
_previous_stock = {}

def check_and_notify() -> None:
    """Check the store for available packs and send notifications for changes."""
    global _previous_stock
    
    # Get current pack availability from store page
    available_packs = fetch_available_packs_from_store()
    
    if not available_packs:
        logging.info("No packs found in store (or failed to fetch)")
        return
    
    notifications_sent = 0
    total_packs = 0
    
    # Check each available set and send notifications only for changes
    for set_name, count in available_packs.items():
        total_packs += count
        previous_count = _previous_stock.get(set_name, 0)
        
        if previous_count == 0:
            # New set in stock - send notification
            message = f"@here {set_name} has {count} pack(s) available on Rip.fun!"
            logging.info("NEW STOCK: %s", message)
            send_email(subject=f"Rip.fun: {set_name} in stock", body=message)
            send_discord_notification(message)
            notifications_sent += 1
        elif count > previous_count + 5:
            # Significant increase in stock (more than 5 packs) - send notification
            message = f"@here {set_name} restocked! Now {count} pack(s) available (was {previous_count})"
            logging.info("RESTOCK: %s", message)
            send_email(subject=f"Rip.fun: {set_name} restocked", body=message)
            send_discord_notification(message)
            notifications_sent += 1
        else:
            # Same stock level - no notification, just log
            logging.debug("%s still has %d packs (no change)", set_name, count)
    
    # Update tracking
    _previous_stock = available_packs.copy()
    
    # Log summary
    set_count = len(available_packs)
    logging.info("Found %d sets with %d total packs in stock (%d notifications sent)", 
                set_count, total_packs, notifications_sent)



def main() -> None:
    """Main entry point - runs the stock monitoring loop."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    logging.info("Starting Rip.fun stock notifier")
    logging.info("Checking store every %d seconds (%d minutes)", POLL_INTERVAL_SECONDS, POLL_INTERVAL_SECONDS // 60)
    
    if ENABLE_EMAIL_NOTIFICATIONS:
        logging.info("Email notifications enabled: %s", EMAIL_CONFIG["to_address"])
    else:
        logging.info("Email notifications disabled")
        
    if ENABLE_DISCORD_NOTIFICATIONS:
        logging.info("Discord notifications enabled")
    else:
        logging.info("Discord notifications disabled")

    try:
        while True:
            check_and_notify()
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logging.info("Notifier stopped by user")


if __name__ == "__main__":
    main()