document.addEventListener('DOMContentLoaded', () => {
    const extractDataBtn = document.getElementById('extract-data-btn');
    const entityNameInput = document.getElementById('entity-name');
    const industryInput = document.getElementById('industry');
    const documentUpload = document.getElementById('document-upload');
    const uploadedFilesTableBody = document.querySelector('#uploaded-files-table tbody');
    const uploadContainer = document.getElementById('upload-container');
    const dataExtractionSection = document.getElementById('data-extraction-section');
    const extractedDataContainer = document.getElementById('extracted-data-container');
    const generateSpreadsheetBtn = document.getElementById('generate-spreadsheet-btn');

    // Field References
    const entityTypeInput = document.getElementById('entity-type');
    const listedEntityInput = document.getElementById('listed-entity');
    const cinIdInput = document.getElementById('cin-id');
    const keyContactInput = document.getElementById('key-contact');
    const creditAnalystInput = document.getElementById('credit-analyst');

    const BACKEND_URL = '';
    let uploadedFiles = [];

    // Facility Table Logic
    function setupFacilityTable() {
        const table = document.getElementById('facility-details-table');
        if (!table) return;

        const inputs = table.querySelectorAll('.facility-input');

        inputs.forEach(input => {
            input.addEventListener('input', () => {
                recalculateFacilityTable();
            });
        });

        // Initial Calc
        recalculateFacilityTable();
    }

    function recalculateFacilityTable() {
        // defined rows logic
        const getVal = (row, col) => {
            const el = document.querySelector(`.facility-input[data-row="${row}"][data-col="${col}"]`);
            return el ? (parseFloat(el.value) || 0) : 0;
        };

        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val.toFixed(2); // Format to 2 decimal places
        };

        const setNetChange = (row, val) => {
            const el = document.querySelector(`.calc-net-change[data-row="${row}"]`);
            if (el) el.textContent = val.toFixed(2);
        };

        // Rows: secured, unsecured, other
        // Cols: existing, proposed, outstanding, irregularity

        const rows = ['secured', 'unsecured', 'other'];
        let totals = { existing: 0, proposed: 0, netChange: 0, outstanding: 0, irregularity: 0 };
        let grandTotals = { existing: 0, proposed: 0, netChange: 0, outstanding: 0, irregularity: 0 };

        // Process Secured & Unsecured for "Total Credit Exposure"
        ['secured', 'unsecured'].forEach(rowKey => {
            const existing = getVal(rowKey, 'existing');
            const proposed = getVal(rowKey, 'proposed');
            const outstanding = getVal(rowKey, 'outstanding');
            const irregularity = getVal(rowKey, 'irregularity');
            const netChange = proposed - existing;

            setNetChange(rowKey, netChange);

            totals.existing += existing;
            totals.proposed += proposed;
            totals.netChange += netChange;
            totals.outstanding += outstanding;
            totals.irregularity += irregularity;
        });

        // Set Total Credit Exposure Row
        setVal('total-existing', totals.existing);
        setVal('total-proposed', totals.proposed);
        setVal('total-net-change', totals.netChange);
        setVal('total-outstanding', totals.outstanding);
        setVal('total-irregularity', totals.irregularity);

        // Process "Other" and add to Grand Totals (Sanctioned Limit)
        // Assumption: Total Sanctioned Limit = Total Credit Exposure + Other Limits
        grandTotals = { ...totals };

        const otherExisting = getVal('other', 'existing');
        const otherProposed = getVal('other', 'proposed');
        const otherOutstanding = getVal('other', 'outstanding');
        const otherIrregularity = getVal('other', 'irregularity');
        const otherNetChange = otherProposed - otherExisting;

        setNetChange('other', otherNetChange);

        grandTotals.existing += otherExisting;
        grandTotals.proposed += otherProposed;
        grandTotals.netChange += otherNetChange;
        grandTotals.outstanding += otherOutstanding;
        grandTotals.irregularity += otherIrregularity;

        // Set Total Sanctioned Limit Row
        setVal('grand-total-existing', grandTotals.existing);
        setVal('grand-total-proposed', grandTotals.proposed);
        setVal('grand-total-net-change', grandTotals.netChange);
        setVal('grand-total-outstanding', grandTotals.outstanding);
        setVal('grand-total-irregularity', grandTotals.irregularity);
    }

    // Call setup
    setupFacilityTable();

    documentUpload.addEventListener('change', () => {
        const files = documentUpload.files;
        for (const file of files) {
            const { type, year } = classifyFile(file.name);
            uploadedFiles.push({ file, type, year });
        }
        renderUploadedFiles();
    });

    function classifyFile(filename) {
        let type = 'Other';
        if (/annual-report/i.test(filename)) {
            type = 'Annual Report';
        } else if (/annual return/i.test(filename)) {
            type = 'Annual Return';
        } else if (/shareholding pattern/i.test(filename)) {
            type = 'Shareholding Pattern';
        }

        const yearMatch = filename.match(/(20\d{2})/);
        const year = yearMatch ? parseInt(yearMatch[0]) : new Date().getFullYear();

        return { type, year };
    }

    function renderUploadedFiles() {
        uploadedFilesTableBody.innerHTML = '';
        uploadedFiles.forEach((fileData, index) => {
            const row = document.createElement('tr');
            
            const fileTypes = ['Annual Report', 'Annual Return', 'Shareholding Pattern', 'Detail Financial Report', 'Earnings Call Recording', 'Other'];
            const typeOptions = fileTypes.map(t => `<option value="${t}" ${t === fileData.type ? 'selected' : ''}>${t}</option>`).join('');

            const currentYear = new Date().getFullYear();
            const yearOptions = Array.from({length: 10}, (_, i) => currentYear - i)
                                     .map(y => `<option value="${y}" ${y === fileData.year ? 'selected' : ''}>${y}</option>`).join('');

            row.innerHTML = `
                <td>${fileData.file.name}</td>
                <td><select class="file-type-selector" data-index="${index}">${typeOptions}</select></td>
                <td><select class="year-selector" data-index="${index}">${yearOptions}</select></td>
                <td><button class="delete-btn" data-index="${index}">×</button></td>
            `;
            uploadedFilesTableBody.appendChild(row);
        });

        document.querySelectorAll('.delete-btn').forEach(button => {
            button.addEventListener('click', (e) => {
                const index = e.target.getAttribute('data-index');
                uploadedFiles.splice(index, 1);
                renderUploadedFiles();
            });
        });

        document.querySelectorAll('.file-type-selector, .year-selector').forEach(selector => {
            selector.addEventListener('change', (e) => {
                const index = e.target.getAttribute('data-index');
                if (e.target.classList.contains('file-type-selector')) {
                    uploadedFiles[index].type = e.target.value;
                } else {
                    uploadedFiles[index].year = parseInt(e.target.value);
                }
            });
        });
    }

    extractDataBtn.addEventListener('click', async () => {
        const companyName = entityNameInput.value;
        const industry = industryInput.value;
        const entityType = entityTypeInput.value;
        const cinId = cinIdInput.value;
        const keyContact = keyContactInput.value;
        const creditAnalyst = creditAnalystInput.value;
        const listedEntity = listedEntityInput.checked;

        if (!companyName || !industry) {
            alert('Please enter both entity name and industry.');
            return;
        }

        // Gather Facility Details
        const getVal = (row, col) => {
            const el = document.querySelector(`.facility-input[data-row="${row}"][data-col="${col}"]`);
            return el ? (parseFloat(el.value) || 0) : 0;
        };

        const facilityDetails = {
            secured: {
                existing: getVal('secured', 'existing'),
                proposed: getVal('secured', 'proposed'),
                outstanding: getVal('secured', 'outstanding'),
                irregularity: getVal('secured', 'irregularity')
            },
            unsecured: {
                existing: getVal('unsecured', 'existing'),
                proposed: getVal('unsecured', 'proposed'),
                outstanding: getVal('unsecured', 'outstanding'),
                irregularity: getVal('unsecured', 'irregularity')
            },
            other: {
                existing: getVal('other', 'existing'),
                proposed: getVal('other', 'proposed'),
                outstanding: getVal('other', 'outstanding'),
                irregularity: getVal('other', 'irregularity')
            }
        };


        extractDataBtn.textContent = 'Extracting...';
        extractDataBtn.disabled = true;

        const createCompanyFormData = new FormData();
        createCompanyFormData.append('company_name', companyName);
        createCompanyFormData.append('industry', industry);
        createCompanyFormData.append('entity_type', entityType);
        createCompanyFormData.append('cin', cinId);
        createCompanyFormData.append('key_contact', keyContact);
        createCompanyFormData.append('credit_analyst', creditAnalyst);
        createCompanyFormData.append('listed_entity', listedEntity);
        createCompanyFormData.append('facility_details', JSON.stringify(facilityDetails));

        try {
            const createResponse = await fetch(`${BACKEND_URL}/create-company`, {
                method: 'POST',
                body: createCompanyFormData
            });


            if (!createResponse.ok) {
                const errorData = await createResponse.json();
                throw new Error(errorData.detail || `HTTP error! status: ${createResponse.status}`);
            }

            if (uploadedFiles.length > 0) {
                const uploadFormData = new FormData();
                uploadFormData.append('company_name', companyName);
                
                const fileMetadata = uploadedFiles.map(f => ({
                    filename: f.file.name,
                    type: f.type,
                    year: f.year
                }));
                
                uploadFormData.append('metadata', JSON.stringify(fileMetadata));

                for (const fileData of uploadedFiles) {
                    uploadFormData.append('files', fileData.file);
                }

                const uploadResponse = await fetch(`${BACKEND_URL}/upload-classified-documents`, {
                    method: 'POST',
                    body: uploadFormData
                });

                if (!uploadResponse.ok) {
                    throw new Error(`HTTP error! status: ${uploadResponse.status}`);
                }
            }

            // 1. Logic: Upload ALL Files & Sync
            // Everything is already uploaded by upload-classified-documents.
            // We just trigger extraction now.

            console.log('Files uploaded. Triggering extraction via GCS-Sync.');
            const filesToProcess = uploadedFiles;

            // Trigger Extraction (Sync)
            extractDataBtn.textContent = `Extracting...`;

            // Trigger Extraction (Sync)
            // We rely on the files already uploaded by upload-classified-documents:
            // - Detailed Reports -> 'financial_reports'
            // - Annual Reports -> 'annual_reports'
            // The backend /extract/ endpoint scans these folders with priority.

            extractDataBtn.textContent = `Extracting from GCS...`;

            const extractFormData = new FormData();
            extractFormData.append('company_name', companyName);
            extractFormData.append('force_refresh', 'false');

            const extractResponse = await fetch(`${BACKEND_URL}/extract/`, {
                method: 'POST',
                body: extractFormData
            });

            const extractResult = await extractResponse.json();

            if (extractResult.success) {
                console.log('Extraction complete:', extractResult.message);
            } else {
                console.warn('Extraction completed with warnings:', extractResult.message);
                // We proceed anyway as it might just be "no new data"
            }
            
            // After extraction, redirect to the entity page
            window.location.href = `entity.html?company=${encodeURIComponent(companyName)}`;

        } catch (error) {
            console.error('Error during extraction process:', error);
            alert(`An error occurred: ${error.message}`);
        } finally {
            extractDataBtn.textContent = 'Extract Data';
            extractDataBtn.disabled = false;
        }
    });



    // Deprecated helpers removed/replaced by uploadToGCS
    // The renderExtractedDataTable function is now in utils.js

});