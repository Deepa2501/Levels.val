document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const API_BASE = "https://levels-val-1.onrender.com";
    const salaryForm = document.getElementById("salary-form");
    const generateIpBtn = document.getElementById("generate-ip-btn");
    const ipAddressInput = document.getElementById("ipAddress");
    const offerDateInput = document.getElementById("offerDate");
    const submitBtn = document.getElementById("submit-btn");
    
    const serverStatusLed = document.getElementById("server-status-led");
    const serverStatusText = document.getElementById("server-status-text");
    
    const resultsEmpty = document.getElementById("results-empty");
    const resultsDisplay = document.getElementById("results-display");
    const valStatusBadge = document.getElementById("val-status-badge");
    const valStatusText = document.getElementById("val-status-text");
    const valTrustScoreText = document.getElementById("val-trust-score");
    const gaugeFillCircle = document.getElementById("gauge-fill-circle");
    
    const valNormSalary = document.getElementById("val-norm-salary");
    const valDeviation = document.getElementById("val-deviation");
    
    const valRangeMin = document.getElementById("val-range-min");
    const valRangeAvg = document.getElementById("val-range-avg");
    const valRangeMax = document.getElementById("val-range-max");
    const valSalaryMarker = document.getElementById("val-salary-marker");
    const valMarkerTooltip = document.getElementById("val-marker-tooltip");
    
    const valReasonsList = document.getElementById("val-reasons-list");
    
    const statTotalRecords = document.getElementById("stat-total-records");
    const statDbRecords = document.getElementById("stat-db-records");
    const featureChart = document.getElementById("feature-chart");
    const retrainBtn = document.getElementById("retrain-btn");
    const historyTableBody = document.getElementById("history-table-body");
    
    const themeToggleBtn = document.getElementById("theme-toggle");
    const themeNameSpan = document.getElementById("theme-name");
    
    const toast = document.getElementById("toast");

    // Initialize default values
    ipAddressInput.value = generateRandomIP();
    offerDateInput.value = new Date().toISOString().split("T")[0];

    // Theme Management
    initTheme();
    themeToggleBtn.addEventListener("click", toggleTheme);

    // Check server connection
    checkServerStatus();

    // Randomize IP click
    generateIpBtn.addEventListener("click", () => {
        ipAddressInput.value = generateRandomIP();
        showToast("Client IP randomized.");
    });

    // Form submission
    salaryForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        // Disable button during call
        submitBtn.disabled = true;
        submitBtn.innerHTML = "<span>Analyzing...</span>";
        
        const payload = {
            company: document.getElementById("company").value,
            role: document.getElementById("role").value,
            location: document.getElementById("location").value,
            yearsOfExperience: parseFloat(document.getElementById("yearsOfExperience").value),
            offerDate: offerDateInput.value,
            totalCompensation: parseFloat(document.getElementById("totalCompensation").value),
            currency: document.getElementById("currency").value,
            level: document.getElementById("level").value,
            baseSalary: parseFloat(document.getElementById("baseSalary").value) || 0.0,
            avgAnnualStockGrantValue: parseFloat(document.getElementById("avgAnnualStockGrantValue").value) || 0.0,
            avgAnnualBonusValue: parseFloat(document.getElementById("avgAnnualBonusValue").value) || 0.0,
            ipAddress: ipAddressInput.value
        };

        try {
            const response = await fetch('${API_BASE}/validate-submission', {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Validation request failed.");
            }

            const data = await response.json();
            renderResults(data, payload);
            showToast("Compensation analyzed successfully!");
            
            // Reload metadata and history after submissions
            setTimeout(() => {
                loadInsights();
                loadHistory();
            }, 500);

        } catch (error) {
            console.error(error);
            showToast(error.message, "danger");
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = "<span>Analyze Submission</span>";
        }
    });

    // Retrain button click
    retrainBtn.addEventListener("click", async () => {
        retrainBtn.disabled = true;
        retrainBtn.innerText = "Training Model...";
        showToast("Model retraining cycle triggered in background.");

        try {
            const response = await fetch('${API_BASE}/train', { method: "POST" });
            if (!response.ok) throw new Error("Retraining trigger failed.");
            pollTrainingStatus();
        } catch (error) {
            console.error(error);
            showToast(error.message, "danger");
            retrainBtn.disabled = false;
            retrainBtn.innerText = "Retrain Model";
        }
    });

    // --- Core Sub-modules ---

    function initTheme() {
        const savedTheme = localStorage.getItem("theme") || "theme-synthwave";
        document.body.className = savedTheme;
        themeNameSpan.innerText = savedTheme === "theme-light" ? "Light Mode" : "Synthwave";
        
        // Redraw distribution canvas if results are visible
        if (!resultsDisplay.classList.contains("hidden")) {
            setTimeout(redrawCanvasCurrent, 100);
        }
    }

    function toggleTheme() {
        const isLight = document.body.classList.contains("theme-light");
        const nextTheme = isLight ? "theme-synthwave" : "theme-light";
        document.body.className = nextTheme;
        themeNameSpan.innerText = nextTheme === "theme-light" ? "Light Mode" : "Synthwave";
        localStorage.setItem("theme", nextTheme);
        showToast(`Switched to ${nextTheme === "theme-light" ? "frosted glass light mode" : "cyberpunk synthwave dark mode"}.`);
        
        // Redraw distribution canvas
        if (!resultsDisplay.classList.contains("hidden")) {
            redrawCanvasCurrent();
        }
    }

    function redrawCanvasCurrent() {
        const submitted = parseFloat(valNormSalary.dataset.rawVal);
        const min = parseFloat(valRangeMin.dataset.rawVal);
        const avg = parseFloat(valRangeAvg.dataset.rawVal);
        const max = parseFloat(valRangeMax.dataset.rawVal);
        if (!isNaN(submitted)) {
            drawDistributionCurve(submitted, min, avg, max);
        }
    }

    async function checkServerStatus() {
        try {
            const response = await fetch('${API_BASE}/health');
            if (response.ok) {
                serverStatusLed.className = "status-indicator online";
                serverStatusText.innerText = "Connected";
                loadInsights();
                loadHistory();
            } else {
                throw new Error();
            }
        } catch (error) {
            serverStatusLed.className = "status-indicator offline";
            serverStatusText.innerText = "Offline";
            showToast("Cannot connect to server.", "danger");
        }
    }

    async function loadInsights() {
        try {
            const response = await fetch('${API_BASE}/model-insights');
            if (!response.ok) throw new Error();
            
            const data = await response.json();
            
            statTotalRecords.innerText = data.total_training_records;
            statDbRecords.innerText = data.db_accepted_records;
            
            renderFeatureChart(data.feature_importances);
        } catch (error) {
            console.error("Failed to load model insights.", error);
        }
    }

    async function loadHistory() {
        try {
            const response = await fetch('${API_BASE}/submissions');
            if (!response.ok) throw new Error("Failed to load submissions audit history.");
            
            const data = await response.json();
            renderHistoryTable(data);
        } catch (error) {
            console.error(error);
        }
    }

    function renderHistoryTable(submissions) {
        historyTableBody.innerHTML = "";
        
        if (!submissions || submissions.length === 0) {
            historyTableBody.innerHTML = `
                <tr>
                    <td colspan="10" class="empty-table">No accepted submissions in SQLite database.</td>
                </tr>
            `;
            return;
        }

        submissions.forEach(row => {
            const tr = document.createElement("tr");
            
            const salaryFormatted = formatCurrency(row.totalCompensation) + ` ${row.currency}`;
            const trustColorClass = row.trust_score >= 70 ? 'text-success' : 'text-warning';
            
            const breakdownText = (row.baseSalaryINR || row.stockINR || row.bonusINR) ? 
                `<div style="font-size: 0.7rem; color: var(--text-secondary); margin-top: 0.15rem; white-space: nowrap;">` +
                `Base: ${formatCurrency(row.baseSalaryINR)} | ` +
                `Stock: ${formatCurrency(row.stockINR)} | ` +
                `Bonus: ${formatCurrency(row.bonusINR)} (INR)` +
                `</div>` : "";

            tr.innerHTML = `
                <td>#${row.id}</td>
                <td><strong>${row.company}</strong></td>
                <td>${row.role}</td>
                <td><span style="font-weight: 600; color: var(--accent-pink);">${row.level || 'IC1'}</span></td>
                <td>${row.location}</td>
                <td>${row.yearsOfExperience} YOE</td>
                <td>
                    <div style="font-weight: 600;">${salaryFormatted}</div>
                    ${breakdownText}
                </td>
                <td class="trust-cell ${trustColorClass}">${row.trust_score}</td>
                <td>
                    <span class="status-badge ${row.status}">
                        <span class="badge-dot"></span>
                        <span class="badge-text" style="font-size: 0.65rem;">${row.status}</span>
                    </span>
                </td>
                <td>
                    <button class="btn-delete" data-id="${row.id}">Prune</button>
                </td>
            `;
            
            // Add click listener for pruning DB items
            tr.querySelector(".btn-delete").addEventListener("click", () => {
                deleteSubmissionRecord(row.id);
            });
            
            historyTableBody.appendChild(tr);
        });
    }

    async function deleteSubmissionRecord(id) {
        if (!confirm(`Are you sure you want to delete submission #${id} from database?`)) {
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/submissions/${id}`, { method: "DELETE" });
            if (!response.ok) throw new Error("Deletion request failed.");
            
            showToast(`Submission #${id} deleted from database.`);
            loadHistory();
            loadInsights();
        } catch (error) {
            console.error(error);
            showToast(error.message, "danger");
        }
    }

    function renderFeatureChart(importances) {
        featureChart.innerHTML = "";
        
        if (!importances || importances.length === 0) {
            featureChart.innerHTML = `<div class="chart-loading">No weights available. Train model.</div>`;
            return;
        }

        const maxWeight = Math.max(...importances.map(f => f.weight), 0.01);

        importances.forEach(item => {
            const pct = (item.weight * 100).toFixed(1);
            const scaleWidth = (item.weight / maxWeight) * 100;
            
            const row = document.createElement("div");
            row.className = "chart-row";
            row.innerHTML = `
                <div class="chart-row-lbls">
                    <span class="lbl">${item.feature}</span>
                    <span class="val">${pct}%</span>
                </div>
                <div class="chart-bar-track">
                    <div class="chart-bar-fill" style="width: 0%"></div>
                </div>
            `;
            featureChart.appendChild(row);
            
            setTimeout(() => {
                const fill = row.querySelector(".chart-bar-fill");
                if (fill) fill.style.width = scaleWidth + "%";
            }, 100);
        });
    }

    function renderResults(data, payload = null) {
        // Toggle view panels
        resultsEmpty.classList.add("hidden");
        resultsDisplay.classList.remove("hidden");
        
        // Status badge updates
        valStatusText.innerText = data.status;
        valStatusBadge.className = `status-badge ${data.status}`;
        
        // Trust score animation (Gauge)
        animateTrustScore(data.trust_score);
        
        // Store raw variables on dataset for theme shifts
        valNormSalary.dataset.rawVal = data.submitted_salary;
        valRangeMin.dataset.rawVal = data.predicted_range.min;
        valRangeAvg.dataset.rawVal = data.predicted_range.avg;
        valRangeMax.dataset.rawVal = data.predicted_range.max;
        
        // Text details
        valNormSalary.innerText = formatCurrency(data.submitted_salary) + " INR";
        
        const deviationStr = data.deviation_percent >= 0 ? `+${data.deviation_percent}%` : `${data.deviation_percent}%`;
        valDeviation.innerText = deviationStr;
        valDeviation.className = `val ${data.deviation_percent > 30 || data.deviation_percent < -30 ? 'text-danger' : ''}`;
        
        // Populate Submitted Details
        const companyVal = payload ? payload.company : document.getElementById("company").value;
        const roleVal = payload ? payload.role : document.getElementById("role").value;
        const levelVal = payload ? payload.level : document.getElementById("level").value;
        const locationVal = payload ? payload.location : document.getElementById("location").value;
        const yoeVal = payload ? payload.yearsOfExperience : parseFloat(document.getElementById("yearsOfExperience").value);
        const tcVal = payload ? payload.totalCompensation : parseFloat(document.getElementById("totalCompensation").value);
        const currencyVal = payload ? payload.currency : document.getElementById("currency").value;
        const baseVal = payload ? payload.baseSalary : parseFloat(document.getElementById("baseSalary").value) || 0.0;
        const stockVal = payload ? payload.avgAnnualStockGrantValue : parseFloat(document.getElementById("avgAnnualStockGrantValue").value) || 0.0;
        const bonusVal = payload ? payload.avgAnnualBonusValue : parseFloat(document.getElementById("avgAnnualBonusValue").value) || 0.0;

        document.getElementById("val-submitted-profile").innerText = `${companyVal || '-'} - ${roleVal || '-'} (${levelVal || '-'})`;
        document.getElementById("val-submitted-loc-yoe").innerText = `${locationVal || '-'} | ${!isNaN(yoeVal) ? yoeVal : 0} YOE`;
        document.getElementById("val-submitted-tc").innerText = !isNaN(tcVal) ? `${formatCurrency(tcVal)} ${currencyVal}` : "-";
        document.getElementById("val-submitted-base").innerText = baseVal > 0 ? `${formatCurrency(baseVal)} ${currencyVal}` : "-";
        document.getElementById("val-submitted-stock").innerText = stockVal > 0 ? `${formatCurrency(stockVal)} ${currencyVal}` : "-";
        document.getElementById("val-submitted-bonus").innerText = bonusVal > 0 ? `${formatCurrency(bonusVal)} ${currencyVal}` : "-";

        // Expected market range labels
        valRangeMin.innerText = formatCurrencyCompact(data.predicted_range.min);
        valRangeAvg.innerText = formatCurrencyCompact(data.predicted_range.avg);
        valRangeMax.innerText = formatCurrencyCompact(data.predicted_range.max);
        
        // Range Visualizer positioning
        positionSalaryMarker(
            data.submitted_salary, 
            data.predicted_range.min, 
            data.predicted_range.avg, 
            data.predicted_range.max
        );
        
        // Draw Distribution Bell Curve on Canvas
        drawDistributionCurve(
            data.submitted_salary, 
            data.predicted_range.min, 
            data.predicted_range.avg, 
            data.predicted_range.max
        );
        
        // Scoring Log / Reasons
        valReasonsList.innerHTML = "";
        if (data.reasons.length === 0) {
            valReasonsList.innerHTML = `
                <li style="border-left-color: var(--color-success); background: rgba(16,185,129,0.03);">
                    ✅ Submission completely aligned with market predictions and validation limits.
                </li>
            `;
        } else {
            data.reasons.forEach(reason => {
                const li = document.createElement("li");
                
                if (reason.includes("-50.0") || reason.includes("-40.0") || reason.includes("outlier")) {
                    li.className = "danger";
                } else if (reason.includes("anomaly") || reason.includes("-35.0") || reason.includes("deviates")) {
                    li.className = "warning";
                }
                
                li.innerText = reason;
                valReasonsList.appendChild(li);
            });
        }
    }

    function animateTrustScore(score) {
        let current = 0;
        const duration = 1000;
        const steps = 30;
        const stepTime = duration / steps;
        const increment = score / steps;
        
        const interval = setInterval(() => {
            current += increment;
            if (current >= score) {
                current = score;
                clearInterval(interval);
            }
            valTrustScoreText.innerText = Math.round(current);
        }, stepTime);
        
        const offset = 283 - (283 * score) / 100;
        gaugeFillCircle.style.strokeDashoffset = offset;
        
        if (score >= 70) {
            gaugeFillCircle.style.stroke = "var(--color-success)";
        } else if (score >= 50) {
            gaugeFillCircle.style.stroke = "var(--color-warning)";
        } else {
            gaugeFillCircle.style.stroke = "var(--color-danger)";
        }
    }

    function positionSalaryMarker(submitted, min, avg, max) {
        const marker = valSalaryMarker;
        const tooltip = valMarkerTooltip;
        
        marker.classList.remove("out-of-bounds");
        
        const rangeWidth = max - min;
        let pct = 50;
        
        if (rangeWidth > 0) {
            pct = ((submitted - min) / rangeWidth) * 60 + 20;
        }
        
        pct = Math.max(5, Math.min(95, pct));
        marker.style.left = pct + "%";
        
        if (submitted < min || submitted > max) {
            marker.classList.add("out-of-bounds");
            tooltip.innerText = `Deviating: ${formatCurrencyCompact(submitted)}`;
        } else {
            tooltip.innerText = `Verified: ${formatCurrencyCompact(submitted)}`;
        }
    }

    function drawDistributionCurve(submitted, min, avg, max) {
        const canvas = document.getElementById("distribution-canvas");
        const ctx = canvas.getContext("2d");
        
        // Make canvas responsive based on container
        const rect = canvas.parentNode.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = 140;
        
        const width = canvas.width;
        const height = canvas.height;
        ctx.clearRect(0, 0, width, height);
        
        // Define standard deviation. Standard normal P10-P90 is ~2.56 std devs.
        const stdDev = Math.max((max - min) / 2.56, min * 0.1, 1000);
        const mean = avg;
        
        // X scale limits (Mean - 3.5 SD to Mean + 3.5 SD)
        const xMin = mean - 3.5 * stdDev;
        const xMax = mean + 3.5 * stdDev;
        const xRange = xMax - xMin;
        
        // Map data points to Canvas pixels
        function toXPixel(val) {
            return ((val - xMin) / xRange) * (width - 40) + 20;
        }
        
        // Math standard normal density: f(x)
        function normalPDF(x) {
            return Math.exp(-0.5 * Math.pow((x - mean) / stdDev, 2));
        }
        
        // Peak of curve is at height - 30px
        const graphHeight = height - 40;
        function toYPixel(densityVal) {
            return height - 20 - (densityVal * graphHeight);
        }
        
        // Setup colors based on theme class on body
        const isLight = document.body.classList.contains("theme-light");
        const colorPrimary = isLight ? "#4338ca" : "#ff007f"; // Indigo or Hot Pink
        const colorSecondary = isLight ? "#0ea5e9" : "#00f0ff"; // Cyan
        const colorText = isLight ? "#64748b" : "#b4b0c4";
        const colorGrid = isLight ? "rgba(15, 23, 42, 0.08)" : "rgba(255, 255, 255, 0.05)";
        const colorFill = isLight ? "rgba(99, 102, 241, 0.08)" : "rgba(255, 0, 127, 0.08)";
        
        // 1. Draw Grid lines
        ctx.strokeStyle = colorGrid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        // Base line
        ctx.moveTo(10, height - 20);
        ctx.lineTo(width - 10, height - 20);
        ctx.stroke();
        
        // 2. Draw expected range fill box (P10 to P90)
        const p10X = toXPixel(min);
        const p90X = toXPixel(max);
        
        ctx.fillStyle = colorFill;
        ctx.beginPath();
        ctx.moveTo(p10X, height - 20);
        
        // Trace bell curve top for shaded inlier zone
        for (let xPixel = p10X; xPixel <= p90X; xPixel++) {
            const xValue = xMin + ((xPixel - 20) / (width - 40)) * xRange;
            const yValue = toYPixel(normalPDF(xValue));
            ctx.lineTo(xPixel, yValue);
        }
        ctx.lineTo(p90X, height - 20);
        ctx.closePath();
        ctx.fill();
        
        // 3. Draw full bell curve outline
        ctx.strokeStyle = colorPrimary;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        for (let xPixel = 15; xPixel < width - 15; xPixel++) {
            const xValue = xMin + ((xPixel - 20) / (width - 40)) * xRange;
            const yValue = toYPixel(normalPDF(xValue));
            if (xPixel === 15) {
                ctx.moveTo(xPixel, yValue);
            } else {
                ctx.lineTo(xPixel, yValue);
            }
        }
        ctx.stroke();
        
        // 4. Draw marker for User's salary
        const userX = toXPixel(submitted);
        const cappedUserX = Math.max(25, Math.min(width - 25, userX));
        const userDensity = normalPDF(submitted);
        const userY = toYPixel(userDensity);
        
        // User vertical indicator line
        ctx.strokeStyle = submitted < min || submitted > max ? "var(--color-danger)" : colorSecondary;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(cappedUserX, height - 20);
        ctx.lineTo(cappedUserX, Math.min(userY, height - 40));
        ctx.stroke();
        ctx.setLineDash([]); // Reset dash
        
        // Draw user dot
        ctx.fillStyle = submitted < min || submitted > max ? "var(--color-danger)" : colorSecondary;
        ctx.beginPath();
        ctx.arc(cappedUserX, Math.min(userY, height - 40), 6, 0, 2 * Math.PI);
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        
        // Draw user label text
        ctx.fillStyle = isLight ? "#0f172a" : "#ffffff";
        ctx.font = "bold 9px Inter, sans-serif";
        ctx.textAlign = cappedUserX > width - 60 ? "right" : cappedUserX < 60 ? "left" : "center";
        ctx.fillText("You (" + formatCurrencyCompact(submitted) + ")", cappedUserX, Math.min(userY, height - 40) - 10);
        
        // 5. Draw Range bounds indicators
        ctx.fillStyle = colorText;
        ctx.font = "500 8px Inter, sans-serif";
        ctx.textAlign = "center";
        
        // Min vertical tick
        ctx.strokeStyle = colorGrid;
        ctx.beginPath();
        ctx.moveTo(p10X, height - 25);
        ctx.lineTo(p10X, height - 15);
        ctx.stroke();
        ctx.fillText("P10", p10X, height - 7);
        
        // Max vertical tick
        ctx.beginPath();
        ctx.moveTo(p90X, height - 25);
        ctx.lineTo(p90X, height - 15);
        ctx.stroke();
        ctx.fillText("P90", p90X, height - 7);
        
        // Avg/Mean vertical tick
        const avgX = toXPixel(mean);
        ctx.beginPath();
        ctx.moveTo(avgX, height - 25);
        ctx.lineTo(avgX, height - 15);
        ctx.stroke();
        ctx.fillText("Market Avg", avgX, height - 7);
    }

    function formatCurrency(num) {
        return new Intl.NumberFormat('en-IN', { maxFractionDigits: 0 }).format(num);
    }

    function formatCurrencyCompact(num) {
        if (num >= 10000000) {
            return (num / 10000000).toFixed(2) + " Cr";
        } else if (num >= 100000) {
            return (num / 100000).toFixed(2) + " L";
        } else if (num >= 1000) {
            return (num / 1000).toFixed(0) + " K";
        }
        return num.toFixed(0);
    }

    async function pollTrainingStatus() {
        let attempts = 0;
        const maxAttempts = 15;
        
        const interval = setInterval(async () => {
            attempts++;
            try {
                const response = await fetch('${API_BASE}/health');
                if (response.ok) {
                    const data = await response.json();
                    if (data.model_trained && attempts > 1) {
                        clearInterval(interval);
                        retrainBtn.disabled = false;
                        retrainBtn.innerText = "Retrain Model";
                        showToast("Model retrained and updated successfully!");
                        loadInsights();
                    }
                }
            } catch (e) {
                console.error("Polling training health failed.", e);
            }
            
            if (attempts >= maxAttempts) {
                clearInterval(interval);
                retrainBtn.disabled = false;
                retrainBtn.innerText = "Retrain Model";
                showToast("Training taking longer than expected. Check logs.", "warning");
            }
        }, 2000);
    }

    function showToast(msg, type = "success") {
        toast.innerText = msg;
        toast.className = `toast ${type}`;
        toast.classList.remove("hidden");
        
        if (toast.timeoutId) {
            clearTimeout(toast.timeoutId);
        }
        
        toast.timeoutId = setTimeout(() => {
            toast.classList.add("hidden");
        }, 3500);
    }

    function generateRandomIP() {
        const octet1 = Math.floor(Math.random() * 223) + 1;
        const octet2 = Math.floor(Math.random() * 256);
        const octet3 = Math.floor(Math.random() * 256);
        const octet4 = Math.floor(Math.random() * 254) + 1;
        return `${octet1}.${octet2}.${octet3}.${octet4}`;
    }
});
