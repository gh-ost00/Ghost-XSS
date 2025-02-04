import logging
import requests
import urllib.parse
import concurrent.futures
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import argparse
import sys
import pyfiglet

GREEN = '\033[92m'
PINK = '\033[95m'
RESET = '\033[0m'
CYAN = '\033[96m'
RED = '\033[91m'
BOLD = '\033[1m'

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

def print_banner():
    ascii_art = pyfiglet.figlet_format("Ghost XSS", font="slant")
    print(f"{BOLD}{RED}{ascii_art}{RESET}")
    print(f"{BOLD}{RED}💀 Automatic XSS Scanner Tool 2024 | By GhostSec 💀{RESET}\n")

def create_session():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def setup_logging(output_file):
    file_handler = logging.FileHandler(output_file, mode='w')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(file_handler)

def crawl_website(base_url):
    session = create_session()
    visited = set()
    urls_to_visit = [base_url]
    collected_urls = []

    while urls_to_visit:
        current_url = urls_to_visit.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)
        try:
            response = session.get(current_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urllib.parse.urljoin(base_url, href)
                if base_url in full_url and full_url not in visited:
                    urls_to_visit.append(full_url)
                    collected_urls.append(full_url)
        except requests.RequestException as e:
            logger.error(f"{RED} ❌ [ERROR] Failed to crawl URL: {current_url} - {e}{RESET}")

    return collected_urls

def find_parameters(url):
    parsed_url = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed_url.query)
    return list(query.keys()) if query else []

def check_xss_with_selenium(url, timeout=10):
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--headless")

    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        driver.get(url)
        driver.implicitly_wait(timeout)
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            alert.accept()
            return True, alert_text
        except Exception:
            return False, None
    finally:
        driver.quit()

def test_xss_on_url(url, parameters, payloads):
    base_url, query_string = url.split('?', 1) if '?' in url else (url, '')
    original_params = urllib.parse.parse_qs(query_string)

    for payload in payloads:
        for param in parameters:
            test_params = original_params.copy()
            test_params[param] = payload
            encoded_query = urllib.parse.urlencode(test_params, doseq=True)
            test_url = f"{base_url}?{encoded_query}"

            is_vuln, _ = check_xss_with_selenium(test_url)
            if is_vuln:
                logger.info(f"{GREEN}✅ [VULN] URL: {test_url} - [XSS DETECTED!]{RESET}")
            else:
                logger.info(f"{RED}🔎 [INFO] URL: {test_url} - [No XSS detected].{RESET}")

def main():
    print_banner()

    parser = argparse.ArgumentParser(description="XSS Vulnerability Crawler & Checker Tool")
    parser.add_argument('-u', '--url', type=str, required=True, help="Base URL to crawl and test for XSS vulnerabilities.")
    parser.add_argument('-p', '--payloads', type=str, default='payloads.txt', help="File containing XSS payloads.")
    parser.add_argument('-o', '--output', type=str, default='xss_scan_results.txt', help="File to save the scan results.")
    args = parser.parse_args()

    setup_logging(args.output)

    payloads = []
    try:
        with open(args.payloads, 'r') as file:
            payloads = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        logger.error(f"{RED}❌ Payloads file '{args.payloads}' NOT FOUND.{RESET}")
        sys.exit(1)

    logger.info(f"{CYAN} [START] Searching for vulnerable parameters: {args.url}...{RESET}")
    urls = crawl_website(args.url)
    logger.info(f"{CYAN} [INFO] Found {len(urls)} URLs to test.{RESET}")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for url in urls:
            parameters = find_parameters(url)
            if parameters:
                logger.info(f"{CYAN}⚙️ [Testing] URL: {url} with parameters: {list(parameters)}{RESET}")
                futures.append(executor.submit(test_xss_on_url, url, parameters, payloads))

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"{RED} ❌ [ERROR] An error occurred during XSS testing: {e}{RESET}")

    logger.info(f"{CYAN}✔️ [COMPLETE] Scan results saved to '{args.output}'{RESET}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RESET}{CYAN}⚠️ [INFO] Interrupted by user. Exiting...{RESET}")
        sys.exit(0)
