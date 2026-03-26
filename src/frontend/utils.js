function renderExtractedDataTable(data, container, isEditable = false) {
    const table = document.createElement('table');
    table.className = 'company-table financial-table'; 

    // 1. Sort Years
    let years = Object.keys(data);
    years.sort((a, b) => {
        const numA = parseInt(a.replace(/\D/g, '') || 0);
        const numB = parseInt(b.replace(/\D/g, '') || 0);
        if (numA !== numB) return numA - numB;
        return a.localeCompare(b);
    });

    const headers = ['Metric', ...years];
    
    // 2. Get All Metrics
    let allKeys = new Set();
    try {
        Object.values(data).forEach(yearData => {
            const keys = yearData.extracted_data ? Object.keys(yearData.extracted_data) : Object.keys(yearData);
            keys.forEach(key => allKeys.add(key));
        });
    } catch (e) { console.error("Error parsing keys", e); }

    // 3. Build Header
    let tableHTML = `<thead><tr>${headers.map((h, i) => 
        `<th style="${i===0 ? 'text-align:left; width: 250px;' : 'text-align:right; color:#6b7280; font-size:0.75rem; letter-spacing:0.05em;'}">${h}</th>`
    ).join('')}</tr></thead><tbody>`;
    
    const sortedKeys = Array.from(allKeys);

    // 4. Build Rows
    sortedKeys.forEach(key => {
        // Metric Name
        tableHTML += `<tr><td style="font-weight:600; color:#1f2937; font-size:0.9rem;">${key}</td>`;
        
        years.forEach(year => {
            const yearData = data[year] ? (data[year].extracted_data || data[year]) : null;
            const dataPoint = yearData && yearData[key] ? yearData[key][0] : {};

            const value = dataPoint ? String(dataPoint.value || '') : '';
            const unit = dataPoint.unitOfMeasure ? dataPoint.unitOfMeasure : '';

            // --- Tooltip Logic ---
            let tooltipHTML = '';
            const hasMetadata = dataPoint.citation_page || dataPoint.citation_table || dataPoint.citation_notes;
            
            // Only render the icon wrapper if we have data to show
            if (hasMetadata) {
                tooltipHTML = `
                    <div style="position:relative;">
                        <div class="info-icon">i</div>
                        <div class="hover-tooltip">
                            ${dataPoint.citation_table ? `
                                <div class="tooltip-row">
                                    <span class="tooltip-label">Source Table</span>
                                    ${dataPoint.citation_table}
                                </div>` : ''}
                            
                            ${dataPoint.citation_page ? `
                                <div class="tooltip-row">
                                    <span class="tooltip-label">Location</span>
                                    Page ${dataPoint.citation_page}
                                </div>` : ''}

                            ${dataPoint.citation_notes ? `
                                <div class="tooltip-row">
                                    <span class="tooltip-label">Logic</span>
                                    ${dataPoint.citation_notes}
                                </div>` : ''}
                        </div>
                    </div>
                `;
            } else {
                 // Placeholder invisible icon to keep alignment if needed, or just empty
                 tooltipHTML = `<div style="width:16px;"></div>`; 
            }

            // --- Input Logic ---
            // CRITICAL: Added 'readonly' attribute to prevent editing
            const inputHTML = `<input type="text" class="clean-input" value="${value}" readonly tabIndex="-1">`;

            tableHTML += `
                <td>
                    <div class="data-cell-wrapper">
                        ${unit ? `<span class="data-unit">${unit}</span>` : ''}
                        ${inputHTML}
                        ${tooltipHTML}
                    </div>
                </td>`;
        });
        tableHTML += `</tr>`;
    });

    tableHTML += `</tbody>`;
    table.innerHTML = tableHTML;
    container.innerHTML = '';
    container.appendChild(table);
}