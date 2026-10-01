"""Private invoice-level validation of payments, balanced ledgers and deliveries."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timedelta
import re
from vic_apps.communications import file_record
from vic_apps.payment_projects import receipt_text,report_text


def selected(initial,variant):
    w=initial['world'];objects=initial['domain']['objects'];result=[]
    for bill in w['bills']:
        if bill['id'] not in w['batch_bills']:continue
        p=objects[bill['payee']]
        matches=initial['task_id']==46 or {'A':w['letter'].lower() in p['name'].lower(),'B':int(p['account'][-1])%2==0,'C':bill['cents']<w['threshold']}[variant]
        if matches:result.append(bill)
    return result


def memo(initial,bill,variant):
    if initial['task_id']==56:return bill['note']
    account=initial['domain']['objects'][bill['payee']]['account']
    return {'A':account[-4:],'B':account[:4],'C':account[:4]+'*'*(len(account)-8)+account[-4:]}[variant]


def evaluate(initial,final,variant,events):
    checks=[]
    def check(id,value):checks.append(dict(id=id,passed=bool(value)))
    for k in initial.keys()-{'world','domain','next_transfer','next_receipt'}:check('input:'+k,initial[k]==final.get(k))
    for k in initial['domain'].keys()-{'balances','ledger','files'}:check('input:domain:'+k,initial['domain'][k]==final['domain'].get(k))
    start=initial['world'];w=final['world']
    for k in start.keys()-{'transfers','bill_links','report','receipts','discussion'}:check('input:world:'+k,start[k]==w.get(k))
    payments={k:t for k,t in w['transfers'].items() if k not in start['transfers']}
    expected_bills=selected(initial,variant)
    check('payment_count',len(payments)==len(expected_bills))
    check('historical_payments',all(w['transfers'].get(k)==t for k,t in start['transfers'].items()))
    balances=deepcopy(initial['domain']['balances']);ledger=deepcopy(initial['domain']['ledger']);files=deepcopy(initial['domain']['files']);links=deepcopy(start['bill_links'])
    for bill in expected_bills:
        matches=[(key,t) for key,t in payments.items() if t['bill']==bill['id']]
        check(bill['id']+':one_payment',len(matches)==1)
        balances[bill['payer']]-=bill['cents'];balances[bill['payee']]+=bill['cents']
        if len(matches)!=1:continue
        key,t=matches[0];valid=bool(re.fullmatch(r'PAY-\d{4}',key));check(bill['id']+':payment_id',valid)
        if not valid:continue
        time=(datetime.fromisoformat(start['reference_time'])+timedelta(seconds=int(key[4:]))).isoformat()
        expected=dict(id=key,bill=bill['id'],payer=bill['payer'],payee=bill['payee'],cents=bill['cents'],memo=memo(initial,bill,variant),status='posted',occurred_at=time)
        check(bill['id']+':payment_fields',t==expected);links[bill['id']]=key
        ledger.extend([dict(transfer=key,account=bill['payer'],cents=-bill['cents'],counterparty=bill['payee']),dict(transfer=key,account=bill['payee'],cents=bill['cents'],counterparty=bill['payer'])])
        files['transfer-'+key]=file_record(key+'-付款回执.md',receipt_text(initial,expected))
    check('bill_receipts',w['bill_links']==links)
    check('balances',final['domain']['balances']==balances)
    def legs(items):return Counter((r['transfer'],r['account'],r['cents'],r['counterparty']) for r in items)
    check('double_entry_ledger',legs(final['domain']['ledger'])==legs(ledger))
    if initial['task_id']==46:check('no_unrequested_report',w['report'] is None and not w['receipts'])
    else:
        rows=[dict(bill=id,transfer=links.get(id,''),reason='' if id in links else start['unpaid_reason']) for id in start['batch_bills']]
        reference=deepcopy(initial);reference['domain']['balances']=balances
        body=report_text(reference,rows)
        check('reconciliation',w['report']==dict(rows=rows,body=body))
        files['payment-report']=file_record('十月付款对账清单.md',body)
        check('one_finance_notification',len(w['receipts'])==1)
        for r in w['receipts']:check('notification_recipient_and_body',r['recipient']==start['report_recipient'] and r['body']==body)
    check('actual_files',final['domain']['files']==files);check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
