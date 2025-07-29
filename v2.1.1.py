# Este script permite realizar múltiples búsquedas consecutivas. 
# Incluye correcciones para el manejo adecuado de ChromeOptions y evita errores de reutilización.
# También asegura el correcto manejo de entradas completas/incompletas y nombres de archivos únicos.

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import re
import time
import os
from datetime import datetime

# Clase personalizada para Chrome
class CustomChrome(uc.Chrome):
    def __del__(self):
        pass  # Evitar cierre automático

# Configuración del directorio de salida
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)

def setup_driver():
    """Inicializa el navegador Chrome."""
    print("[INFO] Setting up the Chrome driver...")
    options = uc.ChromeOptions()  # Crear un nuevo objeto ChromeOptions para cada ejecución
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = CustomChrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.navigator.chrome = {runtime: {}};
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """
    })
    return driver

def search_google(driver, query):
    """Realiza una búsqueda en Google."""
    print("[INFO] Accessing Google...")
    driver.get("https://www.google.com")
    try:
        accept_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept all')] | //button[contains(., 'Aceptar todo')]"))
        )
        accept_button.click()
        print("[INFO] Cookies accepted.")
    except:
        print("[INFO] No cookie acceptance button found.")
    search_box = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "q")))
    search_box.send_keys(query)
    search_box.send_keys(Keys.RETURN)
    print("[INFO] Search query submitted.")

def extract_emails(text):
    """Extrae correos válidos de un texto."""
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    return [email for email in emails if not email.startswith("950000000")]

def extract_phones(text):
    """Extrae números de teléfono válidos de un texto."""
    phones = re.findall(r"\(?\+?\d{1,3}\)?[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,9}", text)
    return [phone for phone in phones if len(re.sub(r"\D", "", phone)) >= 7]

def extract_results(driver, include_incomplete, max_pages, category, country):
    """Extrae resultados de Google y organiza los datos en filas únicas por combinación de correo/teléfono."""
    results = []
    page = 1

    while page <= max_pages:
        try:
            print(f"[INFO] Extracting results from page {page}...")
            search_results = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, "//div[@class='MjjYud']"))
            )
            for idx, result in enumerate(search_results, start=1 + (page - 1) * 10):
                try:
                    title_element = result.find_elements(By.TAG_NAME, 'h3')
                    link_element = result.find_elements(By.TAG_NAME, 'a')
                    snippet_element = result.find_elements(By.CLASS_NAME, 'VwiC3b')

                    title = title_element[0].text if title_element else "N/A"
                    link = link_element[0].get_attribute('href') if link_element else "N/A"
                    description = snippet_element[0].text if snippet_element else "N/A"

                    emails = extract_emails(description)
                    phones = extract_phones(description)

                    if not include_incomplete:
                        if not emails or not phones:
                            print(f"[INFO] Skipping incomplete result: Title={title}, Emails={emails}, Phones={phones}")
                            continue

                    for email in emails or ["N/A"]:
                        for phone in phones or ["N/A"]:
                            results.append({
                                "Name": title.split(" - ")[0] if " - " in title else "N/A",
                                "Company": title.split(" - ")[1] if " - " in title else title,
                                "Phone": phone,
                                "Detail": description,
                                "Link": link,
                                "Email": email,
                                "Category": category,
                                "Country": country
                            })
                except Exception as e:
                    print(f"[WARNING] Skipping result {idx}: {e}")

            next_button = driver.find_elements(By.XPATH, "//a[@id='pnnext']")
            if next_button:
                next_button[0].click()
                page += 1
                time.sleep(2)
            else:
                print("[INFO] No 'Next' button found. Stopping extraction.")
                break
        except Exception as e:
            print(f"[ERROR] Failed to process page {page}: {e}")
            break

    return results

def unique_filename(base_filename):
    """Genera un nombre de archivo único si ya existe."""
    counter = 1
    filename = base_filename
    while os.path.exists(filename):
        filename = f"{base_filename}({counter})"
        counter += 1
    return filename

def save_to_files(data, category, country, include_incomplete):
    """Guarda los datos en archivos CSV y Excel."""
    if not data:
        print("[WARNING] No data to save.")
        return
    completeness = "completo" if not include_incomplete else "incompleto"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"{output_dir}/{category}-{country}-{completeness}-{timestamp}"
    csv_filename = unique_filename(f"{base_filename}.csv")
    excel_filename = unique_filename(f"{base_filename}.xlsx")
    df = pd.DataFrame(data)
    df.to_csv(csv_filename, index=False)
    df.to_excel(excel_filename, index=False)
    print(f"[INFO] Data saved to {csv_filename} and {excel_filename}")

def main():
    """Función principal."""
    while True:
        category = input("Enter the company category (e.g., distribuidoras): ")
        country = input("Enter the country code (e.g., PE for Peru): ")
        include_incomplete = input("Do you want to include contacts without email or phone? (yes/no): ").strip().lower() == "yes"
        max_pages = int(input("Enter the maximum number of pages to scrape (recommended 5-20): "))
        query = f'"{category}" "{country}" "@gmail.com"'
        print(f"[INFO] Using search query: {query}")

        driver = setup_driver()
        try:
            search_google(driver, query)
            results = extract_results(driver, include_incomplete, max_pages, category, country)
            save_to_files(results, category, country, include_incomplete)
        finally:
            driver.quit()
            print("[INFO] Chrome driver closed.")

        another_search = input("Do you want to perform another search? (yes/no): ").strip().lower()
        if another_search != "yes":
            print("[INFO] Ending the script.")
            break

if __name__ == "__main__":
    main()
