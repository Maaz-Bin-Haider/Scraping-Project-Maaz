import os
import time
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Debugging: Check if the environment variable is set
firebase_creds = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
if not firebase_creds:
    print("Firebase credentials not found in environment variable.")
    raise ValueError("Firebase credentials not found in environment variable.")

# Write the credentials to a temporary file
with open('firebase_credentials.json', 'w') as f:
    f.write(firebase_creds)

# Initialize Firebase
cred = credentials.Certificate('firebase_credentials.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Setup Chrome WebDriver with options for headless mode
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# List of URLs to scrape
urls = [
    'https://www.jbhifi.com.au/products/hp-9t0j6pa-14-hd-laptop-256gbamd-athlon-silver',
    'https://www.jbhifi.com.au/products/apple-ipad-10-9-inch-64gb-wi-fi-silver-10th-gen',
    'https://www.jbhifi.com.au/products/lenovo-ideacentre-aio-3-27-fhd-all-in-one-pc-intel-i5512gb',
    'https://www.jbhifi.com.au/products/aftershock-rapid-gaming-desktop-pc-ryzen-5-7500f-rtx-4060ti',
    'https://www.jbhifi.com.au/products/apple-macbook-pro-14-inch-with-m3-pro-chip-512gb-ssd-space-black2023',
    'https://www.jbhifi.com.au/products/samsung-galaxy-s24-ultra-5g-256gb-titanium-grey'
]
itemNames = ['Hp Laptop', 'Ipad', 'Lenovo PC', "Afterstock Gaming PC",'Macbook Pro M3','Galaxy S24 Ultra']
itemPrices = []


def safe_find_element(by, value):
    for _ in range(3):  # Retry 3 times
        try:
            element = driver.find_element(by, value)
            return element
        except Exception as e:
            time.sleep(1)  # Wait before retrying
    raise Exception("Failed to find element after 3 retries")

def scrape_price(url, index):
    driver.get(url)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'PriceTag_actualWrapperDefault__1eb7mu9p'))
        )
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        # Use safe_find_element to ensure we handle any stale element exceptions
        parent_element = safe_find_element(By.CLASS_NAME, 'PriceTag_actualWrapperDefault__1eb7mu9p')
        price_element = parent_element.find_element(By.CLASS_NAME, 'PriceTag_actual__1eb7mu9q')
        price = price_element.text
        itemPrices.append(price)

    except Exception as e:
        itemPrices.append('0')
        print(f"Error scraping {url}: {e}")

# Iterate over each URL and scrape the price
for i, url in enumerate(urls):
    scrape_price(url, i)

# Close the browser
driver.quit()

# Print scraped data
for i, name in enumerate(itemNames):
    print(f"{name} price: {itemPrices[i]}")

# Save scraped data to Firestore
def save_to_firestore(itemNames, itemPrices, urls):
    for i, name in enumerate(itemNames):
        doc_ref = db.collection('products').document(name)
        doc_ref.set({
            'name': name,
            'price': itemPrices[i],
            'url': urls[i],
        }, merge=True)
    print("Data saved to Firestore successfully.")

save_to_firestore(itemNames, itemPrices, urls)

def notify_users():
    # Get all products
    products = db.collection('products').stream()

    for product in products:
        product_data = product.to_dict()
        product_id = product.id
        
        # Ensure that price and targetedPrice are not None before converting
        current_price_str = product_data.get('price')
        targeted_price_str = product_data.get('targetedPrice')
        
        if current_price_str is not None and targeted_price_str is not None:
            try:
                # Convert price strings to float after removing any unwanted characters
                current_price = float(current_price_str.replace('$', '').replace(',', '').strip())
                targeted_price = float(str(targeted_price_str).replace('$', '').replace(',', '').strip())
                
                print(f"Current price: {current_price}")
                print(f"Targeted price: {targeted_price}")
                
                # Check if current price is less than or equal to targeted price
                if current_price <= targeted_price:
                    # Retrieve all FCM tokens
                    tokens = db.collection('UsersInfo').stream()
                    
                    for token_doc in tokens:
                        token_data = token_doc.to_dict()
                        fcm_token = token_data.get('FCM-Token')
                        
                        if fcm_token:
                            # Image URL for notification (must be accessible via public URL)
                            notification_image_url = "https://firebasestorage.googleapis.com/v0/b/project-scraper-694a2.appspot.com/o/logo2.png?alt=media&token=938d3e08-f7b1-4617-b147-06b6c58c6103"  # Replace with your image URL

                            message = messaging.Message(
                                notification=messaging.Notification(
                                    title='Price Alert!',
                                    body=f'The price for {product_id} has dropped to {current_price}.',
                                    image=notification_image_url,
                                    
                                ),
                                token=fcm_token,
                                android=messaging.AndroidConfig(
                                    priority='high',
                                    notification=messaging.AndroidNotification(
                                        icon='launcher_icon'  # Use the drawable resource name
                                    )  # Ensure high-priority delivery
                                )
                            )
                            try:
                                response = messaging.send(message)
                                print(f'Successfully sent message: {response}')

                                time.sleep(2)  # Adjust as needed
                            except Exception as e:
                                print(f'Failed to send message: {e}')
            except ValueError as e:
                print(f'Error converting prices for product {product_id}: {e}')
        else:
            print(f"Skipping product {product_id} due to missing price or targetedPrice.")


# calling
notify_users()








# Cleanup: remove the temporary credentials file
os.remove('firebase_credentials.json')
