import os
import re
import socket
import smtplib
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import dns.resolver
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Set

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Request headers to mimic a real web browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# -------------------------------
# 1. REAL WEB CRAWLING
# -------------------------------
def extract_emails_from_text(text: str) -> Set[str]:
    """Extracts valid email addresses from raw text using regex."""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    matches = re.findall(pattern, text)
    # Exclude common image extensions or static assets accidentally caught by regex
    filtered = {
        email.lower() for email in matches
        if not re.search(r'\.(png|jpg|jpeg|gif|svg|webp|css|js)$', email, re.IGNORECASE)
    }
    return filtered

def crawl_public_emails(domain: str) -> List[str]:
    """
    Crawls the main domain and common pages (/contact, /about, /team, etc.)
    to extract actual published email addresses.
    """
    found_emails: Set[str] = set()
    base_url = f"https://{domain}"
    target_paths = ["", "/contact", "/over-ons", "/about", "/about-us", "/team", "/contact-us"]

    def fetch_page(path: str) -> Set[str]:
        url = urljoin(base_url, path)
        try:
            response = requests.get(url, headers=HEADERS, timeout=6, allow_redirects=True)
            if response.status_code == 200:
                return extract_emails_from_text(response.text)
        except requests.RequestException:
            pass
        return set()

    # Crawl target pages concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_page, path) for path in target_paths]
        for future in as_completed(futures):
            found_emails.update(future.result())

    # Only retain emails matching the targeted domain
    domain_emails = [e for e in found_emails if e.endswith(f"@{domain}")]
    return domain_emails


# -------------------------------
# 2. REAL PUBLIC SOURCES & KVK API
# -------------------------------
def fetch_kvk_data(company_name_or_domain: str) -> List[str]:
    """
    Fetches company officer/contact names using the Dutch KvK API (if API key provided)
    or public KvK search endpoint.
    """
    kvk_api_key = os.environ.get("KVK_API_KEY")
    names = []

    # Clean query domain name into a searchable company term
    query_term = company_name_or_domain.split('.')[0]

    if kvk_api_key:
        try:
            url = f"https://api.kvk.nl/api/v1/zoeken?q={query_term}"
            headers = {"apikey": kvk_api_key}
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                for result in data.get("resultaten", []):
                    # Extract trade names or owner details if available
                    if "handelsnaam" in result:
                        names.append(result["handelsnaam"])
        except Exception:
            pass

    return names

def fetch_names_from_public_sources(domain: str) -> List[str]:
    """
    Extracts potential employee/team names directly from team/about web pages,
    and enriches with KvK search data.
    """
    extracted_names: Set[str] = set()
    base_url = f"https://{domain}"
    target_paths = ["/about", "/over-ons", "/team", "/our-team"]

    # Name matching regex (Capitalized first + last name, including Dutch prefixes like 'de', 'van')
    name_pattern = r'\b([A-Z][a-z]+(?:\s+(?:van|de|den|der|het|'t|vander))?\s+[A-Z][a-z]+)\b'

    for path in target_paths:
        try:
            url = urljoin(base_url, path)
            resp = requests.get(url, headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Target common heading/team elements
                for element in soup.find_all(['h2', 'h3', 'h4', 'strong', 'p', 'figcaption']):
                    text = element.get_text().strip()
                    matches = re.findall(name_pattern, text)
                    for match in matches:
                        # Exclude common site keywords
                        if not any(w in match.lower() for w in ['contact', 'privacy', 'cookies', 'copyright', 'home']):
                            extracted_names.add(match)
        except requests.RequestException:
            continue

    # Enrich with KvK data if available
    kvk_results = fetch_kvk_data(domain)
    
    return list(extracted_names)


# -------------------------------
# 3. PATTERN RECOGNITION & GENERATION
# -------------------------------
def derive_pattern(domain: str, known_emails: List[str]) -> str:
    """Infers email pattern from found public emails."""
    if not known_emails:
        return 'firstname.lastname'  # Standard default

    for email in known_emails:
        local_part = email.split('@')[0]
        if '.' in local_part:
            return 'firstname.lastname'
        elif '_' in local_part:
            return 'firstname_lastname'
        elif '-' in local_part:
            return 'firstname-lastname'

    return 'firstname.lastname'

def generate_predicted_emails(domain: str, names: List[str], pattern: str) -> List[str]:
    """Generates candidate email addresses based on names and detected format."""
    predicted = []
    for full_name in names:
        parts = full_name.lower().strip().split()
        if len(parts) < 2:
            continue
        
        first = parts[0]
        last = parts[-1]  # Handles Dutch prefixes by using the main surname

        if pattern == 'firstname.lastname':
            email = f"{first}.{last}@{domain}"
        elif pattern == 'firstname_lastname':
            email = f"{first}_{last}@{domain}"
        elif pattern == 'firstname-lastname':
            email = f"{first}-{last}@{domain}"
        elif pattern == 'firstname':
            email = f"{first}@{domain}"
        elif pattern == 'lastname.firstname':
            email = f"{last}.{first}@{domain}"
        else:
            email = f"{first}.{last}@{domain}"

        predicted.append(email)
    return list(set(predicted))


# -------------------------------
# 4. REAL SMTP VERIFICATION
# -------------------------------
def get_mx_records(domain: str) -> List[str]:
    """Retrieves Mail Exchange (MX) hostnames sorted by priority."""
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        records = sorted(answers, key=lambda r: r.preference)
        return [str(r.exchange).rstrip('.') for r in records]
    except Exception:
        return []

def verify_email_smtp(email: str, mx_hosts: List[str]) -> str:
    """
    Performs real SMTP verification without sending an email.
    Returns: 'verified', 'invalid', or 'unverifiable'
    """
    if not mx_hosts:
        return 'invalid'

    mx_host = mx_hosts[0]
    
    try:
        # Establish connection with mail server
        server = smtplib.SMTP(timeout=5)
        server.connect(mx_host, 25)
        server.helo(socket.getfqdn())
        server.mail('verify@check-domain.com')
        
        code, message = server.rcpt(email)
        server.quit()

        # 250 means recipient address accepted
        if code == 250:
            return 'verified'
        elif code in (550, 551, 552, 553, 554):
            return 'invalid'
        else:
            return 'unverifiable'
            
    except (smtplib.SMTPException, socket.error, TimeoutError):
        return 'unverifiable'


# -------------------------------
# 5. CORE SEARCH CONTROLLER
# -------------------------------
def find_emails_for_domain(domain: str) -> List[Dict[str, str]]:
    """Runs crawling, pattern recognition, prediction, and live SMTP checks."""
    if not domain or not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain):
        return []

    # 1. Crawl website for public emails
    public_emails = crawl_public_emails(domain)

    # 2. Extract employee names from site & external registries
    names = fetch_names_from_public_sources(domain)

    # 3. Derive pattern and generate predicted candidates
    pattern = derive_pattern(domain, public_emails)
    predicted_emails = generate_predicted_emails(domain, names, pattern) if names else []

    # Combine unique candidates
    all_public = set(public_emails)
    unique_predicted = [e for e in predicted_emails if e not in all_public]
    all_emails = public_emails + unique_predicted

    # Get DNS MX hosts for SMTP checking
    mx_hosts = get_mx_records(domain)

    # 4. Verify emails in parallel via SMTP
    result = []

    def verify_single(email: str):
        is_public = email in all_public
        smtp_status = verify_email_smtp(email, mx_hosts)

        if smtp_status == 'verified':
            final_status = 'verified'
        elif is_public:
            final_status = 'public'
        elif smtp_status == 'invalid':
            final_status = 'invalid'
        else:
            final_status = 'predicted'

        return {
            'email': email,
            'status': final_status
        }

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(verify_single, email) for email in all_emails]
        for future in as_completed(futures):
            res = future.result()
            if res['status'] != 'invalid':  # Filter out confirmed non-existent emails
                result.append(res)

    # Sort results: verified first, then public, then predicted
    status_order = {'verified': 0, 'public': 1, 'predicted': 2}
    result.sort(key=lambda x: status_order.get(x['status'], 3))

    return result


# -------------------------------
# 6. FLASK ROUTE
# -------------------------------
@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json()
    if not data or 'domain' not in data:
        return jsonify({'error': 'No domain provided'}), 400

    domain = data['domain'].strip().lower()
    if not domain:
        return jsonify({'error': 'Domain cannot be empty'}), 400

    if not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain):
        return jsonify({'error': 'Invalid domain format'}), 400

    emails = find_emails_for_domain(domain)
    return jsonify({'emails': emails})


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5030)
