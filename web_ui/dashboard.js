async function loadReport() {
  try {
    const response = await fetch("report.json");
    const data = await response.json();
    renderDashboard(data);
  } catch (e) {
    document.getElementById("summary").innerHTML =
      "<p>⚠️ No report found. Run your SEO audit first.</p>";
  }
}

function getBadge(score) {
  if (score >= 85) return `<span class='score-badge score-good'>${score}%</span>`;
  if (score >= 60) return `<span class='score-badge score-average'>${score}%</span>`;
  return `<span class='score-badge score-poor'>${score}%</span>`;
}

function renderDashboard(data) {
  const summaryEl = document.getElementById("summary");
  const pages = Object.keys(data.pages).length;
  const scores = Object.values(data.pages).map(p => p.scores.score);
  const avgScore = scores.length ? (scores.reduce((a,b)=>a+b,0)/scores.length).toFixed(1) : 0;

  summaryEl.innerHTML = `
    <p><strong>Website:</strong> ${data.site}</p>
    <p><strong>Total Pages Crawled:</strong> ${pages}</p>
    <p><strong>Average SEO Score:</strong> ${getBadge(avgScore)}</p>
    <p><strong>Generated:</strong> ${data.generated_at}</p>
  `;

  // Trend chart (simulate by showing scores over index)
  const ctxTrend = document.getElementById("trendChart");
  new Chart(ctxTrend, {
    type: "line",
    data: {
      labels: scores.map((_, i) => "Page " + (i + 1)),
      datasets: [{
        label: "SEO Score",
        data: scores,
        borderColor: "#a020f0",
        backgroundColor: "rgba(160,32,240,0.2)",
        fill: true,
        tension: 0.3
      }]
    },
    options: { scales: { y: { beginAtZero: true, max: 100 } } }
  });

  // Score distribution
  const ctxScore = document.getElementById("scoreChart");
  const groups = { good: 0, average: 0, poor: 0 };
  scores.forEach(s => {
    if (s >= 85) groups.good++;
    else if (s >= 60) groups.average++;
    else groups.poor++;
  });

  new Chart(ctxScore, {
    type: "doughnut",
    data: {
      labels: ["Good (85–100)", "Average (60–84)", "Poor (<60)"],
      datasets: [{
        data: [groups.good, groups.average, groups.poor],
        backgroundColor: ["#3ab54a", "#f5a623", "#e9407a"]
      }]
    },
    options: { plugins: { legend: { position: "bottom" } } }
  });

  // Issues table
  const tbody = document.querySelector("#issuesTable tbody");
  tbody.innerHTML = "";
  Object.entries(data.pages).forEach(([url, page]) => {
    const reasons = page.scores?.reasons?.join(", ") || "No issues";
    tbody.insertAdjacentHTML(
      "beforeend",
      `<tr><td>${url}</td><td>${reasons}</td><td>${getBadge(page.scores?.score || 0)}</td></tr>`
    );
  });
}

loadReport();
