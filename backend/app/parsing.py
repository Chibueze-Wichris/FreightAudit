import csv, io, re, hashlib
from pypdf import PdfReader
from openpyxl import load_workbook
from fastapi import HTTPException
ALIASES={'invoice':'reference','invoice_number':'reference','invoice_no':'reference','reference':'reference','carrier':'carrier','carrier_name':'carrier','date':'invoice_date','invoice_date':'invoice_date','total':'billed_total','billed_total':'billed_total','amount':'billed_total','linehaul':'linehaul','line_haul':'linehaul','fuel':'fuel_amount','fuel_amount':'fuel_amount','fuel_surcharge':'fuel_amount','fuel_percent':'fuel_percent','fuel_pct':'fuel_percent','lane':'lane'}
REQUIRED={'reference','carrier','invoice_date','billed_total'}
def normalize(r):
    row={}
    for k,v in r.items():
        key=ALIASES.get(re.sub(r'[^a-z0-9]+','_',str(k or '').strip().lower()).strip('_'))
        if key and v is not None: row[key]=v
    for k in ('billed_total','linehaul','fuel_amount','fuel_percent'):
        if k in row:
            try: row[k]=float(str(row[k]).replace(',','').replace('$','').replace('%','').strip() or 0)
            except ValueError: raise HTTPException(422, f"Invalid numeric value in {k}")
    missing=REQUIRED-row.keys()
    if missing: raise HTTPException(422, 'Missing required columns: '+', '.join(sorted(missing)))
    row.setdefault('linehaul',0.0); row.setdefault('fuel_amount',0.0); row.setdefault('fuel_percent',0.0); row.setdefault('lane',''); row.setdefault('source_page',1); row['reference']=str(row['reference']).strip(); row['carrier']=str(row['carrier']).strip(); row['invoice_date']=str(row['invoice_date'])[:10]
    row['fingerprint']=hashlib.sha256('|'.join([row['carrier'].casefold(),row['reference'].casefold(),row['invoice_date'],f"{row['billed_total']:.2f}"]).encode()).hexdigest()
    return row

def parse_upload(name: str, content: bytes):
    ext=name.rsplit('.',1)[-1].lower()
    try:
        if ext=='csv': rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        elif ext in ('xlsx','xlsm'):
            ws=load_workbook(io.BytesIO(content),read_only=True,data_only=True).active
            vals=list(ws.values); headers=[str(x or '') for x in vals[0]]; rows=[dict(zip(headers,r)) for r in vals[1:] if any(v is not None for v in r)]
        elif ext=='pdf':
            reader=PdfReader(io.BytesIO(content)); rows=[]
            for page_no,p in enumerate(reader.pages,1):
                text=p.extract_text() or ''
                if not text.strip(): raise HTTPException(422, f'Page {page_no} has no selectable text. Scanned PDFs are not supported in this MVP.')
                # No guessed PDF field extraction: require structured rows for dependable calculation.
                raise HTTPException(422,'Text was found, but invoice PDF field extraction is not enabled in this MVP. Export invoice line data to CSV/XLSX first.')
        else: raise HTTPException(415,'Supported formats: CSV, XLSX, text-based PDF (PDF text extraction is currently validation-only).')
    except HTTPException: raise
    except Exception as e: raise HTTPException(422, f'Could not read file: {e}')
    if not rows: raise HTTPException(422,'No invoice rows found.')
    if len(rows)>5000: raise HTTPException(413,'A file may contain at most 5,000 invoice rows.')
    return [normalize(r) for r in rows]
