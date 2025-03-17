import requests
import time
from bs4 import BeautifulSoup
import logging
import os
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("rcb_ticket_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
URL = "https://shop.royalchallengers.com/ticket"
ALERT_MESSAGE = "🎉 RCB TICKETS ARE NOW AVAILABLE! 🎉 Go to: https://shop.royalchallengers.com/ticket"
EXPECTED_COMING_SOON_COUNT = 7  # Expected number of "COMING SOON" elements when no tickets are available

# Get secrets from environment variables
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK")
if not SLACK_WEBHOOK:
    logger.error("SLACK_WEBHOOK environment variable is not set")
    raise ValueError("SLACK_WEBHOOK environment variable must be set")

PAGERDUTY_ROUTING_KEY = os.environ.get("PAGERDUTY_ROUTING_KEY")
if not PAGERDUTY_ROUTING_KEY:
    logger.error("PAGERDUTY_ROUTING_KEY environment variable is not set")
    raise ValueError("PAGERDUTY_ROUTING_KEY environment variable must be set")

def send_pagerduty_event():
    """
    Send an alert to PagerDuty using the Events API
    """
    url = "https://events.pagerduty.com/v2/enqueue"
    
    payload = {
        "routing_key": PAGERDUTY_ROUTING_KEY,
        "event_action": "trigger",
        "payload": {
            "summary": "RCB Tickets now available: shop.royalchallengers.com/ticket",
            "source": "Python Automation",
            "severity": "error"
        }
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"Success! Alert sent to PagerDuty. Status code: {response.status_code}")
        logger.info(f"Response: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending alert to PagerDuty: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response: {e.response.text}")
        return False

def send_slack_message(webhook_url, message):
    """
    Send a message to Slack using a webhook URL.
    
    Args:
        webhook_url (str): The Slack webhook URL
        message (str): The message to send
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    # Prepare the payload
    payload = {
        "text": message
    }
    
    # Convert the payload to JSON
    payload_json = json.dumps(payload)
    
    # Set the headers
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        # Send the POST request
        response = requests.post(webhook_url, data=payload_json, headers=headers)
        
        # Check if the request was successful
        if response.status_code == 200 and response.text == "ok":
            logger.info("Slack message sent successfully!")
            return True
        else:
            logger.error(f"Failed to send Slack message. Status code: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Unexpected error sending Slack message: {str(e)}")
        return False

def setup_selenium():
    """Set up and return a headless Chrome browser instance."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        logger.error(f"Error setting up Selenium: {e}")
        raise

def check_ticket_availability():
    """Check ticket availability using Selenium to load dynamic content."""
    driver = None
    try:
        logger.info("Starting Selenium browser to check ticket availability")
        driver = setup_selenium()
        
        # Load the page
        driver.get(URL)
        
        # Wait for the page to fully load
        time.sleep(30)  # Allow JavaScript to render content
        
        # Take a screenshot for debugging
        driver.save_screenshot("latest_screenshot.png")
        logger.info("Saved screenshot for inspection")
        
        # Get the page source after JavaScript has executed
        page_source = driver.page_source
        
        # Save the dynamically generated HTML for inspection
        with open("latest_dynamic_page.html", "w", encoding="utf-8") as f:
            f.write(page_source)
        logger.info("Saved dynamic page HTML for inspection")
        
        # First check for "BUY TICKETS" or "GET TICKETS" directly in the page
        buy_tickets_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'BUY TICKETS') or contains(text(), 'Buy Tickets') or contains(text(), 'Get Tickets')]")
        
        # Look for "COMING SOON" elements
        coming_soon_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'COMING SOON') or contains(text(), 'Coming Soon')]")
        
        logger.info(f"Found {len(buy_tickets_elements)} 'BUY TICKETS' elements on the page")
        logger.info(f"Found {len(coming_soon_elements)} 'COMING SOON' elements on the page")
        
        # IMPROVED LOGIC: Alert if we find any "BUY TICKETS" element
        if len(buy_tickets_elements) > 0:
            logger.info("TICKETS ARE AVAILABLE NOW! Found 'BUY TICKETS' elements.")
            return True
            
        # # IMPROVED LOGIC: Alert if the number of "COMING SOON" elements is less than expected
        # if len(coming_soon_elements) < EXPECTED_COMING_SOON_COUNT:
        #     logger.info(f"POTENTIAL TICKET AVAILABILITY! Found only {len(coming_soon_elements)} 'COMING SOON' elements (expected {EXPECTED_COMING_SOON_COUNT}).")
        #     return True
            
        # Additional check for button elements
        buttons = driver.find_elements(By.TAG_NAME, "button")
        logger.info(f"Found {len(buttons)} button elements")
        for i, button in enumerate(buttons[:5]):  # Log first 5 buttons only
            button_text = button.text.upper()
            logger.info(f"Button {i+1}: '{button_text}'")
            if ("BUY" in button_text or "GET" in button_text) and "TICKET" in button_text:
                logger.info("TICKETS ARE AVAILABLE NOW! Found button with ticket purchase text.")
                return True
        
        # No ticket availability detected
        logger.info("Tickets not available yet - all checks indicate tickets are not on sale")
        return False
        
    except Exception as e:
        logger.error(f"Error during selenium check: {str(e)}")
        return False
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Selenium browser closed")
            except:
                pass

def main():
    """Main function to check ticket availability once (for GitHub Actions)."""
    logger.info("Starting RCB ticket availability monitor")
    
    tickets_available = check_ticket_availability()
    
    if tickets_available:
        logger.info("Tickets are now available! Sending alerts...")
        
        # Send both PagerDuty and Slack alerts for redundancy
        pagerduty_sent = send_pagerduty_event()
        slack_sent = send_slack_message(SLACK_WEBHOOK, ALERT_MESSAGE)
        
        # Consider alert sent if at least one notification method worked
        alert_sent = pagerduty_sent or slack_sent
        
        if alert_sent:
            logger.info("At least one alert sent successfully!")
            return 0
        else:
            logger.error("Failed to send any alerts")
            return 1
    else:
        logger.info("Tickets not available yet.")
        return 0

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        check_ticket_availability()
        logger.info("Debug analysis complete. Check the log, latest_screenshot.png, and latest_dynamic_page.html for details.")
    else:
        exit_code = main()
        exit(exit_code)
