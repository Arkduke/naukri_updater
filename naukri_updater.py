import os
import time
import schedule
import pyperclip
import logging
from google import genai 
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

load_dotenv()

NAUKRI_USERNAME = os.environ.get("NAUKRI_USERNAME")
NAUKRI_PASSWORD = os.environ.get("NAUKRI_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
UPDATE_TIME = os.environ.get("UPDATE_TIME")

def process_text_with_gemini(text):
    try:
        if not GEMINI_API_KEY:
            return text
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""Just change one or two words with buzzwords that will attract recruiters for the profile summary,
        profile summary: {text}
        rest of the things should remain same
        remember do not provide any options or anything else unrelated to profile summary.
        follow the profile summary format for the output do not add extra annotations.
        """
        
        response = client.models.generate_content(model='gemini-2.5-flash',contents=prompt)
        processed_text = response.text.strip()
        
        if processed_text.startswith('"') and processed_text.endswith('"'):
            processed_text = processed_text[1:-1]
        
        if len(processed_text) > 990:
            processed_text = processed_text[:995] + "..."
        
        logging.info("Text processed with Gemini")
        return processed_text
        
    except Exception as e:
        logging.error(f"Gemini processing failed: {e}")
        cleaned_text = text.strip()
        if not cleaned_text.endswith('.'):
            cleaned_text += '.'
        
        return cleaned_text

def update_naukri_profile():
    logging.info("Starting profile update")
    
    if not NAUKRI_USERNAME or not NAUKRI_PASSWORD:
        logging.error("Missing credentials")
        return
    
    try:
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        # Enhanced headless mode with stealth options
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
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logging.info("Browser initialized")
    except Exception as e:
        logging.error(f"Browser initialization failed: {e}")
        return

    try:
        login_url = "https://login.naukri.com/"
        driver.get(login_url)
        logging.info("Navigated to login page")

        wait = WebDriverWait(driver, 30)  # Increased timeout
        
        # Wait for page to load
        time.sleep(3)
        
        username_field = wait.until(EC.presence_of_element_located((By.ID, "usernameField")))
        username_field.clear()
        username_field.send_keys(NAUKRI_USERNAME)
        time.sleep(1)

        password_field = driver.find_element(By.ID, "passwordField")
        password_field.clear()
        password_field.send_keys(NAUKRI_PASSWORD)
        time.sleep(1)

        login_button = driver.find_element(By.CSS_SELECTOR, "button.waves-effect")
        login_button.click()
        logging.info("Login attempted")

        # Wait longer for login to complete with multiple checks
        login_success = False
        for attempt in range(3):
            try:
                # Check for successful login by looking for profile elements
                wait.until(EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "nI-gNb-icon-img")),
                    EC.url_contains("mnjuser"),
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'userName')]"))
                ))
                login_success = True
                logging.info("Login successful")
                break
            except TimeoutException:
                logging.warning(f"Login attempt {attempt + 1} failed, retrying...")
                time.sleep(5)
        
        if not login_success:
            # Take screenshot for debugging
            driver.save_screenshot("d:/Project/naukri_updater/login_failed.png")
            logging.error("Login failed after 3 attempts")
            raise Exception("Login verification failed")
        
        # Navigate to profile page
        profile_url = "https://www.naukri.com/mnjuser/profile"
        driver.get(profile_url)
        logging.info("Navigated to profile page")
        
        # Wait for page to load completely
        time.sleep(5)

        # Wait for page to load completely
        time.sleep(5)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        driver.execute_script("window.scrollTo(0, 0);")
        
        # More comprehensive edit icon patterns
        edit_icon_xpaths = [
            "//div[@class='profileSummary']//div[@class='card']//div//span[@class='edit icon'][normalize-space()='editOneTheme']",
        ]
        
        edit_icon = None
        logging.info("Searching for edit icon...")
        
        # First, try to find any edit icons on the page
        all_elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'edit') or contains(text(), 'edit') or contains(@title, 'edit')]")
        logging.info(f"Found {len(all_elements)} elements with 'edit' in them")
        
        for xpath in edit_icon_xpaths:
            try:
                scroll_positions = [0, 400, 800, 1200, 1600, 2000, 2400]
                
                for scroll_position in scroll_positions:
                    driver.execute_script(f"window.scrollTo(0, {scroll_position});")
                    time.sleep(1)
                    
                    try:
                        edit_icon = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))  # Increased timeout
                        logging.info(f"Found edit icon with xpath: {xpath}")
                        break
                    except TimeoutException:
                        continue
                
                if edit_icon:
                    break
                    
            except TimeoutException:
                continue
        
        if not edit_icon:
            # Take a screenshot for debugging
            driver.save_screenshot("d:/Project/naukri_updater/debug_screenshot.png")
            logging.info("Screenshot saved as debug_screenshot.png")
            
            # Get page source for debugging
            with open("d:/Project/naukri_updater/page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logging.info("Page source saved as page_source.html")
            
            logging.error("Edit icon not found after trying all patterns")
            raise Exception("Edit icon not found after trying multiple patterns and scroll positions")
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", edit_icon)
        time.sleep(2)
        
        try:
            edit_icon.click()
            logging.info("Edit icon clicked")
        except Exception as e1:
            try:
                driver.execute_script("arguments[0].click();", edit_icon)
            except Exception as e2:
                try:
                    actions = ActionChains(driver)
                    actions.move_to_element(edit_icon).click().perform()
                except Exception as e3:
                    alternative_edit_xpath = "//span[contains(@class, 'edit') and contains(@class, 'icon')]"
                    alternative_edits = driver.find_elements(By.XPATH, alternative_edit_xpath)
                    for alt_edit in alternative_edits:
                        try:
                            if alt_edit.is_displayed() and alt_edit.is_enabled():
                                driver.execute_script("arguments[0].click();", alt_edit)
                                break
                        except:
                            continue
                    else:
                        raise Exception("All click methods failed")

        # More comprehensive textarea patterns
        textarea_xpaths = [
            "//textarea[@id='profileSummaryTxt']",
        ]
        
        textarea = None
        logging.info("Searching for textarea...")
        
        for xpath in textarea_xpaths:
            try:
                textarea = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                logging.info(f"Found textarea with xpath: {xpath}")
                break
            except TimeoutException:
                continue
        
        if not textarea:
            all_textareas = driver.find_elements(By.TAG_NAME, "textarea")
            all_editables = driver.find_elements(By.XPATH, "//div[@contenteditable='true']")
            logging.info(f"Found {len(all_textareas)} textareas and {len(all_editables)} editable divs")
            
            if all_textareas:
                textarea = all_textareas[0]
                logging.info("Using first available textarea")
            elif all_editables:
                textarea = all_editables[0]
                logging.info("Using first available editable div")
            else:
                logging.error("No textarea or editable element found")
                raise Exception("Textarea not found after trying multiple patterns")
        
        textarea.click()
        time.sleep(1)
        logging.info("Textarea found and focused")
        
        current_text = textarea.get_attribute("value") or textarea.text
        
        textarea.send_keys(Keys.CONTROL + "a")
        time.sleep(0.5)
        
        textarea.send_keys(Keys.CONTROL + "c")
        time.sleep(0.5)
        
        try:
            original_text = pyperclip.paste()
            if not original_text or original_text.strip() == "":
                original_text = current_text
        except Exception as e:
            original_text = current_text
        
        if original_text and original_text.strip():
            processed_text = process_text_with_gemini(original_text)
            
            textarea.clear()
            time.sleep(0.5)
            textarea.send_keys(processed_text)
        
        time.sleep(2)

        save_button_xpath = "//button[normalize-space()='Save']"
        save_button = wait.until(EC.element_to_be_clickable((By.XPATH, save_button_xpath)))
        
        save_button.click()
        logging.info("Save button clicked")
        
        wait.until(EC.presence_of_element_located((By.XPATH, "//p[@class='head']")))
        logging.info("Profile update completed successfully")

    except TimeoutException:
        logging.error("Timeout occurred")
    except NoSuchElementException as e:
        logging.error("Element not found")
    except Exception as e:
        logging.error(f"Update failed: {e}")
    finally:
        driver.quit()
        logging.info("Browser closed")


if __name__ == "__main__":
    logging.info(f"Scheduler started - runs daily at {UPDATE_TIME}")
    schedule.every().day.at(UPDATE_TIME).do(update_naukri_profile)
    # update_naukri_profile()
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Scheduler stopped")
        pass

