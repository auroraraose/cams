document.addEventListener('DOMContentLoaded', () => {
    const entityNameHeader = document.getElementById('entity-name-header');

    // Buttons
    const financialsBtn = document.getElementById('financials-btn');
    const refreshFinancialsBtn = document.getElementById('refresh-financials-btn');

    // UI State
    let isDataDirty = false; 

    // --- CONFIGURATION ---
    const BACKEND_URL = '';
    async function handleUpload(file) {
        // Show status
        const statusDiv = document.getElementById('uploadStatus');
        const statusText = statusDiv.querySelector('p');
        const progressBar = statusDiv.querySelector('.progress-bar-fill');
        const statusIcon = statusDiv.querySelector('.status-icon');

        statusDiv.style.display = 'block';
        statusText.textContent = 'Uploading Annual Report to GCS...';
        statusIcon.textContent = 'cloud_upload';
        progressBar.style.width = '30%';

        const formData = new FormData();
        formData.append('pdf_file', file);
        formData.append('company_name', companyName);
        // We can pass year if we want, but it's optional now
        // formData.append('year', yearInput.value); 

        try {
            // Step 1: Upload to GCS
            const uploadResponse = await fetch(`${BACKEND_URL}/upload-pdf/`, {
                method: 'POST',
                body: formData
            });

            const uploadResult = await uploadResponse.json();

            if (!uploadResult.success) {
                throw new Error(uploadResult.detail || uploadResult.message || 'Upload failed');
            }

            progressBar.style.width = '60%';
            statusText.textContent = 'Syncing & Extracting Data...';
            statusIcon.textContent = 'sync';
            statusIcon.classList.add('spin');

            // Step 2: Trigger Sync Extraction
            const extractFormData = new FormData();
            extractFormData.append('company_name', companyName);
            extractFormData.append('force_refresh', 'false'); // Default to false

            const extractResponse = await fetch(`${BACKEND_URL}/extract/`, {
                method: 'POST',
                body: extractFormData
            });

            const extractResult = await extractResponse.json();

            if (!extractResult.success) {
                if (extractResult.message && extractResult.message.includes("No new data")) {
                    statusText.textContent = 'Sync complete. No new data found.';
                } else {
                    throw new Error(extractResult.detail || extractResult.message || 'Extraction failed');
                }
            } else {
                statusText.textContent = 'Extraction complete! Data saved.';
            }

            statusIcon.classList.remove('spin');
            statusIcon.textContent = 'check_circle';
            progressBar.style.width = '100%';
            statusDiv.classList.add('success');

            // Wait a moment then load the data
            setTimeout(() => {
                // Refresh the year list (dynamic years)
                setupYearTabs();
                statusDiv.style.display = 'none';
                statusDiv.classList.remove('success');
                progressBar.style.width = '0%';
            }, 2000);

        } catch (error) {
            console.error('Error:', error);
            statusText.textContent = `Error: ${error.message}`;
            statusIcon.textContent = 'error';
            statusDiv.classList.add('error');
            progressBar.style.backgroundColor = '#ef4444';
        }
    }

    // -------------------

    const urlParams = new URLSearchParams(window.location.search);
    const companyName = urlParams.get('company');

    if (companyName) {
        entityNameHeader.textContent = companyName;
    }

    // --- Tab Navigation Logic ---
    function setupTabs() {
        const tabs = document.querySelectorAll('.tab-btn');
        const contents = document.querySelectorAll('.tab-content');

        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                // Deactivate all
                tabs.forEach(t => t.classList.remove('active'));
                contents.forEach(c => c.classList.remove('active'));

                // Activate clicked
                tab.classList.add('active');
                const targetId = tab.dataset.tab;
                document.getElementById(targetId).classList.add('active');

                // If CAM tab is activated and no sidebar item is active, select first default
                if (targetId === 'cam') {
                    const activeSidebar = document.querySelector('.cam-sidebar-btn.active');
                    if (!activeSidebar) {
                        // Default to Business if available, or first item
                        const firstBtn = document.querySelector('.cam-sidebar-btn');
                        if (firstBtn) firstBtn.click();
                    }
                } else if (targetId === 'documents') {
                    fetchAndRenderDocuments();
                }
            });
        });

        // Handle URL param for initial tab
        const initialTab = urlParams.get('tab');
        if (initialTab) {
            const tabBtn = document.querySelector(`.tab-btn[data-tab="${initialTab}"]`);
            if (tabBtn) tabBtn.click();
        }
    }

    // --- CAM Sidebar Logic ---
    function setupCamSidebar() {
        const sidebarBtns = document.querySelectorAll('.cam-sidebar-btn');
        const camContent = document.getElementById('cam-content'); // Updated ID
        const viewerTitle = document.getElementById('cam-viewer-title');

        sidebarBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                // Deactivate all
                sidebarBtns.forEach(b => b.classList.remove('active'));

                // Activate clicked
                btn.classList.add('active');

                const viewType = btn.dataset.view;
                const viewLabel = btn.textContent;

                viewerTitle.textContent = viewLabel;
                // Store current view type for regeneration
                camContent.dataset.currentViewType = viewType;
                loadCamView(viewType, camContent);
            });
        });
    }

    async function loadCamView(type, container) {
        if (!companyName) return;

        const UNDER_DEVELOPMENT_VIEWS = [];

        const VIEW_MAPPINGS = {
            'rating': 'rating',
            'business_analysis': 'business_analysis',
            'industry_analysis': 'industry',
            'financial_commentary': 'financial_profile',
            'non_compliance_financial': 'risk_policy',
            'earnings_call': 'earnings_call',
            'forensics': 'forensics',
            'promoter': 'promoter',
            'business': 'business_summary',
            'financial_profile_summary': 'financial_summary',
            'swot': 'swot',
            'borrower_profile': 'borrower_profile',
            'media_monitoring': 'media_monitoring'
        };

        // Handle placeholders
        if (UNDER_DEVELOPMENT_VIEWS.includes(type)) {
            container.innerHTML = `
                <div style="display: flex; justify-content: center; align-items: center; height: 100%; color: #888;">
                    <div style="text-align: center;">
                        <h3 style="color: #ccc; font-size: 2rem; margin-bottom: 1rem;">🚧</h3>
                        <h3>${type.replace(/_/g, ' ').toUpperCase()}</h3>
                        <p>This section is under development.</p>
                    </div>
                </div>
            `;
            return;
        }

        const backendType = VIEW_MAPPINGS[type] || type;
        container.innerHTML = '<div style="text-align: center; padding: 2rem; color: #666;">Loading analysis...</div>';

        try {
            const response = await fetch(`${BACKEND_URL}/view-analysis?company_name=${encodeURIComponent(companyName)}&type=${backendType}`);

            if (response.ok) {
                const text = await response.text();
                // Convert Markdown to HTML
                const converter = new showdown.Converter({
                    tables: true,
                    tasklists: true,
                    strikethrough: true,
                    simpleLineBreaks: true
                });
                const html = converter.makeHtml(text);
                container.innerHTML = html;
            } else {
                // Handle 404 or other errors (backend might return HTML or text)
                const errorText = await response.text();
                // If it looks like HTML, render it, otherwise wrap it
                if (errorText.trim().startsWith('<')) {
                    container.innerHTML = errorText;
                } else {
                    const converter = new showdown.Converter();
                    container.innerHTML = converter.makeHtml(errorText);
                }
            }
        } catch (error) {
            console.error('Error loading analysis:', error);
            container.innerHTML = `<div style="text-align: center; padding: 2rem; color: #d9534f;">Failed to load analysis: ${error.message}</div>`;
        }

        // Show Regenerate Button if valid backend type
        const regenerateBtn = document.getElementById('regenerate-section-btn');
        if (regenerateBtn) {
            regenerateBtn.style.display = 'block';
            regenerateBtn.dataset.currentType = backendType; // Store backend type mapping

            // Generate Key Mapping (UI/View Key -> Generation Key)
            const GEN_KEY_MAPPING = {
                'rating': 'credit_rating',
                'business_analysis': 'business_analysis',
                'industry_analysis': 'industry_analysis',
                'financial_commentary': 'financial_commentary',
                'non_compliance_financial': 'risk_policy',
                'earnings_call': 'earnings_call',
                'forensics': 'forensics',
                'promoter': 'promoter',
                'business': 'business_summary',
                'financial_profile_summary': 'financial_summary',
                'swot': 'swot'
            };

            regenerateBtn.dataset.sectionType = GEN_KEY_MAPPING[type] || type;
        }
    }

    // Regenerate Section Button Logic
    const regenerateSectionBtn = document.getElementById('regenerate-section-btn');
    if (regenerateSectionBtn) {
        regenerateSectionBtn.addEventListener('click', async () => {
            const sectionType = regenerateSectionBtn.dataset.sectionType;
            if (!sectionType) return;

            if (!confirm(`Are you sure you want to regenerate the ${sectionType.replace('_', ' ')} section? This will overwrite existing analysis.`)) {
                return;
            }

            regenerateSectionBtn.textContent = 'Regenerating...';
            regenerateSectionBtn.disabled = true;

            try {
                const response = await fetch(`${BACKEND_URL}/generate-section/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ company_name: companyName, section_type: sectionType })
                });

                const result = await response.json();

                if (result.success) {
                    alert(`Section ${sectionType} regenerated successfully!`);
                    // Reload the content
                    const camContent = document.getElementById('cam-content');
                    const currentViewType = camContent.dataset.currentViewType;
                    if (currentViewType) {
                        loadCamView(currentViewType, camContent);
                    }
                } else {
                    alert(`Failed to regenerate section: ${result.message}`);
                }

            } catch (error) {
                console.error('Regeneration error:', error);
                alert('An error occurred during regeneration.');
            } finally {
                regenerateSectionBtn.textContent = 'Regenerate Section';
                regenerateSectionBtn.disabled = false;
            }
        });
    }

    // --- Action Buttons Logic ---

    if (financialsBtn) {
        financialsBtn.addEventListener('click', async () => {
            financialsBtn.textContent = 'Processing...';
            financialsBtn.disabled = true;
            try {
                if (isDataDirty) {
                    await handleFinancialsUpdate();
                } else {
                    await handleFinancialsDownload();
                }
            } catch (error) {
                console.error('Error with spreadsheet:', error);
                alert('Failed to process spreadsheet.');
            } finally {
                financialsBtn.textContent = 'Generate Financials Spreadsheet';
                financialsBtn.disabled = false;
            }
        });
    }

    async function handleFinancialsUpdate() {
        const extractedDataContainer = document.getElementById('extracted-data-container');
        const tableRows = extractedDataContainer.querySelectorAll('tbody tr');
        const headers = Array.from(extractedDataContainer.querySelectorAll('thead th')).slice(1).map(th => th.textContent);
        const updatedData = {};

        tableRows.forEach(row => {
            const key = row.cells[0].textContent;
            Array.from(row.cells).slice(1).forEach((cell, i) => {
                const year = headers[i];
                const value = cell.querySelector('input').value;
                const dataPoint = { value: value, year: year };

                const tooltip = cell.querySelector('.tooltip-text');
                if (tooltip) {
                    const html = tooltip.innerHTML;
                    const unitMatch = html.match(/<strong>Unit:<\/strong> (.*?)(<br>|$)/);
                    if (unitMatch) dataPoint.unitOfMeasure = unitMatch[1];
                }

                if (!updatedData[year]) updatedData[year] = {};
                updatedData[year][key] = [dataPoint];
            });
        });

        const response = await fetch(`${BACKEND_URL}/generate-and-download-spreadsheet/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ company_name: companyName, updated_data: updatedData })
        });

        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const blob = await response.blob();
        saveAs(blob, `${companyName}_financials.xlsx`);
        isDataDirty = false;
    }

    async function handleFinancialsDownload() {
        const response = await fetch(`${BACKEND_URL}/download-spreadsheet/?company_name=${companyName}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const blob = await response.blob();
        saveAs(blob, `${companyName}_financials.xlsx`);
    }

    // --- Document Wrappers ---
    // Make sure downloadDocument is global
    window.downloadDocument = async (folder, filename) => {
        try {
            const response = await fetch(`${BACKEND_URL}/download-document/?company_name=${encodeURIComponent(companyName)}&folder=${encodeURIComponent(folder)}&filename=${encodeURIComponent(filename)}`);
            if (!response.ok) throw new Error('Download failed');

            const blob = await response.blob();
            saveAs(blob, filename);
        } catch (error) {
            console.error('Download error:', error);
            alert('Failed to download document.');
        }
    };

    // Generate CAM Button (Full Run)
    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) {
        generateBtn.addEventListener('click', async () => {
            if (!confirm("Are you sure you want to run the entire pipeline? This may take a few minutes.")) {
                return;
            }

            generateBtn.textContent = 'Processing...';
            generateBtn.disabled = true;

            try {
            // Call generate-and-download-credit-memo
            // Note: The endpoint expects a POST with GenerateSheetRequest structure if using updated data,
            // or we can pass empty updated_data if just regenerating.
            // The backend implementation:
            // class GenerateSheetRequest(BaseModel):
            //     company_name: str
            //     updated_data: Dict[str, Any] = {}

                const response = await fetch(`${BACKEND_URL}/generate-and-download-credit-memo/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ company_name: companyName, updated_data: {} }) 
                });

                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                
                const blob = await response.blob();
                saveAs(blob, `${companyName}_credit_memo.docx`);
                alert("CAM Generated and Downloaded Successfully!");

            } catch (error) {
                console.error('Error generating CAM:', error);
                alert('Failed to generate CAM.');
            } finally {
                generateBtn.textContent = 'Generate CAM';
                generateBtn.disabled = false;
            }
        });
    }

    // Refresh Memo Button (Assemble Only)
    const refreshMemoBtn = document.getElementById('refresh-memo-btn');
    if (refreshMemoBtn) {
        refreshMemoBtn.addEventListener('click', async () => {
            refreshMemoBtn.textContent = 'Assembling...';
            refreshMemoBtn.disabled = true;
            try {
                // 1. Assemble
                const assembleResponse = await fetch(`${BACKEND_URL}/assemble-memo/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ company_name: companyName })
                });

                const assembleResult = await assembleResponse.json();

                if (assembleResult.success) {
                    // 2. Auto Download on Success
                    refreshMemoBtn.textContent = 'Downloading...';
                    const downloadResponse = await fetch(`${BACKEND_URL}/download-credit-memo/?company_name=${encodeURIComponent(companyName)}`);
                    if (!downloadResponse.ok) throw new Error('Download failed after assembly');

                    const blob = await downloadResponse.blob();
                    saveAs(blob, `${companyName}_credit_memo.docx`);
                    alert('Credit Memo Refresh Complete!');
                } else {
                    alert('Assembly failed: ' + assembleResult.message);
                }
            } catch (error) {
                console.error('Refresh error:', error);
                alert('Failed to refresh memo.');
            } finally {
                refreshMemoBtn.textContent = 'Refresh Memo (Assemble)';
                refreshMemoBtn.disabled = false;
            }
        });
    }

    if (refreshFinancialsBtn) {
        refreshFinancialsBtn.addEventListener('click', () => {
            fetchAndRenderExtractedData();
        });
    }


    // --- Financials Table Logic ---
    async function fetchAndRenderExtractedData() {
        const extractedDataContainer = document.getElementById('extracted-data-container');

        if (!extractedDataContainer) return; // Guard clause if element doesn't exist (e.g. simplified layouts)

        extractedDataContainer.innerHTML = '<div style="text-align:center; padding: 2rem; color: #666;">Loading extracted data...</div>';

        try {
            const response = await fetch(`${BACKEND_URL}/load-all-data/?company_name=${companyName}`);
            if (!response.ok) {
                if (response.status === 404) {
                    extractedDataContainer.innerHTML = '<div style="text-align:center; padding: 2rem;">No extracted data found for this entity. Please generate financials first.</div>';
                    return;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const result = await response.json();
            renderExtractedDataTable(result.data, extractedDataContainer, true); 
            
            // Track changes
            extractedDataContainer.addEventListener('input', () => {
                isDataDirty = true;
            });

        } catch (error) {
            console.error('Error fetching extracted data:', error);
            extractedDataContainer.innerHTML = `<div style="text-align:center; padding: 2rem; color: red;">Could not load extracted data: ${error.message}</div>`;
        }
    }

    // --- Documents Logic ---
    async function fetchAndRenderDocuments() {
        const tbody = document.getElementById('documents-table-body');
        if (!tbody) return;

        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 2rem; color: #666;">Loading documents...</td></tr>';

        try {
            const response = await fetch(`${BACKEND_URL}/list-all-documents/?company_name=${encodeURIComponent(companyName)}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const result = await response.json();
            const documents = result.documents;

            tbody.innerHTML = '';

            if (documents.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 2rem; color: #666;">No documents found.</td></tr>';
                return;
            }

            documents.forEach(doc => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <span style="font-size: 1.2rem; color: #666;">📄</span>
                            <span>${doc.name}</span>
                        </div>
                    </td>
                    <td>${doc.type}</td>
                    <td>${doc.upload_date}</td>
                    <td>
                        <span style="background: #e6f4ea; color: #1e7e34; padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">
                            ${doc.status}
                        </span>
                    </td>
                    <td>
                        <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.8rem;" onclick="downloadDocument('${doc.folder}', '${doc.filename}')">
                            Download
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            console.log('Documents rendered.');

        } catch (error) {
            console.error('Error fetching documents:', error);
            // alert(`Error loading documents: ${error.message}`); // Optional: alert for visibility
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 2rem; color: #d9534f;">Failed to load documents: ${error.message}</td></tr>`;
        }
    }

    // Expose download function globally so inline onclick works
    window.downloadDocument = async (folder, filename) => {
        try {
            const response = await fetch(`${BACKEND_URL}/download-document/?company_name=${encodeURIComponent(companyName)}&folder=${encodeURIComponent(folder)}&filename=${encodeURIComponent(filename)}`);
            if (!response.ok) throw new Error('Download failed');

            const blob = await response.blob();
            saveAs(blob, filename);
        } catch (error) {
            console.error('Download error:', error);
            alert('Failed to download document.');
        }
    };

    // Initialize
    setupTabs();
    setupCamSidebar();

    // Auto-load financials
    fetchAndRenderExtractedData();
});
