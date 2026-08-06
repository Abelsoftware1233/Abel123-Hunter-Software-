// script.js - alle frontend logica

document.addEventListener('DOMContentLoaded', function() {
    const domainInput = document.getElementById('domainInput');
    const searchBtn = document.getElementById('searchBtn');
    const emailListContainer = document.getElementById('emailListContainer');
    const emailCount = document.getElementById('emailCount');

    // --- Configuratie ---
    // VERANDER HIER HET IP-ADRES LATER
    const API_BASE_URL = 'http://127.0.0.1:5030';

    // --- Helpers ---
    function setLoading(isLoading) {
        if (isLoading) {
            searchBtn.disabled = true;
            searchBtn.innerHTML = `<span class="loader"></span> Zoeken...`;
        } else {
            searchBtn.disabled = false;
            searchBtn.innerHTML = `<i class="fas fa-arrow-right"></i> Zoek e-mails`;
        }
    }

    function renderEmails(emails) {
        if (!emails || emails.length === 0) {
            emailListContainer.innerHTML = `
                <div class="placeholder-text">
                    <i class="fas fa-inbox"></i> Geen e-mails gevonden voor dit domein
                </div>
            `;
            emailCount.textContent = '0';
            return;
        }

        let html = `<div class="email-list">`;
        emails.forEach((item) => {
            let statusClass = 'public';
            let statusLabel = 'publiek';
            if (item.status === 'predicted') {
                statusClass = 'predicted';
                statusLabel = 'patroon';
            } else if (item.status === 'verified') {
                statusClass = 'verified';
                statusLabel = 'actief ✅';
            } else if (item.status === 'public') {
                statusClass = 'public';
                statusLabel = 'gevonden';
            }

            html += `
                <div class="email-item">
                    <span class="email-addr">
                        <i class="fas fa-envelope-open-text"></i> ${item.email}
                    </span>
                    <span class="status-badge ${statusClass}">${statusLabel}</span>
                </div>
            `;
        });
        html += `</div>`;
        emailListContainer.innerHTML = html;
        emailCount.textContent = emails.length;
    }

    // --- API call ---
    async function searchEmails(domain) {
        if (!domain || domain.trim() === '') {
            alert('Voer een geldig domein in (bijv. bedrijf.nl)');
            return;
        }

        const cleanDomain = domain.trim().toLowerCase();
        setLoading(true);

        try {
            const response = await fetch(`${API_BASE_URL}/api/search`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ domain: cleanDomain }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Onbekende fout');
            }

            const data = await response.json();
            renderEmails(data.emails || []);
        } catch (error) {
            console.error('Fout bij zoeken:', error);
            emailListContainer.innerHTML = `
                <div class="placeholder-text" style="color:#c0392b;">
                    <i class="fas fa-exclamation-triangle"></i> 
                    Fout: ${error.message || 'Kan gegevens niet ophalen'}
                </div>
            `;
            emailCount.textContent = '0';
        } finally {
            setLoading(false);
        }
    }

    // --- Event listeners ---
    searchBtn.addEventListener('click', () => {
        searchEmails(domainInput.value);
    });

    // Enter to search
    domainInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            searchEmails(domainInput.value);
        }
    });
});