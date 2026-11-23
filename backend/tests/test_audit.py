from app.audit import audit_invoice

def base():
 return {'reference':'X-1','carrier':'RoadCo','invoice_date':'2026-11-01','billed_total':1250,'linehaul':1000,'fuel_amount':250,'fuel_percent':25,'fingerprint':'same','file_name':'sample.csv','source_page':1}
def test_fuel_variance_uses_approved_terms_and_cents():
 f=audit_invoice(base(),{'id':3,'source_name':'terms.pdf','terms':{'fuel_percent':20}},set())
 assert len(f)==1 and f[0]['rule']=='fuel' and f[0]['expected']==200 and f[0]['variance']==50
 assert f[0]['evidence']['contract_id']==3

def test_no_fuel_flag_when_invoice_at_or_below_rate():
 row=base();row['fuel_amount']=200
 assert audit_invoice(row,{'terms':{'fuel_percent':20}},set())==[]

def test_duplicate_flag_is_evidence_bearing():
 f=audit_invoice(base(),{'terms':{}},{'same'})
 assert f[0]['rule']=='duplicate' and f[0]['variance']==1250 and f[0]['evidence']['reference']=='X-1'
