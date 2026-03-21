"""
Selenium WebDriver utilities for headless browser scraping.
Provides consistent driver configuration across all scrapers.
"""

import logging
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver

from config.scraper_settings import ScraperConfig

logger = logging.getLogger(__name__)


def create_driver(
    headless: bool = True,
    user_agent: Optional[str] = None,
    page_load_timeout: Optional[int] = None,
    chrome_binary: Optional[str] = None,
    chromedriver_path: Optional[str] = None,
) -> WebDriver:
    """
    Create a configured Selenium Chrome WebDriver.

    Args:
        headless: Run browser in headless mode
        user_agent: Custom user agent string
        page_load_timeout: Page load timeout in seconds
        chrome_binary: Path to Chrome binary
        chromedriver_path: Path to ChromeDriver executable

    Returns:
        Configured WebDriver instance
    """
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")

    _user_agent = user_agent or ScraperConfig.USER_AGENT
    options.add_argument(f"--user-agent={_user_agent}")

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    _chrome_binary = chrome_binary or ScraperConfig.CHROME_BINARY
    if _chrome_binary:
        options.binary_location = _chrome_binary

    _chromedriver_path = chromedriver_path or ScraperConfig.CHROMEDRIVER_PATH
    if _chromedriver_path:
        service = Service(executable_path=_chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    _page_load_timeout = page_load_timeout or ScraperConfig.PAGE_LOAD_TIMEOUT
    driver.set_page_load_timeout(_page_load_timeout)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """},
    )

    logger.info(f"Created WebDriver (headless={headless})")
    return driver


def scroll_page(
    driver: WebDriver,
    scroll_pause_time: float = 2.0,
    max_scrolls: int = 50,
) -> int:
    """
    Scroll down a page to load dynamic content.

    Args:
        driver: WebDriver instance
        scroll_pause_time: Time to wait between scrolls
        max_scrolls: Maximum number of scroll attempts

    Returns:
        Number of scrolls performed
    """
    import time

    last_height = driver.execute_script("return document.body.scrollHeight")
    scrolls = 0

    while scrolls < max_scrolls:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause_time)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break

        last_height = new_height
        scrolls += 1

    logger.info(f"Performed {scrolls} scrolls")
    return scrolls
