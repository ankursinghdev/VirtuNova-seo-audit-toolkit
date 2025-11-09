# --- BEGIN VirtuNova SEO Audit Toolkit (Final Full Script) ---
"""
VirtuNova SEO Audit Toolkit
Fully automated crawler + analyzer + PDF + Web UI generator
"""

import argparse, asyncio, json, os, re, time
from collections import deque
from urllib.parse import urljoin, urlparse
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
import aiohttp
from bs4 import BeautifulSoup
import validators

USER_AGENT = "VirtuNova-SEO-Toolkit/1.0 (+https://virtunova.com)"
MAX_CONCURRENT_REQUESTS = 8
REQUEST_TIMEOUT = 20
DEFAULT_MAX_PAGES = 100


async def fetch(session, url):
    headers = {"User-Agent": USER_AGENT}
    try:
        async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            text = await resp.text(errors="ignore")
            return {"url": url, "status": resp.status, "text": text, "headers": dict(resp.headers)}
    except Exception as e:
        return {"url": url, "status": None, "error": str(e)}


def normalize_url(base, href):
    if not href or href.startswith(("javascript:", "mailto:", "#")):
        return None
    joined = urljoin(base, href)
    parsed = urlparse(joined)
    return parsed._replace(fragment="").geturl()


def analyze_html(url, text):
    soup = BeautifulSoup(text, "lxml")
    result = {}
    title_tag = soup.find("title")
    title = title_tag.string.strip() if title_tag and title_tag.string else ""
    desc_tag = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    desc = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
    imgs = soup.find_all("img")
    imgs_missing_alt = [i.get("src") for i in imgs if not i.get("alt")]
    result.update({
        "title": {"text": title, "length": len(title)},
        "meta_description": {"text": desc, "length": len(desc)},
        "h1": {"count": len(h1s), "texts": h1s},
        "images": {"total": len(imgs), "missing_alt_count": len(imgs_missing_alt)},
    })
    return result


class SEOCrawler:
    def __init__(self, seed_url, max_pages=DEFAULT_MAX_PAGES):
        self.seed = seed_url
        self.to_visit = deque([seed_url])
        self.seen = set([seed_url])
        self.results = {}
        self.max_pages = max_pages

    async def run(self):
        async with aiohttp.ClientSession() as session:
            sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

            async def worker():
                while self.to_visit:
                    url = self.to_visit.popleft()
                    async with sem:
                        data = await fetch(session, url)
                    self.results[url] = {"fetch": data}
                    if data.get("status") == 200 and data.get("text"):
                        analysis = analyze_html(url, data["text"])
                        self.results[url]["analysis"] = analysis
                        soup = BeautifulSoup(data["text"], "lxml")
                        for a in soup.find_all("a", href=True):
                            n = normalize_url(url, a["href"])
                            if n and urlparse(n).netloc == urlparse(self.seed).netloc and n not in self.seen:
                                if len(self.seen) < self.max_pages:
                                    self.seen.add(n)
                                    self.to_visit.append(n)

            tasks = [asyncio.create_task(worker()) for _ in range(MAX_CONCURRENT_REQUESTS)]
            await asyncio.gather(*tasks)


def score_page(analysis):
    score = 100
    reasons = []
    if analysis["title"]["length"] == 0:
        score -= 15; reasons.append("Missing title")
    if analysis["meta_description"]["length"] == 0:
        score -= 10; reasons.append("Missing meta description")
    if analysis["h1"]["count"] == 0:
        score -= 10; reasons.append("No H1 tag")
    if analysis["images"]["missing_alt_count"] > 0:
        score -= 5; reasons.append("Images missing alt text")
    return {"score": max(0, score), "reasons": reasons}


def generate_pdf_report(report_data, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("<font size=18 color='#A020F0'><b>VirtuNova SEO Audit Report</b></font>", styles["Title"]),
        Spacer(1, 0.25 * inch),
        Paragraph(f"<b>Website:</b> {report_data['site']}", styles["Normal"]),
        Paragraph(f"<b>Generated:</b> {report_data['generated_at']}", styles["Normal"]),
        Spacer(1, 0.25 * inch),
    ]
    total_pages = len(report_data["pages"])
    elements.append(Paragraph(f"<b>Total Pages Crawled:</b> {total_pages}", styles["Normal"]))
    issues = [(u, p["scores"]["reasons"]) for u, p in report_data["pages"].items() if p["scores"]["reasons"]]
    elements.append(Paragraph(f"<b>Pages with issues:</b> {len(issues)}", styles["Normal"]))
    for url, reasons in issues[:10]:
        elements.append(Paragraph(f"<b>{url}</b>", styles["Normal"]))
        for r in reasons:
            elements.append(Paragraph(f"- {r}", styles["Normal"]))
        elements.append(Spacer(1, 0.1 * inch))
    elements.append(Spacer(1, 0.25 * inch))
    elements.append(Paragraph("<font color='#A020F0'>VirtuNova — Where Creativity, Technology, and Strategy Converge.</font>", styles["Italic"]))
    doc.build(elements)
    print(f"✅ PDF generated at {output_path}")


async def run_audit(seed_url, output_path, max_pages=50):
    crawler = SEOCrawler(seed_url, max_pages=max_pages)
    await crawler.run()
    report = {"site": seed_url, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "pages": {}}
    for url, data in crawler.results.items():
        if data.get("analysis"):
            scores = score_page(data["analysis"])
            report["pages"][url] = {"analysis": data["analysis"], "scores": scores}
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    generate_pdf_report(report, os.path.join(os.path.dirname(output_path), "SEO_Audit_Report.pdf"))
    print("Audit complete. Report saved to", output_path)
    return report


def cli():
    parser = argparse.ArgumentParser(description="VirtuNova SEO Audit")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", default="reports/report.json")
    parser.add_argument("--pages", type=int, default=50)
    args = parser.parse_args()
    asyncio.run(run_audit(args.url, args.output, args.pages))


if __name__ == "__main__":
    cli()
# --- END VirtuNova SEO Audit Toolkit ---
