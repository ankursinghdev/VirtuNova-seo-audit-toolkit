# VirtuNova-seo-audit-toolkit

Automated SEO Audit Toolkit by VirtuNova — Where Creativity, Technology, and Strategy Converge

[![SEO Audit Workflow](https://github.com/ankursinghdev/VirtuNova-seo-audit-toolkit/actions/workflows/seo_audit.yml/badge.svg)](https://github.com/ankursinghdev/VirtuNova-seo-audit-toolkit/actions)

## Quickstart

```bash
git clone https://github.com/ankursinghdev/VirtuNova-seo-audit-toolkit.git
cd VirtuNova-seo-audit-toolkit
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run an audit:

```bash
python seo_audit_tool_extended.py --url https://example.com --output reports/report.json --pages 100 --pagespeed-key YOUR_PAGESPEED_KEY --web-ui
```

Add your PageSpeed API key as a GitHub secret named `PAGESPEED_KEY`.
