# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import re
import random
import smtplib
import dns.resolver
from typing import List, Dict, Optional

app = Flask(__name__)
CORS(app)  # voor cross-origin tijdens ontwikkeling

# -------------------------------
# 1. WEB CRAWLING (simulatie)
# -------------------------------
def crawl_public_emails(domain: str) -> List[str]:
    """
    Simuleert het crawlen van publieke webpagina's.
    In werkelijkheid zou je requests + BeautifulSoup gebruiken.
    Nu genereren we 'gevonden' adressen op basis van het domein.
    """
    # Basis set van veelvoorkomende publieke e-mails
    common_public = [
        f"info@{domain}",
        f"contact@{domain}",
        f"support@{domain}",
        f"sales@{domain}",
        f"admin@{domain}",
    ]
    # Random selectie (niet allemaal, alsof ze niet allemaal gevonden worden)
    count = random.randint(1, 3)
    return random.sample(common_public, min(count, len(common_public)))

# -------------------------------
# 2. PATROONHERKENNING
# -------------------------------
def derive_pattern(domain: str, known_emails: List[str]) -> Optional[str]:
    """
    Bepaalt op basis van bekende e-mails het patroon.
    Simulatie: we kijken of er een punt of underscore in zit.
    """
    if not known_emails:
        return None

    # Neem de eerste e-mail als voorbeeld
    sample = known_emails[0]
    local_part = sample.split('@')[0]

    if '.' in local_part:
        return 'firstname.lastname'
    elif '_' in local_part:
        return 'firstname_lastname'
    elif local_part.islower() and len(local_part) < 10:
        return 'firstname'
    else:
        return 'firstname.lastname'  # default

def generate_predicted_emails(domain: str, names: List[str], pattern: str) -> List[str]:
    """
    Genereer e-mails op basis van een patroon en een lijst van namen.
    """
    predicted = []
    for full_name in names:
        parts = full_name.lower().strip().split()
        if len(parts) < 2:
            continue
        first = parts[0]
        last = parts[-1]

        if pattern == 'firstname.lastname':
            email = f"{first}.{last}@{domain}"
        elif pattern == 'firstname_lastname':
            email = f"{first}_{last}@{domain}"
        elif pattern == 'firstname':
            email = f"{first}@{domain}"
        elif pattern == 'lastname.firstname':
            email = f"{last}.{first}@{domain}"
        else:
            email = f"{first}.{last}@{domain}"
        predicted.append(email)
    return predicted

# -------------------------------
# 3. SMTP-VERIFICATIE (simulatie)
# -------------------------------
def verify_email_smtp(email: str) -> bool:
    """
    Simuleert SMTP-verificatie (zonder echt te verbinden).
    In werkelijkheid: VRFY of RCPT TO + HELO.
    Nu geven we willekeurig true/false, maar met hoge kans true voor validatie.
    """
    # In de echte wereld: check MX-record, verbind met SMTP, etc.
    # Hier simuleren we: 85% kans dat een 'goed' formaat adres als actief wordt beschouwd.
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return random.random() < 0.85
    return False

# -------------------------------
# 4. PUBLIEKE BRONNEN (LinkedIn, registers)
# -------------------------------
def fetch_names_from_public_sources(domain: str) -> List[str]:
    """
    Simuleert ophalen van namen via LinkedIn, KVK, etc.
    Retourneert lijst van 'voornaam achternaam'.
    """
    # Voorbeeld namen per domein (statisch voor demo)
    sample_names = {
        'example.com': ['Jane Doe', 'John Smith', 'Alice Johnson', 'Bob Williams'],
        'bedrijf.nl': ['Annie de Vries', 'Bas van Dijk', 'Charlotte Jansen', 'Daan Bakker'],
        'techcorp.io': ['Eva Chen', 'Finn O'Brien', 'Grace Lee', 'Henry Adams'],
        'default': ['Alex de Groot', 'Sanne Post', 'Tim van der Meer', 'Lisa Willems']
    }
    return sample_names.get(domain, sample_names['default'])

# -------------------------------
# 5. HOOFDFUNCTIE: zoek e-mails
# -------------------------------
def find_emails_for_domain(domain: str) -> List[Dict[str, str]]:
    """
    Integreert alle stappen:
    1. Crawl publieke e-mails
    2. Haal namen op uit publieke bronnen
    3. Leid patroon af op basis van gevonden e-mails
    4. Genereer voorspelde e-mails
    5. Verifieer (simuleer SMTP)
    6. Combineer en tag status
    """
    if not domain or not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain):
        return []

    # Stap 1: crawlen
    public_emails = crawl_public_emails(domain)

    # Stap 2: namen uit publieke bronnen
    names = fetch_names_from_public_sources(domain)

    # Stap 3: patroon afleiden (op basis van publieke e-mails)
    pattern = derive_pattern(domain, public_emails)
    predicted_emails = []
    if pattern and names:
        predicted_emails = generate_predicted_emails(domain, names, pattern)

    # Combineer, remove duplicates, behoud volgorde
    all_emails_set = set(public_emails)
    unique_predicted = [e for e in predicted_emails if e not in all_emails_set]
    all_emails = public_emails + unique_predicted

    # Stap 5: SMTP-verificatie (simulatie) en opmaken resultaat
    result = []
    for email in all_emails:
        # Bepaal status
        if email in public_emails:
            status = 'public'
        else:
            status = 'predicted'

        # Simuleer SMTP-check (alleen voor predicted of public, random)
        # We doen het voor allemaal, maar voor public laten we het vaak verified zijn
        if status == 'public':
            # 80% kans dat publieke adressen als actief worden gezien
            is_verified = random.random() < 0.8
        else:
            is_verified = verify_email_smtp(email)

        if is_verified:
            status = 'verified'  # overschrijf naar verified

        result.append({
            'email': email,
            'status': status,
        })

    # Sorteer: verified eerst, dan public, dan predicted
    status_order = {'verified': 0, 'public': 1, 'predicted': 2}
    result.sort(key=lambda x: status_order.get(x['status'], 3))

    return result

# -------------------------------
# 6. FLASK ENDPOINT
# -------------------------------
@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json()
    if not data or 'domain' not in data:
        return jsonify({'error': 'Geen domein opgegeven'}), 400

    domain = data['domain'].strip().lower()
    if not domain:
        return jsonify({'error': 'Domein mag niet leeg zijn'}), 400

    # Eenvoudige validatie
    if not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain):
        return jsonify({'error': 'Ongeldig domeinformaat'}), 400

    emails = find_emails_for_domain(domain)
    return jsonify({'emails': emails})

# -------------------------------
# 7. START
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5030)