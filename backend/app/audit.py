"""Deterministic audit module: normalized inputs in, evidence-bearing findings out."""
from decimal import Decimal, ROUND_HALF_UP

def cents(value): return float(Decimal(str(value or 0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
def audit_invoice(invoice: dict, contract: dict, prior_fingerprints: set[str]) -> list[dict]:
    out=[]
    if invoice['fingerprint'] in prior_fingerprints:
        out.append(dict(rule='duplicate', billed=cents(invoice['billed_total']), expected=0.0, variance=cents(invoice['billed_total']), explanation='A prior invoice has the same normalized carrier, reference, date, and total. Verify this is not a corrected or reissued bill.', evidence={'reference':invoice['reference'],'match_basis':'carrier + reference + date + billed total','source_file':invoice['file_name'],'page':invoice['source_page']}))
    terms=contract.get('terms',{})
    rate=terms.get('fuel_percent')
    if rate is not None and invoice.get('linehaul',0)>0:
        expected=cents(invoice['linehaul']*float(rate)/100); actual=cents(invoice.get('fuel_amount',0)); variance=cents(actual-expected)
        if variance>0.01:
            out.append(dict(rule='fuel', billed=actual, expected=expected, variance=variance, explanation=f"Fuel billed at {invoice.get('fuel_percent',0):.2f}% versus the approved contract rate of {float(rate):.2f}%.", evidence={'contract_id':contract.get('id'),'contract_source':contract.get('source_name'),'invoice_file':invoice['file_name'],'page':invoice['source_page'],'linehaul':cents(invoice['linehaul']),'formula':'linehaul × approved fuel percent'}))
    return out
