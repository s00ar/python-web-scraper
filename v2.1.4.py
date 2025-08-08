# -*- coding: utf-8 -*-
# Scraper de Google con Selenium + undetected_chromedriver
# - Búsqueda por URL (evita overlays y clics interceptados)
# - Paginación por start=
# - Consentimiento de Google (con/sin iframe) y click JS de respaldo
# - Esperas explícitas y guardado CSV/XLSX

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)
import pandas as pd
import re
import time
import os
from datetime import datetime
from urllib.parse import quote_plus

# =========================
# Clase personalizada Chrome
# =========================
class CustomChrome(uc.Chrome):
    def __del__(self):
        # Evita cierre por GC en algunos entornos
        pass

# =========================
# Configuración
# =========================
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)

def setup_driver():
    """Inicializa el navegador Chrome."""
    print("[INFO] Setting up the Chrome driver...")
    options = uc.ChromeOptions()
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

def _try_click(driver, elem):
    """Intenta click normal y, de fallback, click por JS."""
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(elem))
        elem.click()
        return True
    except (ElementClickInterceptedException, StaleElementReferenceException, TimeoutException):
        try:
            driver.execute_script("arguments[0].click();", elem)
            return True
        except Exception:
            return False

def _find_consent_buttons(driver):
    """Devuelve posibles botones de Aceptar/Rechazar del diálogo de consentimiento."""
    XPATHS = [
        # Botón clásico
        "//button[@id='L2AGLb']",
        # Variantes por texto (ES/EN)
        "//div[@role='dialog']//button[contains(., 'Aceptar todo')]",
        "//div[@role='dialog']//button[contains(., 'Acepto')]",
        "//div[@role='dialog']//button[contains(., 'Aceptar')]",
        "//div[@role='dialog']//button[contains(., 'Accept all')]",
        "//div[@role='dialog']//button[contains(., 'I agree')]",
        # Por aria-label
        "//button[contains(@aria-label, 'Aceptar') or contains(@aria-label, 'Accept')]",
        # Botones dentro de formularios de consentimiento
        "//form[contains(@action,'consent') or contains(@action,'setConsent')]//button[contains(., 'Aceptar') or contains(., 'Accept')]",
    ]
    found = []
    for xp in XPATHS:
        found.extend(driver.find_elements(By.XPATH, xp))
    # Filtrar duplicados y no visibles
    unique = []
    seen = set()
    for e in found:
        try:
            if e.is_displayed() and e.is_enabled():
                key = e.get_attribute("outerHTML")
                if key and key not in seen:
                    unique.append(e)
                    seen.add(key)
        except Exception:
            pass
    return unique

def accept_consent_if_any(driver, timeout=10):
    """
    Acepta el consentimiento de Google si aparece.
    - Prueba primero en el documento principal.
    - Si no, entra en iframes que contengan 'consent' / 'callout'.
    - Usa click normal y fallback JS.
    - Espera a salir de consent.google.com.
    """
    wait = WebDriverWait(driver, timeout)
    # 1) Intento en el documento principal
    try:
        buttons = _find_consent_buttons(driver)
        for b in buttons:
            if _try_click(driver, b):
                print("[INFO] Cookies accepted (main document).")
                time.sleep(0.3)
                break
    except Exception:
        pass

    # 2) Intento en iframes de consentimiento
    try:
        iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='consent'], iframe[name*='consent'], iframe[name^='callout']")
        for i, frame in enumerate(iframes):
            try:
                driver.switch_to.frame(frame)
                buttons = _find_consent_buttons(driver)
                clicked = False
                for b in buttons:
                    if _try_click(driver, b):
                        print(f"[INFO] Cookies accepted (iframe #{i}).")
                        clicked = True
                        time.sleep(0.3)
                        break
                driver.switch_to.default_content()
                if clicked:
                    break
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
    except Exception:
        pass

    # 3) Esperar a que el host no sea consent.google.com
    try:
        wait.until(lambda d: "consent.google" not in d.current_url)
    except TimeoutException:
        pass

def search_google(driver, query):
    """Abre directamente la página de resultados de Google."""
    print("[INFO] Accessing Google...")
    driver.get("https://www.google.com")
    accept_consent_if_any(driver)

    search_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=es"
    driver.get(search_url)

    # Esperar a que carguen los resultados
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.MjjYud"))
        )
    except Exception:
        pass

    print("[INFO] Search query submitted via URL.")

def extract_emails(text):
    emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    return [email for email in emails if not email.startswith("950000000")]

def extract_phones(text):
    phones = re.findall(r"\(?\+?\d{1,3}\)?[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,9}", text)
    return [phone for phone in phones if len(re.sub(r"\D", "", phone)) >= 7]

def extract_results(driver, include_incomplete, max_pages, category, country, query):
    """Extrae resultados y navega por páginas usando start=."""
    results = []
    page = 1

    while page <= max_pages:
        try:
            print(f"[INFO] Extracting results from page {page}...")
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.MjjYud"))
            )
            search_results = driver.find_elements(By.CSS_SELECTOR, "div.MjjYud")

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

                    if not include_incomplete and (not emails or not phones):
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

            if page < max_pages:
                next_start = page * 10
                next_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=es&start={next_start}"
                driver.get(next_url)
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.MjjYud"))
                    )
                except Exception:
                    pass
                page += 1
                time.sleep(0.8)
            else:
                break
        except Exception as e:
            print(f"[ERROR] Failed to process page {page}: {e}")
            break

    return results

def unique_filename(base_filename):
    counter = 1
    filename = base_filename
    while os.path.exists(filename):
        filename = f"{base_filename}({counter})"
        counter += 1
    return filename

def save_to_files(data, category, country, include_incomplete):
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
            # IMPORTANTE: pasar query aquí
            results = extract_results(driver, include_incomplete, max_pages, category, country, query)
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
