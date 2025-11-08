# --- BEGIN seo_audit_tool_extended.py ---
"""
VirtuNova SEO Audit Toolkit — Extended Version
Features:
- Async Crawler & HTML Analyzer
- PageSpeed Insights Integration (optional)
- Lighthouse JSON Import
- Branded PDF Report Export
- React Web UI JSON Writer
- Advanced audits: JSON-LD, hreflang, canonical chains
Usage:
  python seo_audit_tool_extended.py --url https://www.ellocentlabs.com --output reports/report.json --pages 100 --pagespeed-key ${{ secrets.PAGESPEED_KEY }} --web-ui
Dependencies (install via pip):
  aiohttp beautifulsoup4 lxml validators reportlab requests
"""

import argparse, asyncio, json, os, re, time
from collections import deque
from urllib.parse import urljoin, urlparse

# Optional dependencies
try:
    import aiohttp
    from bs4 import BeautifulSoup
    import validators
except Exception:
    aiohttp = None
    BeautifulSoup = None
    validators = None

# Branding constants
USER_AGENT = "VirtuNova-SEO-Toolkit/1.0 (+https://virtunova.com)"
MAX_CONCURRENT_REQUESTS = 8
REQUEST_TIMEOUT = 20
DEFAULT_MAX_PAGES = 200


# --- Fetching and Parsing ---
async def fetch(session, url):
    headers = {"User-Agent": USER_AGENT}
    start = time.time()
    try:
        async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            text = await resp.text(errors='ignore')
            return {"url": url, "status": resp.status, "text": text, "elapsed": time.time() - start}
    except Exception as e:
        return {"url": url, "status": None, "error": str(e), "elapsed": None}


def normalize_url(base, href):
    if not href or href.startswith(("javascript:", "mailto:", "#")):
        return None
    return urlparse(urljoin(base, href))._replace(fragment="").geturl()


def is_same_origin(a, b):
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def analyze_html(url, text):
    if not BeautifulSoup:
        return {}
    soup = BeautifulSoup(text, "lxml")
    result = {}

    title_tag = soup.find("title")
    title = title_tag.string.strip() if title_tag and title_tag.string else ""
    result["title"] = {"text": title, "length": len(title)}

    desc_tag = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    desc = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
    result["meta_description"] = {"text": desc, "length": len(desc)}

    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
    result["h1"] = {"count": len(h1s), "texts": h1s}

    can_tag = soup.find("link", rel=re.compile("canonical", re.I))
    canonical = can_tag["href"].strip() if can_tag and can_tag.get("href") else ""
    result["canonical"] = canonical

    robots_tag = soup.find("meta", attrs={"name": re.compile("robots", re.I)})
    robots = robots_tag["content"].strip() if robots_tag and robots_tag.get("content") else ""
    result["meta_robots"] = robots

    viewport_tag = soup.find("meta", attrs={"name": re.compile("viewport", re.I)})
    viewport = viewport_tag["content"].strip() if viewport_tag and viewport_tag.get("content") else ""
    result["viewport"] = viewport

    json_ld = []
    for s in soup.find_all("script", type="application/ld+json"):
        if s.string:
            try:
                json_ld.append(json.loads(s.string))
            except Exception:
                json_ld.append({"raw": s.string[:500]})
    result["json_ld"] = json_ld

    imgs = soup.find_all("img")
    imgs_missing_alt = [i.get("src") for i in imgs if not i.get("alt")]
    result["images"] = {"total": len(imgs), "missing_alt_count": len(imgs_missing_alt)}

    links = [a.get("href") for a in soup.find_all("a", href=True)]
    result["links"] = {"count": len(links)}

    body_text = soup.body.get_text(" ", strip=True) if soup.body else ""
    result["word_count"] = len(re.findall(r"\w+", body_text))

    hreflangs = [{"hreflang": l.get("hreflang"), "href": l.get("href")}
                 for l in soup.find_all("link", attrs={"rel": re.compile("alternate", re.I)})
                 if l.get("hreflang") and l.get("href")]
    result["hreflangs"] = hreflangs
    return result


def validate_json_ld(json_ld_blocks):
    issues = []
    for i, b in enumerate(json_ld_blocks):
        if isinstance(b, dict):
            if "@context" not in b and "@graph" not in b:
                issues.append({"index": i, "issue": "missing @context"})
            if "@type" not in b and "@graph" not in b:
                issues.append({"index": i, "issue": "missing @type"})
        else:
            issues.append({"index": i, "issue": "not a dict"})
    return issues


def canonical_chain_check(pages):
    chains = []
    for url, data in pages.items():
        c = data.get("analysis", {}).get("canonical")
        if not c:
            continue
        chain = [url]
        nxt = c
        while nxt and nxt != chain[-1] and nxt in pages and len(chain) < 20:
            chain.append(nxt)
            nxt = pages[nxt].get("analysis", {}).get("canonical")
        if len(chain) > 1:
            chains.append(chain)
    return chains


async def pagespeed_insights(url, api_key, strategy="mobile"):
    if not api_key:
        return {"error": "no_api_key"}
    api = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = {"url": url, "key": api_key, "strategy": strategy}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api, params=params, timeout=30) as resp:
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}


# --- Crawler ---
class SEOCrawler:
    def __init__(self, seed_url, max_pages=DEFAULT_MAX_PAGES):
        self.seed = seed_url
        self.to_visit = deque([seed_url])
        self.seen = {seed_url}
        self.results = {}
        self.max_pages = max_pages

    async def run(self):
        if not aiohttp:
            raise RuntimeError("aiohttp is required.")
        async with aiohttp.ClientSession() as session:
            sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
            async def worker():
                while self.to_visit:
                    url = self.to_visit.popleft()
                    async with sem:
                        resp = await fetch(session, url)
                    self.results[url] = {"fetch": resp}
                    if resp.get("status") and resp.get("text"):
                        analysis = analyze_html(url, resp["text"])
                        self.results[url]["analysis"] = analysis
                        soup = BeautifulSoup(resp["text"], "lxml")
                        for a in soup.find_all("a", href=True):
                            n = normalize_url(url, a["href"])
                            if n and is_same_origin(self.seed, n) and n not in self.seen and len(self.seen) < self.max_pages:
                                self.seen.add(n)
                                self.to_visit.append(n)
            await asyncio.gather(*[asyncio.create_task(worker()) for _ in range(MAX_CONCURRENT_REQUESTS)])


# --- Core Audit ---
async def run_audit(seed_url, output_path=None, max_pages=100, pagespeed_key=None, write_web_ui=False):
    if not validators or not validators.url(seed_url):
        raise ValueError("Invalid URL or missing validators package.")
    crawler = SEOCrawler(seed_url, max_pages)
    await crawler.run()

    report = {"site": seed_url, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "pages": {}}
    for url, data in crawler.results.items():
        page = {"fetch": data.get("fetch"), "analysis": data.get("analysis")}
        if data.get("analysis") and data.get("fetch"):
            page["scores"] = score_page(page["analysis"], page["fetch"])
        report["pages"][url] = page

    report["canonical_chains"] = canonical_chain_check(report["pages"])
    report["json_ld_issues"] = {u: validate_json_ld(p["analysis"].get("json_ld", []))
                                for u, p in report["pages"].items() if p.get("analysis")}
    if pagespeed_key:
        tasks = [pagespeed_insights(seed_url, pagespeed_key)]
        report["pagespeed"] = {seed_url: (await asyncio.gather(*tasks))[0]}

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    if write_web_ui:
        scaffold_web_ui(report)
    return report


# --- Web UI Writer ---
def scaffold_web_ui(report, target_dir="web_ui"):
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


# --- Scoring ---
def score_page(analysis, fetch_info):
    score, reasons = 100, []
    if not analysis.get("title", {}).get("length"):
        score -= 20; reasons.append("Missing title")
    if not analysis.get("meta_description", {}).get("length"):
        score -= 10; reasons.append("Missing meta description")
    if not analysis.get("h1", {}).get("count"):
        score -= 10; reasons.append("Missing H1")
    if analysis.get("word_count", 0) < 100:
        score -= 5; reasons.append("Low word count (<100)")
    if not fetch_info.get("status") or fetch_info.get("status") >= 400:
        score = 0; reasons.append(f"HTTP error: {fetch_info.get('status')}")
    return {"score": max(0, score), "reasons": reasons}


# --- Branded PDF Generator ---
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

def generate_pdf_report(report_data, output_path="reports/SEO_Audit_Report.pdf"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    styles = getSampleStyleSheet()

    primary_color = colors.HexColor("#A020F0")
    accent_color = colors.HexColor("#E9407A")

    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], textColor=primary_color, fontSize=22)
    heading_style = ParagraphStyle("Heading", parent=styles["Heading2"], textColor=accent_color, fontSize=14)
    normal_style = styles["Normal"]

    elements = []
    logo_path = "assets/logo.png"
    if os.path.exists(logo_path):
        elements.append(Image(logo_path, width=2*inch, height=2*inch))
        elements.append(Spacer(1, 0.2*inch))

    elements.append(Paragraph("VirtuNova — SEO Audit Report", title_style))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph(f"<b>Website:</b> {report_data.get('site')}", normal_style))
    elements.append(Paragraph(f"<b>Generated:</b> {report_data.get('generated_at')}", normal_style))
    elements.append(Spacer(1, 0.3*inch))

    pages = report_data.get("pages", {})
    total_pages = len(pages)
    avg_score = round(sum(p["scores"]["score"] for p in pages.values() if "scores" in p) / max(1, len(pages)), 1)
    elements.append(Paragraph("Executive Summary", heading_style))
    elements.append(Paragraph(f"Total Pages Crawled: <b>{total_pages}</b>", normal_style))
    elements.append(Paragraph(f"Average SEO Score: <b>{avg_score}%</b>", normal_style))
    elements.append(Spacer(1, 0.2*inch))

    issues = [[url, ", ".join(p["scores"]["reasons"])] for url, p in pages.items() if p["scores"]["reasons"]]
    if not issues:
        issues = [["No major issues found", ""]]
    table = Table([["Page URL", "Detected Issues"]] + issues[:10], colWidths=[3*inch, 3*inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), primary_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.4*inch))
    elements.append(Paragraph(
        "<b><font color='#A020F0'>VirtuNova</font></b> — Where Creativity, Technology, and Strategy Converge.",
        ParagraphStyle("Footer", textColor=colors.grey, fontSize=10, alignment=1)
    ))

    doc.build(elements)
    print(f"✅ Branded PDF report generated: {output_path}")


# --- CLI ---
def cli():
    parser = argparse.ArgumentParser(description="Run VirtuNova SEO Audit")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", default="reports/report.json")
    parser.add_argument("--pages", type=int, default=100)
    parser.add_argument("--pagespeed-key", default=None)
    parser.add_argument("--web-ui", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(run_audit(args.url, output_path=args.output, max_pages=args.pages,
                                   pagespeed_key=args.pagespeed_key, write_web_ui=args.web_ui))
    generate_pdf_report(report)
    print("🎯 Audit completed successfully.")


if __name__ == "__main__":
    cli()
# --- END seo_audit_tool_extended.py ---

