import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

SEARCH_URL = "https://theresanaiforthat.com/s/{query}/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


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


def parse_pricing_type(pricing_text):
    """
    Parse pricing text from TAAFT and return pricing_type.

    Examples:
    - "100% Free" -> "free"
    - "Free + from $X/mo" -> "freemium"
    - "From $X/mo" or "From $X" -> "paid"
    - "No pricing" -> "paid" (enterprise/contact)
    """
    if not pricing_text:
        return None

    pricing_text = pricing_text.strip().lower()

    if "100% free" in pricing_text:
        return "free"
    elif "free +" in pricing_text or "free+" in pricing_text:
        return "freemium"
    elif pricing_text.startswith("from") or "$" in pricing_text:
        return "paid"
    elif "no pricing" in pricing_text:
        return "paid"

    return None


def search_tool_pricing(tool_name, driver=None):
    """
    Search TAAFT for a tool and return its pricing information.

    Returns dict with:
    - pricing_type: 'free', 'freemium', or 'paid'
    - pricing_text: original pricing text from TAAFT
    - category: task/category from TAAFT
    - found: whether the tool was found
    """
    close_driver = False
    if driver is None:
        driver = create_driver()
        close_driver = True

    try:
        query = tool_name.lower().replace(" ", "+")
        url = SEARCH_URL.format(query=query)

        driver.get(url)
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        tool_items = soup.select("li[data-name]")

        for item in tool_items:
            item_name = item.get("data-name", "").lower()
            if tool_name.lower() in item_name or item_name in tool_name.lower():
                pricing_text = ""

                for link in item.select("a"):
                    text = link.get_text(strip=True)
                    if (
                        "free" in text.lower()
                        or "$" in text
                        or "from" in text.lower()
                        or "no pricing" in text.lower()
                    ):
                        pricing_text = text
                        break

                category_link = item.select_one("a[href*='/task/']")
                category = category_link.get_text(strip=True) if category_link else None

                return {
                    "found": True,
                    "pricing_text": pricing_text,
                    "pricing_type": parse_pricing_type(pricing_text),
                    "category": category,
                    "taaft_name": item.get("data-name"),
                }

        return {
            "found": False,
            "pricing_text": None,
            "pricing_type": None,
            "category": None,
            "taaft_name": None,
        }

    except Exception as e:
        print(f"Error searching for {tool_name}: {e}")
        return {
            "found": False,
            "pricing_text": None,
            "pricing_type": None,
            "category": None,
            "taaft_name": None,
            "error": str(e),
        }

    finally:
        if close_driver:
            driver.quit()


def batch_search_tools(tool_names, delay=2):
    """
    Search TAAFT for multiple tools.

    Args:
        tool_names: list of tool names to search
        delay: seconds to wait between searches

    Returns:
        dict mapping tool_name -> pricing info
    """
    driver = create_driver()
    results = {}

    try:
        for i, name in enumerate(tool_names):
            print(f"Searching {i + 1}/{len(tool_names)}: {name}")
            results[name] = search_tool_pricing(name, driver)
            if i < len(tool_names) - 1:
                time.sleep(delay)
    finally:
        driver.quit()

    return results


def get_ai_categories():
    """
    Return a list of common AI tool categories.
    These are based on TAAFT's task categories.
    """
    return [
        "Writing",
        "Images",
        "Videos",
        "Audio",
        "Music",
        "Code",
        "Chatbots",
        "Customer Support",
        "Marketing",
        "SEO",
        "Social Media",
        "Email",
        "Sales",
        "Productivity",
        "Research",
        "Education",
        "Finance",
        "Legal",
        "HR",
        "Design",
        "3D",
        "Animation",
        "Voice",
        "Transcription",
        "Translation",
        "Data Analysis",
        "Automation",
        "No-Code",
        "Developer Tools",
        "API",
        "Security",
        "Healthcare",
        "Real Estate",
        "E-commerce",
        "Gaming",
        "Personal Assistant",
        "Meeting",
        "Presentation",
        "Spreadsheets",
        "Documents",
        "Search",
        "Browser",
        "Mobile Apps",
    ]
