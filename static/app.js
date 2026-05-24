document.addEventListener("DOMContentLoaded", () => {

    // Backend API Base URL
    const API_BASE = "https://levels-val-1.onrender.com";

    // DOM Elements
    const salaryForm = document.getElementById("salary-form");
    const generateIpBtn = document.getElementById("generate-ip-btn");
    const ipAddressInput = document.getElementById("ipAddress");
    const offerDateInput = document.getElementById("offerDate");
    const submitBtn = document.getElementById("submit-btn");

    const serverStatusLed = document.getElementById("server-status-led");
    const serverStatusText = document.getElementById("server-status-text");

    // Initialize defaults
    ipAddressInput.value = generateRandomIP();
    offerDateInput.value = new Date().toISOString().split("T")[0];

    // Check backend connection
    checkServerStatus();

    // Generate random IP
    generateIpBtn.addEventListener("click", () => {
        ipAddressInput.value = generateRandomIP();
    });

    // Submit form
    salaryForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        submitBtn.disabled = true;
        submitBtn.innerText = "Analyzing...";

        const payload = {
            company: document.getElementById("company").value,
            role: document.getElementById("role").value,
            location: document.getElementById("location").value,
            yearsOfExperience: parseFloat(document.getElementById("yearsOfExperience").value),
            offerDate: offerDateInput.value,
            totalCompensation: parseFloat(document.getElementById("totalCompensation").value),
            currency: document.getElementById("currency").value,
            level: document.getElementById("level").value,
            baseSalary: parseFloat(document.getElementById("baseSalary").value) || 0,
            avgAnnualStockGrantValue: parseFloat(document.getElementById("avgAnnualStockGrantValue").value) || 0,
            avgAnnualBonusValue: parseFloat(document.getElementById("avgAnnualBonusValue").value) || 0,
            ipAddress: ipAddressInput.value
        };

        try {

            const response = await fetch(`${API_BASE}/validate-submission`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error("Request failed");
            }

            const data = await response.json();

            console.log("Prediction Response:", data);

            alert(
                `Status: ${data.status}\n` +
                `Trust Score: ${data.trust_score}\n` +
                `Deviation: ${data.deviation_percent}%`
            );

        } catch (error) {
            console.error(error);
            alert("Backend connection failed.");
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerText = "Analyze Submission";
        }
    });

    // Health check
    async function checkServerStatus() {

        try {

            const response = await fetch(`${API_BASE}/health`);

            if (response.ok) {
                serverStatusLed.className = "status-indicator online";
                serverStatusText.innerText = "Connected";
            } else {
                throw new Error();
            }

        } catch (error) {

            serverStatusLed.className = "status-indicator offline";
            serverStatusText.innerText = "Offline";

            console.error("Backend Offline");
        }
    }

    // Random IP generator
    function generateRandomIP() {

        const octet1 = Math.floor(Math.random() * 223) + 1;
        const octet2 = Math.floor(Math.random() * 256);
        const octet3 = Math.floor(Math.random() * 256);
        const octet4 = Math.floor(Math.random() * 254) + 1;

        return `${octet1}.${octet2}.${octet3}.${octet4}`;
    }

});
