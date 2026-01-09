import re
import time

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

##############################################
# CONSTANTS
##############################################

EN_URL = "https://www.lacreme.ai/en"
BASE_URL = "https://www.lacreme.ai"
HEADERS = {"User-Agent": "Mozilla/5.0"}


##############################################
# DRIVER SETUP
##############################################


def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options,
    )

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            """
        },
    )

    return driver


##############################################
# DETAIL PAGE SCRAPER
##############################################


def fix(text):
    return text.replace("â\x82¬", "€") if text else ""


def scrape_detail(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        s = BeautifulSoup(r.text, "html.parser")

        image = s.select_one(".image-logiciel")
        website = s.select_one(".row-boutons a")
        description = s.select_one(".paragraph.top-margin")

        pricing_data = [p.get_text(strip=True) for p in s.select(".plans-comparateurs")]
        prices = [p for p in pricing_data if re.match(r"^\d", p)]
        units = [p for p in pricing_data if "€" in p or "month" in p]

        Basique = (
            fix(f"{prices[0]} {units[0]}") if len(prices) > 0 and len(units) > 0 else ""
        )
        Advanced = (
            fix(f"{prices[1]} {units[1]}") if len(prices) > 1 and len(units) > 1 else ""
        )
        Pro = (
            fix(f"{prices[2]} {units[2]}") if len(prices) > 2 and len(units) > 2 else ""
        )

        features_list = []
        block = s.find("div", class_="paragraph w-richtext")
        if block:
            current = ""
            for tag in block.find_all(["h3", "p"]):
                if tag.name == "h3":
                    current = tag.get_text(strip=True)
                else:
                    features_list.append(f"{current}: {tag.get_text(' ', strip=True)}")

        features = " | ".join(features_list)
        who_uses = ", ".join(
            x.get_text(strip=True) for x in s.select(".block-qui .text-block")
        )
        comparison = ", ".join(
            c.get_text(strip=True) for c in s.select(".grid-2x1 .medium")
        )

        return {
            "image": image["src"] if image else "",
            "website": website["href"] if website else "",
            "description": description.get_text(" ", strip=True) if description else "",
            "basique": Basique,
            "advanced": Advanced,
            "pro": Pro,
            "features": features,
            "who_uses": who_uses,
            "comparison": comparison,
        }

    except Exception:
        return {
            "image": "",
            "website": "",
            "description": "",
            "basique": "",
            "advanced": "",
            "pro": "",
            "features": "",
            "who_uses": "",
            "comparison": "",
        }


##############################################
# MAIN SCRAPER
##############################################


def run():
    driver = create_driver()
    driver.get(EN_URL)
    time.sleep(5)

    # -------- CLEAR FILTERS --------
    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        clear_selectors = [
            "[fs-cmsfilter-element='clear']",
            ".fs-cmsfilter_clear",
            "a[href*='reset']",
        ]

        for selector in clear_selectors:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    btn.click()
                    time.sleep(3)
                    break
            except Exception:
                pass

        checkboxes = driver.find_elements(
            By.CSS_SELECTOR, "input[type='checkbox']:checked"
        )
        for cb in checkboxes:
            try:
                driver.execute_script("arguments[0].click();", cb)
                time.sleep(0.2)
            except Exception:
                pass

        current_url = driver.current_url
        if "?" in current_url or "#" in current_url:
            driver.get(current_url.split("?")[0].split("#")[0])
            time.sleep(5)

    except Exception:
        pass

    # -------- WAIT FOR COUNTS --------
    expected_count = None
    try:
        wait = WebDriverWait(driver, 60)

        def counts_loaded(d):
            try:
                r = d.find_element(
                    By.CSS_SELECTOR, '[fs-cmsfilter-element="results-count"]'
                ).text.strip()
                i = d.find_element(
                    By.CSS_SELECTOR, '[fs-cmsfilter-element="items-count"]'
                ).text.strip()
                return r.isdigit() and i.isdigit() and r == i
            except Exception:
                return False

        wait.until(counts_loaded)
        expected_count = int(
            driver.find_element(
                By.CSS_SELECTOR, '[fs-cmsfilter-element="items-count"]'
            ).text.strip()
        )
    except Exception:
        pass

    # -------- AGGRESSIVE SCROLL --------
    last_count = 0
    stall_counter = 0
    max_stalls = 8
    scroll_speed = 1.0

    while True:
        viewport = driver.execute_script("return window.innerHeight")

        for _ in range(3):
            driver.execute_script(f"window.scrollBy(0, {viewport * 0.8});")
            time.sleep(0.15 * scroll_speed)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.3 * scroll_speed)

        driver.execute_script(
            """
            window.dispatchEvent(new Event('scroll'));
            window.dispatchEvent(new Event('resize'));
            window.dispatchEvent(new Event('load'));
        """
        )

        current_count = len(
            driver.find_elements(By.CSS_SELECTOR, ".collection-item-home")
        )

        if current_count == last_count:
            stall_counter += 1
            scroll_speed = max(0.3, scroll_speed * 0.8)
        else:
            stall_counter = 0
            scroll_speed = 1.0

        if stall_counter >= max_stalls:
            break

        if expected_count and current_count >= expected_count:
            break

        last_count = current_count

    # -------- PARSE SUMMARY --------
    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.select(".collection-item-home")

    tools = []
    for card in cards:
        try:
            name = card.select_one('[fs-cmsfilter-field="name"]').get_text(strip=True)
            short_desc = card.select_one(
                '[fs-cmsfilter-field="short description"]'
            ).get_text(strip=True)
            logo = card.select_one("img.image-cart")["src"]
            categories = [
                c.get_text(strip=True) for c in card.select(".card-outils-categories")
            ]
            detail_path = card.select_one("a")["href"]

            tools.append(
                {
                    "name": name,
                    "short_description": short_desc,
                    "logo_url": logo,
                    "categories": categories,
                    "detail_url": (
                        BASE_URL + detail_path
                        if detail_path.startswith("/")
                        else detail_path
                    ),
                }
            )
        except Exception:
            continue

    # -------- DETAIL LOOP --------
    records = []

    for tool in tools:
        detail = scrape_detail(tool["detail_url"])
        records.append(
            {
                "name": tool["name"],
                "short_description": tool["short_description"],
                "logo_url": tool["logo_url"],
                "categories": tool["categories"],
                "website": detail["website"],
                "description": detail["description"],
                "pricing_basique": detail["basique"],
                "pricing_advanced": detail["advanced"],
                "pricing_pro": detail["pro"],
                "features": detail["features"],
                "who_uses": detail["who_uses"],
                "comparison": detail["comparison"],
                "source": "lacreme",
            }
        )
        time.sleep(0.25)

    driver.quit()
    return records
