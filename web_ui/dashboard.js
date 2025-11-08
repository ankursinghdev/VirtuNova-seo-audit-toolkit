async function loadReport() {
  try {
    const response = await fetch("report.json");
    const data = await response.json();
    renderDashboard(data);
  } catch (e) {
    document.getElementById("summary").innerHTML = "<p>⚠️ No report found. Run an audit first.</p>";
  }
}

function renderDashboard(data) {
  const summaryEl = document.getElementById("summary");
  const site = data.site;
  const pages = Object.keys(data.pages).length;
  let avgScore = 0;
  const scores = [];

  for (const [url, page] of Object.entries(data.pages)) {
    const s = page.scores?.score;
    if (s !== undefined) scores.push(s);
  }

  if (scores.length) avgScore = (scores.reduce((a,b)=>a+b,0) / scores.length).toFixed(1);

  summaryEl.innerHTML = `
    <p><strong>Website:</strong> ${site}</p>
    <p><strong>Total Pages:</strong> ${pages}</p>
    <p><strong>Average SEO Score:</strong> ${avgScore}%</p>
  `;

  // Chart
  const ctx = document.getElementById("scoreChart");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: scores.map((_, i) => "Page " + (i + 1)),
      datasets: [{
        label: "SEO Score",
        data: scores,
        backgroundColor: "#a020f0aa"
      }]
    },
    options: {
      scales: { y: { beginAtZero: true, max: 100 } },
      plugins: { legend: { display: false } }
    }
  });

  // Issues table
  const tbody = document.querySelector("#issuesTable tbody");
  Object.entries(data.pages)
    .slice(0, 10)
    .forEach(([url, page]) => {
      const reasons = page.scores?.reasons?.join(", ") || "No major issues";
      const row = `<tr><td>${url}</td><td>${reasons}</td></tr>`;
      tbody.insertAdjacentHTML("beforeend", row);
    });
}

loadReport();
