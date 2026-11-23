import os, io, re, jwt
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from pwdlib import PasswordHash
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from .db import Base, engine, SessionLocal
from . import models as m
from .audit import audit_invoice, cents
from .parsing import parse_upload

Base.metadata.create_all(bind=engine)
app=FastAPI(title='FreightAudit AI', version='0.1.0')
origins=os.getenv('CORS_ORIGINS','http://localhost:3000').split(',')
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_origin_regex=r'https://.*\.e2b\.app',allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
passwords=PasswordHash.recommended(); SECRET=os.getenv('JWT_SECRET')
def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()
def token_for(u):
    if not SECRET: raise HTTPException(503,'JWT_SECRET is not configured')
    return jwt.encode({'sub':str(u.id),'exp':datetime.now(timezone.utc)+timedelta(hours=12)},SECRET,algorithm='HS256')
from fastapi import Header
def actor(authorization:str|None=Header(default=None), session:Session=Depends(db)):
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Sign in required')
    try: payload=jwt.decode(authorization[7:],SECRET,algorithms=['HS256']); user=session.get(m.User,int(payload['sub']))
    except Exception: user=None
    if not user: raise HTTPException(401,'Session expired or invalid')
    return user
class Credentials(BaseModel): email:EmailStr; password:str
class ContractCreate(BaseModel): carrier:str; source_name:str='Manual terms'; fuel_percent:float|None=None
class Approve(BaseModel): fuel_percent:float|None=None
class Review(BaseModel): status:str
class ClaimRequest(BaseModel): body:str|None=None
@app.get('/health')
def health(): return {'ok':True}
@app.post('/auth/register')
def register(data:Credentials,s:Session=Depends(db)):
    if len(data.password)<12: raise HTTPException(422,'Password must be at least 12 characters')
    if s.query(m.User).count(): raise HTTPException(403,'Workspace is already initialized; ask its administrator to create users.')
    u=m.User(email=data.email.lower(),password_hash=passwords.hash(data.password));s.add(u);s.commit();s.refresh(u);return {'access_token':token_for(u),'token_type':'bearer','email':u.email}
@app.post('/auth/login')
def login(data:Credentials,s:Session=Depends(db)):
    u=s.query(m.User).filter_by(email=data.email.lower()).first()
    if not u or not passwords.verify(data.password,u.password_hash): raise HTTPException(401,'Email or password incorrect')
    return {'access_token':token_for(u),'token_type':'bearer','email':u.email}
@app.get('/auth/me')
def me(u:m.User=Depends(actor)): return {'email':u.email}
@app.post('/contracts')
def create_contract(data:ContractCreate,s:Session=Depends(db),u:m.User=Depends(actor)):
    c=m.Contract(carrier=data.carrier,source_name=data.source_name,status='draft',terms={'fuel_percent':data.fuel_percent} if data.fuel_percent is not None else {})
    s.add(c);s.commit();s.refresh(c);return contract_out(c)
@app.post('/contracts/propose')
async def propose_contract(carrier:str=Form(...),file:UploadFile=File(...),s:Session=Depends(db),u:m.User=Depends(actor)):
    raw=await file.read(25*1024*1024+1)
    if len(raw)>25*1024*1024: raise HTTPException(413,'Maximum file size is 25 MB')
    if not (file.filename or '').lower().endswith('.pdf'): raise HTTPException(415,'Upload a text-based PDF rate sheet')
    from pypdf import PdfReader
    try:
        reader=PdfReader(io.BytesIO(raw)); proposed=None; page_no=None
        pattern=re.compile(r'(?:fuel\s*(?:surcharge|adjustment|rate)?|fuel\s+index)[^\n%]{0,70}?(\d+(?:\.\d+)?)\s*(?:%|percent)',re.I)
        for idx,page in enumerate(reader.pages,1):
            text=page.extract_text() or ''
            if not text.strip(): raise HTTPException(422,f'Page {idx} has no selectable text. Scanned PDFs are not supported.')
            match=pattern.search(text)
            if match: proposed=float(match.group(1));page_no=idx;break
    except HTTPException: raise
    except Exception as e: raise HTTPException(422,f'Could not read rate sheet: {e}')
    c=m.Contract(carrier=carrier.strip(),source_name=file.filename or 'Uploaded rate sheet',status='draft',terms={'fuel_percent':proposed,'proposal_page':page_no,'review_required':True})
    s.add(c);s.commit();s.refresh(c);return {**contract_out(c),'proposal_note':'Rule-based text proposal only. Verify the rate and cited page before approval.'}
@app.get('/contracts')
def contracts(s:Session=Depends(db),u:m.User=Depends(actor)): return [contract_out(x) for x in s.query(m.Contract).order_by(m.Contract.id.desc()).all()]
def contract_out(c): return {'id':c.id,'carrier':c.carrier,'status':c.status,'terms':c.terms,'source_name':c.source_name}
@app.post('/contracts/{cid}/approve')
def approve(cid:int,data:Approve,s:Session=Depends(db),u:m.User=Depends(actor)):
    c=s.get(m.Contract,cid)
    if not c: raise HTTPException(404,'Contract not found')
    if data.fuel_percent is not None: c.terms={**c.terms,'fuel_percent':data.fuel_percent}
    c.status='approved';s.commit();return contract_out(c)
@app.post('/uploads/preview')
async def preview(file:UploadFile=File(...),u:m.User=Depends(actor)):
    raw=await file.read(25*1024*1024+1)
    if len(raw)>25*1024*1024: raise HTTPException(413,'Maximum file size is 25 MB')
    rows=parse_upload(file.filename or 'upload',raw)
    return {'file_name':file.filename,'rows':rows,'count':len(rows),'notice':'Preview only. Nothing is persisted until audit is confirmed.'}
class AuditRequest(BaseModel): file_name:str; rows:list[dict]
@app.post('/audits')
def run_audit(req:AuditRequest,s:Session=Depends(db),u:m.User=Depends(actor)):
    if not req.rows or len(req.rows)>5000: raise HTTPException(422,'Provide between 1 and 5,000 previewed rows')
    for row in req.rows:
        if not {'reference','carrier','invoice_date','billed_total','fingerprint'}<=row.keys(): raise HTTPException(422,'Invalid preview payload')
    results=[]
    for row in req.rows:
        inv=m.Invoice(reference=str(row['reference']),carrier=str(row['carrier']),invoice_date=str(row['invoice_date']),billed_total=float(row['billed_total']),linehaul=float(row.get('linehaul',0)),fuel_amount=float(row.get('fuel_amount',0)),fuel_percent=float(row.get('fuel_percent',0)),lane=str(row.get('lane','')),file_name=req.file_name,source_page=int(row.get('source_page',1)),fingerprint=row['fingerprint'])
        prior={x.fingerprint for x in s.query(m.Invoice).filter_by(carrier=inv.carrier,reference=inv.reference).all()}
        s.add(inv);s.flush()
        contract=s.query(m.Contract).filter_by(carrier=inv.carrier,status='approved').order_by(m.Contract.id.desc()).first()
        contract_data={'id':contract.id,'source_name':contract.source_name,'terms':contract.terms} if contract else {'terms':{}}
        findings=audit_invoice({**row,'file_name':req.file_name},contract_data,prior)
        for f in findings:
            obj=m.Finding(invoice_id=inv.id,rule=f['rule'],variance=f['variance'],billed=f['billed'],expected=f['expected'],explanation=f['explanation'],evidence=f['evidence']);s.add(obj);s.flush();results.append(finding_out(obj,inv))
    s.commit()
    return {'invoice_count':len(req.rows),'finding_count':len(results),'potential_variance':cents(sum(x['variance'] for x in results)),'findings':results}
@app.get('/audits')
def list_audits(s:Session=Depends(db),u:m.User=Depends(actor)):
    invs=s.query(m.Invoice).order_by(m.Invoice.id.desc()).limit(300).all(); out=[]
    for i in invs:
        fs=s.query(m.Finding).filter_by(invoice_id=i.id).all();out.append({'id':i.id,'reference':i.reference,'carrier':i.carrier,'invoice_date':i.invoice_date,'billed_total':i.billed_total,'file_name':i.file_name,'findings':[finding_out(f,i) for f in fs]})
    return out
def finding_out(f,i): return {'id':f.id,'invoice_id':i.id,'reference':i.reference,'carrier':i.carrier,'invoice_date':i.invoice_date,'rule':f.rule,'variance':f.variance,'billed':f.billed,'expected':f.expected,'explanation':f.explanation,'evidence':f.evidence,'status':f.status}
@app.patch('/findings/{fid}')
def review(fid:int,data:Review,s:Session=Depends(db),u:m.User=Depends(actor)):
    if data.status not in ('open','accepted','dismissed'): raise HTTPException(422,'Invalid decision')
    f=s.get(m.Finding,fid)
    if not f: raise HTTPException(404,'Finding not found')
    f.status=data.status;s.commit();return {'id':f.id,'status':f.status}
@app.post('/findings/{fid}/claim.pdf')
def claim_pdf(fid:int,request:ClaimRequest,s:Session=Depends(db),u:m.User=Depends(actor)): 
    f=s.get(m.Finding,fid)
    if not f: raise HTTPException(404,'Finding not found')
    inv=s.get(m.Invoice,f.invoice_id)
    default_body=f"Subject: Dispute of invoice {inv.reference}\n\nDear {inv.carrier},\n\nWe are requesting a review of invoice {inv.reference}, dated {inv.invoice_date}. Our review identified a potential {f.rule} variance of ${f.variance:,.2f}.\n\nBilled amount reviewed: ${f.billed:,.2f}\nExpected amount under reviewed terms: ${f.expected:,.2f}\n\nBasis: {f.explanation}\n\nEvidence reference: {f.evidence}\n\nPlease review and provide a corrected invoice or supporting documentation. This draft is subject to our review and is not yet sent.\n\nRegards,\nFreight Accounts Payable"
    body=(request.body or default_body).strip()
    if not body or len(body)>20000: raise HTTPException(422,'Draft must contain 1 to 20,000 characters')
    if any(ord(ch)>255 for ch in body): body=body.encode('latin-1','replace').decode('latin-1')
    claim=m.Claim(finding_id=f.id,body=body);s.add(claim);s.commit()
    pdf=FPDF();pdf.add_page();pdf.set_font('Helvetica','B',16);pdf.cell(0,10,'Freight invoice dispute draft',new_x=XPos.LMARGIN,new_y=YPos.NEXT);pdf.set_font('Helvetica',size=11)
    for para in body.split('\n'): pdf.multi_cell(0,7,para or ' ',new_x=XPos.LMARGIN,new_y=YPos.NEXT)
    data=bytes(pdf.output());return StreamingResponse(io.BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="dispute-{inv.reference}.pdf"'})
