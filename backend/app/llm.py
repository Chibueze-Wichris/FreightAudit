import json
import os
import time
import urllib.request
import urllib.error


LAST_ERROR: str | None = None


def _call_gemini(prompt: str) -> dict | list | None:
    global LAST_ERROR
    LAST_ERROR = None
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        LAST_ERROR = 'GEMINI_API_KEY is not set'
        return None
    env_model = os.getenv('GEMINI_MODEL')
    models = [env_model] if env_model else ['gemini-3.8-flash', 'gemini-3.8-pro', 'gemini-3.5-flash']
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'temperature': 0.1,
        },
    }
    data_bytes = json.dumps(payload).encode('utf-8')
    for model in models:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
        for attempt in range(2):
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                text = data['candidates'][0]['content']['parts'][0]['text']
                return json.loads(text)
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8', errors='replace')[:300]
                LAST_ERROR = f'Gemini ({model}) HTTP {e.code}: {body}'
                if e.code in (429, 503) and attempt == 0:
                    time.sleep(1.5)
                    continue
                if e.code in (404, 429, 503):
                    break  # try next fallback model
                return None
            except Exception as e:
                LAST_ERROR = f'Gemini ({model}) error: {e}'
                return None
    return None


def extract_contract_terms(pages: list[tuple[int, str]], carrier: str) -> dict | None:
    snippet = '\n\n'.join(f'--- PAGE {p} ---\n{txt[:4000]}' for p, txt in pages[:5])
    prompt = f"""You are a freight contract and fuel-surcharge tariff parser.
Extract fuel surcharge terms for carrier "{carrier}" from the following document text.
Return a JSON object with these keys:
- "fuel_percent": number or null (e.g. 18.5 for 18.5%, if percentage-based)
- "fuel_per_mile": number or null (USD per mile, if mileage-based)
- "flat_fee": number or null (USD flat fee per load/carload, if applicable)
- "base_diesel_price": number or null (USD per gallon base diesel price, if stated)
- "proposal_page": integer or null (1-based page number where the main fuel rate appears)
- "summary": short string describing the extracted fuel surcharge rule

Document:
{snippet[:15000]}
"""
    res = _call_gemini(prompt)
    return res if isinstance(res, dict) else None


def map_invoice_columns(headers: list[str], sample_rows: list[dict]) -> dict[str, str] | None:
    prompt = f"""You are a freight invoice spreadsheet column mapper.
Map the spreadsheet headers to our canonical fields:
- "reference": invoice number, PRO number, BOL, or bill number
- "carrier": carrier name, vendor, or SCAC
- "invoice_date": invoice date or ship date
- "billed_total": total billed amount
- "linehaul": base freight / linehaul amount (optional)
- "fuel_amount": fuel surcharge dollar amount (optional)
- "fuel_percent": fuel surcharge percentage (optional)
- "lane": origin-destination lane (optional)

Return a JSON object mapping ONLY the matching original header strings to one of the canonical field names above.
Headers: {json.dumps(headers)}
Sample rows: {json.dumps(sample_rows[:3], default=str)}
"""
    res = _call_gemini(prompt)
    return {str(k): str(v) for k, v in res.items()} if isinstance(res, dict) else None


def extract_invoice_pdf(pages: list[tuple[int, str]]) -> list[dict] | None:
    snippet = '\n\n'.join(f'--- PAGE {p} ---\n{txt[:5000]}' for p, txt in pages[:5])
    prompt = f"""You are a freight invoice extractor.
Extract all freight invoice rows from the following PDF text.
Return a JSON array of objects, each with:
- "reference": string (invoice number / PRO / BOL)
- "carrier": string (carrier or vendor name)
- "invoice_date": string (YYYY-MM-DD format)
- "billed_total": number (total amount billed)
- "linehaul": number (base freight charge, or 0 if not listed)
- "fuel_amount": number (fuel surcharge amount, or 0 if not listed)
- "fuel_percent": number (fuel surcharge %, or 0 if not listed)
- "lane": string (origin-destination, or "")
- "source_page": integer (1-based page number)

Document:
{snippet[:15000]}
"""
    res = _call_gemini(prompt)
    return res if isinstance(res, list) else None


def extract_invoice_spreadsheet(raw_text: str) -> list[dict] | None:
    prompt = f"""You are a freight invoice extractor.
The following CSV or spreadsheet text may be a visual invoice template (with blank rows, metadata at the top, and line items below) rather than a flat table.
Extract the freight invoice(s) from it and return a JSON array of objects, each with:
- "reference": string (invoice number / PRO / BOL)
- "carrier": string (carrier, logistics company, or vendor name)
- "invoice_date": string (YYYY-MM-DD format)
- "billed_total": number (grand total / total amount billed)
- "linehaul": number (base freight charge, or 0 if not listed)
- "fuel_amount": number (fuel surcharge amount, or 0 if not listed)
- "fuel_percent": number (fuel surcharge %, or 0 if not listed)
- "lane": string (origin-destination, or "")

Spreadsheet text:
{raw_text[:15000]}
"""
    res = _call_gemini(prompt)
    return res if isinstance(res, list) else None
