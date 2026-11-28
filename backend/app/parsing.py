import csv, io, re, hashlib
from datetime import date
from pypdf import PdfReader
from openpyxl import load_workbook
from fastapi import HTTPException
from . import llm
from .llm import map_invoice_columns, extract_invoice_pdf, extract_invoice_spreadsheet

ALIASES = {
    'invoice': 'reference', 'invoice_number': 'reference', 'invoice_no': 'reference',
    'inv_no': 'reference', 'inv_number': 'reference', 'inv': 'reference',
    'reference': 'reference', 'bill_no': 'reference', 'bill_number': 'reference',
    'pro': 'reference', 'pro_number': 'reference', 'bol': 'reference',
    'bol_number': 'reference', 'load_id': 'reference', 'shipment_id': 'reference', 'doc_no': 'reference',
    'carrier': 'carrier', 'carrier_name': 'carrier', 'scac': 'carrier',
    'vendor': 'carrier', 'vendor_name': 'carrier', 'trucker': 'carrier', 'hauler': 'carrier',
    'date': 'invoice_date', 'invoice_date': 'invoice_date', 'inv_date': 'invoice_date',
    'bill_date': 'invoice_date', 'ship_date': 'invoice_date', 'pickup_date': 'invoice_date', 'delivery_date': 'invoice_date',
    'total': 'billed_total', 'billed_total': 'billed_total', 'amount': 'billed_total',
    'total_amount': 'billed_total', 'invoice_total': 'billed_total', 'grand_total': 'billed_total',
    'net_amount': 'billed_total', 'total_due': 'billed_total', 'amount_due': 'billed_total', 'total_charges': 'billed_total',
    'linehaul': 'linehaul', 'line_haul': 'linehaul', 'base_rate': 'linehaul',
    'freight_charge': 'linehaul', 'freight_charges': 'linehaul', 'base_freight': 'linehaul',
    'fuel': 'fuel_amount', 'fuel_amount': 'fuel_amount', 'fuel_surcharge': 'fuel_amount',
    'fsc': 'fuel_amount', 'fsc_amount': 'fuel_amount', 'fuel_charge': 'fuel_amount',
    'fuel_percent': 'fuel_percent', 'fuel_pct': 'fuel_percent', 'fsc_percent': 'fuel_percent', 'fsc_pct': 'fuel_percent',
    'lane': 'lane', 'route': 'lane',
}
REQUIRED = set()


def normalize(r, column_map: dict[str, str] | None = None, default_ref: str = 'INV-UNKNOWN'):
    row = {}
    for k, v in r.items():
        if column_map and str(k) in column_map:
            key = column_map[str(k)]
        else:
            key = ALIASES.get(re.sub(r'[^a-z0-9]+', '_', str(k or '').strip().lower()).strip('_'))
        if key and v is not None and str(v).strip() != '':
            row[key] = v
    for k in ('billed_total', 'linehaul', 'fuel_amount', 'fuel_percent'):
        if k in row:
            try:
                row[k] = float(str(row[k]).replace(',', '').replace('$', '').replace('%', '').strip() or 0)
            except ValueError:
                raise HTTPException(422, f"Invalid numeric value in {k}")
    missing = REQUIRED - row.keys()
    if missing:
        raise HTTPException(422, 'Missing required columns: ' + ', '.join(sorted(missing)))
    row.setdefault('billed_total', 0.0)
    row.setdefault('reference', default_ref)
    row.setdefault('carrier', 'Unknown Carrier')
    row.setdefault('invoice_date', date.today().isoformat())
    row.setdefault('linehaul', 0.0)
    row.setdefault('fuel_amount', 0.0)
    row.setdefault('fuel_percent', 0.0)
    row.setdefault('lane', '')
    row.setdefault('source_page', 1)
    row['reference'] = str(row['reference']).strip()
    row['carrier'] = str(row['carrier']).strip()
    row['invoice_date'] = str(row['invoice_date'])[:10]
    row['fingerprint'] = hashlib.sha256(
        '|'.join([row['carrier'].casefold(), row['reference'].casefold(), row['invoice_date'], f"{row['billed_total']:.2f}"]).encode()
    ).hexdigest()
    return row


def parse_upload(name: str, content: bytes):
    ext = name.rsplit('.', 1)[-1].lower()
    headers: list[str] = []
    try:
        if ext == 'csv':
            reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
            headers = list(reader.fieldnames or [])
            rows = list(reader)
        elif ext in ('xlsx', 'xlsm'):
            ws = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
            vals = list(ws.values)
            headers = [str(x or '') for x in vals[0]]
            rows = [dict(zip(headers, r)) for r in vals[1:] if any(v is not None for v in r)]
        elif ext == 'pdf':
            reader = PdfReader(io.BytesIO(content))
            pages = []
            for page_no, p in enumerate(reader.pages, 1):
                text = p.extract_text() or ''
                if not text.strip():
                    raise HTTPException(422, f'Page {page_no} has no selectable text. Scanned PDFs are not supported.')
                pages.append((page_no, text))
            rows = extract_invoice_pdf(pages)
            if not rows:
                detail = 'Could not extract invoice rows from PDF.'
                if llm.LAST_ERROR:
                    detail = f'{detail} ({llm.LAST_ERROR})'
                raise HTTPException(422, detail)
        else:
            raise HTTPException(415, 'Supported formats: CSV, XLSX, text-based PDF.')
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, f'Could not read file: {e}')

    if not rows:
        raise HTTPException(422, 'No invoice rows found.')
    if len(rows) > 5000:
        raise HTTPException(413, 'A file may contain at most 5,000 invoice rows.')

    if ext in ('csv', 'xlsx', 'xlsm'):
        raw_lines = (
            content.decode('utf-8-sig').splitlines()
            if ext == 'csv'
            else [','.join(str(c or '') for c in r) for r in vals[:120]]
        )
        raw_text = '\n'.join(ln for ln in raw_lines if ln.replace(',', '').strip())[:15000]
        ai_rows = extract_invoice_spreadsheet(raw_text)
        if ai_rows:
            return [normalize(r, default_ref=name) for r in ai_rows]
        if headers and any(h.strip() for h in headers):
            ai_map = map_invoice_columns(headers, rows[:3])
            if ai_map:
                return [normalize(r, column_map=ai_map, default_ref=name) for r in rows]

    normalized = [normalize(r, default_ref=name) for r in rows]
    if all(r['billed_total'] == 0.0 for r in normalized) and llm.LAST_ERROR:
        raise HTTPException(422, f'AI extraction failed: {llm.LAST_ERROR}')
    return normalized
