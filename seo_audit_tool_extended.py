# --- BEGIN seo_audit_tool_extended.py ---
"""
Seo Audit Toolkit - Extended (single-file)
Features:
- Async crawler and analyzers
- PageSpeed Insights integration (optional)
- Lighthouse JSON importer
- PDF export (hook) and PPTX export (hook)
- React web UI scaffold writer (writes ./web_ui/report.json)
- Advanced audits: JSON-LD checks, hreflang, canonical chain
Usage:
  python seo_audit_tool_extended.py --url https://www.ellocentlabs.com --output reports/report.json --pages 100 --pagespeed-key "${{ secrets.PAGESPEED_KEY }}" --web-ui
Dependencies (pip):
  aiohttp beautifulsoup4 lxml tldextract validators python-pptx weasyprint requests
"""
import argparse, asyncio, json, os, re, time
from collections import deque
from urllib.parse import urljoin, urlparse

# optional runtime imports
try:
    import aiohttp
    from bs4 import BeautifulSoup
    import validators
except Exception:
    aiohttp = None
    BeautifulSoup = None
    validators = None

USER_AGENT = "VirtuNova-SEO-Toolkit/1.0 (+https://virtunova.com)"
MAX_CONCURRENT_REQUESTS = 8
REQUEST_TIMEOUT = 20
DEFAULT_MAX_PAGES = 200

async def fetch(session, url):
    headers = {"User-Agent": USER_AGENT}
    start = time.time()
    try:
        async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            text = await resp.text(errors='ignore')
            elapsed = time.time() - start
            return {"url": url, "status": resp.status, "text": text, "elapsed": elapsed, "headers": dict(resp.headers)}
    except Exception as e:
        return {"url": url, "status": None, "error": str(e), "elapsed": None}

def normalize_url(base, href):
    if not href: return None
    href = href.strip()
    if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith('#'): return None
    joined = urljoin(base, href)
    parsed = urlparse(joined)
    cleaned = parsed._replace(fragment='')
    return cleaned.geturl()

def is_same_origin(a,b):
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)

def analyze_html(url, text):
    if not BeautifulSoup:
        return {}
    soup = BeautifulSoup(text, "lxml")
    result = {}
    title_tag = soup.find('title')
    title = title_tag.string.strip() if title_tag and title_tag.string else ''
    result['title'] = {'text': title, 'length': len(title)}
    desc_tag = soup.find('meta', attrs={'name': re.compile('description', re.I)})
    desc = desc_tag['content'].strip() if desc_tag and desc_tag.get('content') else ''
    result['meta_description'] = {'text': desc, 'length': len(desc)}
    h1s = [h.get_text(strip=True) for h in soup.find_all('h1')]
    result['h1'] = {'count': len(h1s), 'texts': h1s}
    can_tag = soup.find('link', rel=re.compile('canonical', re.I))
    canonical = can_tag['href'].strip() if can_tag and can_tag.get('href') else ''
    result['canonical'] = canonical
    robots_tag = soup.find('meta', attrs={'name': re.compile('robots', re.I)})
    robots = robots_tag['content'].strip() if robots_tag and robots_tag.get('content') else ''
    result['meta_robots'] = robots
    viewport_tag = soup.find('meta', attrs={'name': re.compile('viewport', re.I)})
    viewport = viewport_tag['content'].strip() if viewport_tag and viewport_tag.get('content') else ''
    result['viewport'] = viewport
    json_ld = []
    for s in soup.find_all('script', type='application/ld+json'):
        if s.string:
            try:
                json_ld.append(json.loads(s.string))
            except Exception:
                json_ld.append({'raw': s.string[:500]})
    result['json_ld'] = json_ld
    imgs = soup.find_all('img')
    imgs_missing_alt = [i.get('src') for i in imgs if not i.get('alt')]
    result['images'] = {'total': len(imgs), 'missing_alt_count': len(imgs_missing_alt), 'missing_alt_srcs': imgs_missing_alt[:50]}
    links = [a.get('href') for a in soup.find_all('a', href=True)]
    result['links'] = {'count': len(links)}
    body = soup.body
    if body:
        body_text = body.get_text(separator=' ', strip=True)
        words = re.findall(r"\w+", body_text)
        result['word_count'] = len(words)
    else:
        result['word_count'] = 0
    hreflangs = []
    for link in soup.find_all('link', attrs={'rel': re.compile('alternate', re.I)}):
        hreflang = link.get('hreflang')
        href = link.get('href')
        if hreflang and href:
            hreflangs.append({'hreflang': hreflang, 'href': href})
    result['hreflangs'] = hreflangs
    return result

def validate_json_ld(json_ld_blocks):
    issues = []
    for i, b in enumerate(json_ld_blocks):
        if isinstance(b, dict):
            if '@context' not in b and '@graph' not in b:
                issues.append({'index': i, 'issue': 'missing @context'})
            if '@type' not in b and '@graph' not in b:
                issues.append({'index': i, 'issue': 'missing @type'})
        else:
            issues.append({'index': i, 'issue': 'not a dict'})
    return issues

def canonical_chain_check(pages):
    chains = []
    for url, data in pages.items():
        c = data.get('analysis', {}).get('canonical')
        if not c:
            continue
        chain = [url]
        nxt = c
        while nxt and nxt != chain[-1] and nxt in pages and len(chain) < 20:
            chain.append(nxt)
            nxt = pages[nxt].get('analysis', {}).get('canonical')
        if len(chain) > 1:
            chains.append(chain)
    return chains

async def pagespeed_insights(url, api_key, strategy='mobile'):
    if not api_key:
        return {'error': 'no_api_key'}
    api = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
    params = {'url': url, 'key': api_key, 'strategy': strategy}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api, params=params, timeout=30) as resp:
                j = await resp.json()
                return j
        except Exception as e:
            return {'error': str(e)}

class SEOCrawler:
    def __init__(self, seed_url, max_pages=DEFAULT_MAX_PAGES):
        self.seed = seed_url
        self.parsed = urlparse(seed_url)
        self.to_visit = deque()
        self.seen = set()
        self.results = {}
        self.max_pages = max_pages
    def enqueue(self, url):
        if not url or url in self.seen or len(self.seen) >= self.max_pages: return
        self.seen.add(url); self.to_visit.append(url)
    async def run(self):
        if not aiohttp:
            raise RuntimeError("aiohttp is required to run the crawler. Install via pip.")
        async with aiohttp.ClientSession() as session:
            self.enqueue(self.seed)
            sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
            async def worker():
                while self.to_visit:
                    url = self.to_visit.popleft()
                    async with sem:
                        resp = await fetch(session, url)
                    self.results[url] = {'fetch': resp}
                    if resp.get('status') and resp.get('text'):
                        analysis = analyze_html(url, resp['text'])
                        self.results[url]['analysis'] = analysis
                        soup = BeautifulSoup(resp['text'], 'lxml')
                        for a in soup.find_all('a', href=True):
                            n = normalize_url(url, a['href'])
                            if not n: continue
                            if is_same_origin(self.seed, n) and n not in self.seen and len(self.seen) < self.max_pages:
                                self.enqueue(n)
            tasks = [asyncio.create_task(worker()) for _ in range(MAX_CONCURRENT_REQUESTS)]
            await asyncio.gather(*tasks)

def import_lighthouse_json(lh_path):
    if not os.path.exists(lh_path):
        return {}
    try:
        with open(lh_path, 'r', encoding='utf-8') as f:
            j = json.load(f)
    except Exception:
        return {}
    out = {}
    if isinstance(j, dict) and 'finalUrl' in j:
        url = j.get('finalUrl')
        cats = j.get('categories', {})
        scores = {k: (v.get('score') * 100 if isinstance(v.get('score'), (int,float)) else None) for k,v in cats.items()}
        out[url] = {'scores': scores}
    if isinstance(j, list):
        for item in j:
            u = item.get('finalUrl')
            if u:
                cats = item.get('categories', {})
                scores = {k: (v.get('score') * 100 if isinstance(v.get('score'), (int,float)) else None) for k,v in cats.items()}
                out[u] = {'scores': scores}
    return out

async def run_audit(seed_url, output_path=None, max_pages=100, pagespeed_key=None, generate_pdf=None, generate_pptx_path=None, write_web_ui=False, lighthouse_json=None):
    if not validators or not validators.url(seed_url):
        raise ValueError('Please provide a valid URL and ensure validators package is installed')
    crawler = SEOCrawler(seed_url, max_pages=max_pages)
    await crawler.run()
    report = {'site': seed_url, 'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'robots': None, 'pages': {}}
    for url, data in crawler.results.items():
        page = {}
        page['fetch'] = data.get('fetch')
        page['analysis'] = data.get('analysis')
        if data.get('analysis') and data.get('fetch'):
            page['scores'] = score_page(page['analysis'], page['fetch'])
        report['pages'][url] = page
    report['canonical_chains'] = canonical_chain_check(report['pages'])
    all_json_ld_issues = {}
    for url, p in report['pages'].items():
        if p.get('analysis'):
            issues = validate_json_ld(p['analysis'].get('json_ld', []))
            if issues:
                all_json_ld_issues[url] = issues
    report['json_ld_issues'] = all_json_ld_issues
    if pagespeed_key:
        report['pagespeed'] = {}
        candidates = [seed_url] + list(report['pages'].keys())[:4]
        tasks = [pagespeed_insights(p, pagespeed_key, strategy='mobile') for p in candidates]
        results = await asyncio.gather(*tasks)
        for p, r in zip(candidates, results):
            report['pagespeed'][p] = r
    if lighthouse_json:
        report['lighthouse'] = import_lighthouse_json(lighthouse_json)
    # write output JSON
    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    if write_web_ui:
        scaffold_web_ui(report)
    return report

def scaffold_web_ui(report, target_dir='web_ui'):
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

def score_page(analysis, fetch_info):
    score = 100
    reasons = []
    tlen = analysis.get('title', {}).get('length', 0)
    if tlen == 0:
        score -= 20; reasons.append('Missing title')
    if analysis.get('meta_description', {}).get('length', 0) == 0:
        score -= 10; reasons.append('Missing meta description')
    if analysis.get('h1', {}).get('count', 0) == 0:
        score -= 10; reasons.append('Missing H1')
    if analysis.get('word_count', 0) < 100:
        score -= 5; reasons.append('Low word count (<100)')
    status = fetch_info.get('status')
    if status is None or (status and status >= 400):
        score = 0; reasons.append(f'HTTP error: {status}')
    return {'score': max(0, score), 'reasons': reasons}

def cli():
    parser = argparse.ArgumentParser(description='Run extended SEO audit')
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', default='reports/report.json')
    parser.add_argument('--pages', type=int, default=100)
    parser.add_argument('--pagespeed-key', default=None)
    parser.add_argument('--lighthouse-json', default=None, help='Path to a Lighthouse JSON file to import into the report')
    parser.add_argument('--web-ui', action='store_true')
    args = parser.parse_args()
    report = asyncio.run(run_audit(args.url, output_path=args.output, max_pages=args.pages, pagespeed_key=args.pagespeed_key, write_web_ui=args.web_ui, lighthouse_json=args.lighthouse_json))
    print('Audit complete. Output:', args.output)

if __name__ == '__main__':
    cli()
# --- END seo_audit_tool_extended.py ---
