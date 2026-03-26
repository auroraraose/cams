document.addEventListener('DOMContentLoaded', () => {
    const addEntityBtn = document.getElementById('add-entity-btn');
    const companyListContainer = document.getElementById('company-list-container');
    const BACKEND_URL = ''; // Add your backend URL here if needed

    if(addEntityBtn) {
        addEntityBtn.addEventListener('click', () => {
            window.location.href = 'new-entity.html';
        });
    }

    async function fetchCompanies() {
        try {
            const response = await fetch(`${BACKEND_URL}/companies`);
            if (!response.ok) {
                console.warn("Backend unavailable, using mock data.");
                const mockData = generateMockData();
                updateDashboardStats(mockData);
                renderCompanyTable(mockData);
                return;
            }
            const companiesByIndustry = await response.json();
            const allCompanies = flattenCompanies(companiesByIndustry);
            
            // Enrich with visual data
            const enrichedCompanies = enrichDataForDashboard(allCompanies);

            updateDashboardStats(enrichedCompanies);
            renderCompanyTable(enrichedCompanies);

        } catch (error) {
            console.error('Error fetching companies:', error);
            const mockData = generateMockData();
            updateDashboardStats(mockData);
            renderCompanyTable(mockData);
        }
    }

    // --- Stats Updater ---
    function updateDashboardStats(companies) {
        const totalElement = document.getElementById('total-applications');
        if (totalElement) totalElement.textContent = companies.length;

        const pendingCount = companies.filter(c => 
            c.status === 'Risk Review' || c.status === 'Committee Review' || c.status === 'Draft'
        ).length;
        const pendingElement = document.getElementById('pending-review');
        if (pendingElement) pendingElement.textContent = pendingCount;

        const approvedCount = companies.filter(c => c.status === 'Approved').length;
        const approvedElement = document.getElementById('approved-mtd');
        if (approvedElement) approvedElement.textContent = approvedCount;
    }

    // --- Table Renderer (Modified: No Amount/Risk, Added Delete) ---
    function renderCompanyTable(companies) {
        companyListContainer.innerHTML = ''; 

        if (companies.length === 0) {
            companyListContainer.innerHTML = '<div style="padding: 2rem; text-align: center; color: #9ca3af;">No applications found.</div>';
            return;
        }

        const tableContainer = document.createElement('div');
        const table = document.createElement('table');
        table.className = 'company-table';
        
        // HEADERS: Removed Amount & Risk Rating
        table.innerHTML = `
            <thead>
                <tr>
                    <th style="width: 15%;">Application ID</th>
                    <th style="width: 40%;">Customer</th>
                    <th style="width: 20%;">Date</th>
                    <th style="width: 15%;">Status</th>
                    <th style="width: 10%; text-align: right;">Action</th>
                </tr>
            </thead>
            <tbody></tbody>
        `;

        const tbody = table.querySelector('tbody');

        companies.forEach(company => {
            const tr = document.createElement('tr');
            
            let badgeClass = 'draft';
            if(company.status === 'Risk Review') badgeClass = 'risk-review';
            if(company.status === 'Approved') badgeClass = 'approved';
            if(company.status === 'Rejected') badgeClass = 'rejected';
            if(company.status === 'Committee Review') badgeClass = 'committee';

            // ROWS: No Amount/Risk Data. Added Delete Button.
            tr.innerHTML = `
                <td class="td-id">${company.id || '-'}</td>
                <td>
                    <span class="customer-name">${company.name}</span>
                    <span class="customer-industry">${company.industry}</span>
                </td>
                <td style="color: #6b7280;">${company.date || '-'}</td>
                <td><span class="badge ${badgeClass}">${company.status || 'Draft'}</span></td>
                <td style="text-align: right;">
                    <div style="display: flex; align-items: center; justify-content: flex-end; gap: 8px;">
                        <a href="#" class="view-link">View</a>
                        
                        <button class="btn-trash" title="Delete Application">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                <line x1="10" y1="11" x2="10" y2="17"></line>
                                <line x1="14" y1="11" x2="14" y2="17"></line>
                            </svg>
                        </button>
                    </div>
                </td>
            `;

            // View Click
            tr.querySelector('.view-link').addEventListener('click', (e) => {
                e.preventDefault();
                window.location.href = `entity.html?company=${encodeURIComponent(company.name)}`;
            });

            // Delete Click
            tr.querySelector('.btn-trash').addEventListener('click', (e) => {
                e.stopPropagation(); 
                if (confirm(`Are you sure you want to delete ${company.name}?`)) {
                    // Visual removal logic
                    tr.style.transition = "opacity 0.3s";
                    tr.style.opacity = '0'; 
                    setTimeout(() => tr.remove(), 300); 
                    
                    // Update stats counter locally
                    const totalEl = document.getElementById('total-applications');
                    if(totalEl) totalEl.textContent = Math.max(0, parseInt(totalEl.textContent) - 1);
                }
            });

            tbody.appendChild(tr);
        });

        tableContainer.appendChild(table);
        companyListContainer.appendChild(tableContainer);
    }

    // --- Helpers ---
    function flattenCompanies(companiesByIndustry) {
        let allCompanies = [];
        for (const industry in companiesByIndustry) {
            companiesByIndustry[industry].forEach(company => {
                allCompanies.push({
                    name: company.name,
                    industry: industry,
                    entity_type: company.entity_type || 'Unknown' 
                });
            });
        }
        return allCompanies;
    }

    function enrichDataForDashboard(companies) {
        return companies.map((comp, index) => ({
            ...comp,
            id: `APP-2024-${String(index + 1).padStart(3, '0')}`,
            date: new Date().toISOString().split('T')[0],
            status: getRandomStatus(), 
            // Note: amount and risk removed from logic since not displayed
        }));
    }

    function getRandomStatus() {
        const statuses = ['Draft', 'Risk Review', 'Approved', 'Rejected', 'Committee Review'];
        return statuses[Math.floor(Math.random() * statuses.length)];
    }

    function generateMockData() {
        return [
            { name: "TechSolutions India Pvt Ltd", industry: "IT Services", entity_type: "Private Limited", id: "APP-2024-001", date: "2024-03-10", status: "Draft" },
            { name: "Patel Textiles", industry: "Manufacturing", entity_type: "Proprietorship", id: "APP-2024-002", date: "2024-03-08", status: "Risk Review" },
            { name: "Desai Organic Foods", industry: "FMCG", entity_type: "LLP", id: "APP-2024-003", date: "2024-03-05", status: "Approved" }
        ];
    }

    // Initial Load
    fetchCompanies();
});