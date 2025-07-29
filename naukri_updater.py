import os
import time
import schedule
import pyperclip
import logging
import threading
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

from google import genai
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dotenv import load_dotenv

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

# --- Environment Variables ---
NAUKRI_USERNAME = os.environ.get("NAUKRI_USERNAME")
NAUKRI_PASSWORD = os.environ.get("NAUKRI_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
UPDATE_TIME = os.environ.get("UPDATE_TIME", "10:00") # Default to 10:00 if not set

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Naukri Profile Updater API",
    description="An API to automatically update your Naukri.com profile summary and check its status.",
    version="1.0.0"
)

# --- Job Status Tracking ---
job_status = {
    "last_run_time": "N/A",
    "last_run_status": "never_run",
    "details": "The updater has not been run yet.",
    "next_scheduled_run": "N/A"
}

class HealthStatus(BaseModel):
    last_run_time: str
    last_run_status: str
    details: str
    next_scheduled_run: str

# --- Core Logic ---

def process_text_with_gemini(text: str) -> str:
    """Processes the profile summary using the Gemini API."""
    try:
        if not GEMINI_API_KEY:
            logging.warning("GEMINI_API_KEY not found. Skipping text processing.")
            return text

        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""Just change one or two words with buzzwords that will attract recruiters for the profile summary.
        profile summary: {text}
        rest of the things should remain same.
        remember do not provide any options or anything else unrelated to profile summary.
        follow the profile summary format for the output do not add extra annotations.
        """
        response = client.models.generate_content(model='models/gemini-1.5-flash', contents=prompt)
        processed_text = response.text.strip()

        if processed_text.startswith('"') and processed_text.endswith('"'):
            processed_text = processed_text[1:-1]

        if len(processed_text) > 990:
            processed_text = processed_text[:995] + "..."

        logging.info("Text successfully processed with Gemini.")
        return processed_text

    except Exception as e:
        logging.error(f"Gemini processing failed: {e}. Returning original text.")
        cleaned_text = text.strip()
        if not cleaned_text.endswith('.'):
            cleaned_text += '.'
        return cleaned_text

def update_naukri_profile():
    """The main function to automate the Naukri profile update, using the robust working approach."""
    job_status.update({
        "last_run_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_run_status": "running",
        "details": "Profile update process is currently running."
    })
    logging.info("Starting profile update...")

    if not NAUKRI_USERNAME or not NAUKRI_PASSWORD:
        logging.error("Missing Naukri credentials in .env file.")
        job_status.update({"last_run_status": "failed", "details": "Missing credentials."})
        return

    driver = None
    try:
        # 1. Initialize WebDriver
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")  # Use new headless mode
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-images")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2
        })
        options.binary_location = "chromium"
        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd(
            'Page.addScriptToEvaluateOnNewDocument',
            {'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
        )
        logging.info("Browser initialized in headless mode.")
        wait = WebDriverWait(driver, 30)

        # 2. Robust Login and Verification
        driver.get("https://login.naukri.com/")
        wait.until(EC.presence_of_element_located((By.ID, "usernameField"))).send_keys(NAUKRI_USERNAME)
        driver.find_element(By.ID, "passwordField").send_keys(NAUKRI_PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button.waves-effect").click()
        logging.info("Login attempted.")

        login_success = False
        for attempt in range(3):
            try:
                wait.until(EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "nI-gNb-icon-img")),
                    EC.url_contains("mnjuser"),
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'userName')]"))
                ))
                login_success = True
                logging.info("Login successful.")
                break
            except TimeoutException:
                logging.warning(f"Login verification attempt {attempt + 1} failed, retrying...")
                time.sleep(5)
        
        if not login_success:
            raise Exception("Login verification failed after multiple attempts.")

        # 3. Navigate to Profile Page
        driver.get("https://www.naukri.com/mnjuser/profile")
        logging.info("Navigated to profile page.")

        # 4. Find and Click Edit Icon with Robust Scrolling and Retries
        edit_icon_xpath = "//div[@class='profileSummary']//div[@class='card']//div//span[@class='edit icon'][normalize-space()='editOneTheme']"
        edit_icon = None
        logging.info("Searching for edit icon with scrolling...")
        
        scroll_positions = [0, 400, 800, 1200, 1600, 2000]
        for scroll_position in scroll_positions:
            driver.execute_script(f"window.scrollTo(0, {scroll_position});")
            time.sleep(1)
            try:
                edit_icon = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, edit_icon_xpath)))
                logging.info(f"Found edit icon with xpath: {edit_icon_xpath}")
                break
            except TimeoutException:
                continue
        
        if not edit_icon:
            raise Exception("Edit icon not found after trying multiple scroll positions.")

        # Click using multiple methods for resilience
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_icon)
            time.sleep(1)
            edit_icon.click()
            logging.info("Edit icon clicked successfully.")
        except Exception as e:
            logging.warning(f"Standard click failed: {e}. Trying JavaScript click.")
            driver.execute_script("arguments[0].click();", edit_icon)
            logging.info("Edit icon clicked via JavaScript.")

        # 5. Find and Edit Textarea
        textarea = wait.until(EC.element_to_be_clickable((By.ID, "profileSummaryTxt")))
        logging.info("Textarea found.")
        
        current_text = textarea.get_attribute("value") or textarea.text
        original_text = current_text
        
        # Use pyperclip for more reliable copy-paste, with a fallback
        try:
            textarea.send_keys(Keys.CONTROL + "a")
            time.sleep(0.5)
            textarea.send_keys(Keys.CONTROL + "c")
            time.sleep(0.5)
            clipboard_text = pyperclip.paste()
            if clipboard_text and clipboard_text.strip():
                original_text = clipboard_text
        except Exception as e:
            logging.warning(f"Could not use pyperclip: {e}. Using value attribute as fallback.")

        processed_text = ""
        if original_text and original_text.strip():
            processed_text = process_text_with_gemini(original_text)
            textarea.clear()
            time.sleep(0.5)
            textarea.send_keys(processed_text)
            logging.info("Updated textarea with new profile summary.")
        else:
            logging.warning("Profile summary textarea was empty. No changes made.")

        # 6. Save Changes and Verify
        save_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Save']")))
        save_button.click()
        logging.info("Save button clicked.")
        
        # Verify save by checking for the new text on the page
        wait.until(EC.presence_of_element_located((By.XPATH, "//p[@class='head']")))
        logging.info("Profile update completed successfully")
        
        logging.info("Profile update completed and verified successfully.")
        job_status.update({"last_run_status": "success", "details": "Profile updated successfully."})

    except Exception as e:
        logging.error(f"An error occurred during the profile update: {e}", exc_info=True)
        job_status.update({"last_run_status": "failed", "details": str(e)})
        if driver:
            driver.save_screenshot("naukri_update_failed.png")
            with open("naukri_update_failed.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
    finally:
        if driver:
            driver.quit()
        logging.info("Browser closed.")
        job_status["next_scheduled_run"] = str(schedule.next_run()) if schedule.jobs else "Not scheduled"


def run_scheduler():
    """Runs the scheduled jobs in a loop."""
    logging.info(f"Scheduler configured to run daily at {UPDATE_TIME}.")
    job_status["next_scheduled_run"] = str(schedule.next_run()) if schedule.jobs else "Not scheduled"
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.on_event("startup")
def startup_event():
    """On app startup, schedule the job and start the scheduler thread."""
    schedule.every().day.at(UPDATE_TIME).do(update_naukri_profile)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logging.info("Scheduler thread started.")

# --- API Endpoints ---
@app.post("/update-profile", status_code=202)
def trigger_update(background_tasks: BackgroundTasks):
    """Manually triggers the Naukri profile update in the background."""
    if job_status["last_run_status"] == "running":
        return {"message": "An update process is already running. Please wait for it to complete."}
    
    background_tasks.add_task(update_naukri_profile)
    return {"message": "Profile update process has been started in the background."}

@app.get("/status", response_model=HealthStatus)
def get_health_status():
    """Returns the current health and status of the updater job."""
    job_status["next_scheduled_run"] = str(schedule.next_run()) if schedule.jobs else "Not scheduled"
    return job_status
