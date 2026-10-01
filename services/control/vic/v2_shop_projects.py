"""Private validation of actual shopping orders and state-linked handovers."""
from copy import deepcopy
from vic_apps.communications import file_record
from vic_apps.shop_projects import order_text,handover_text,request_rows


def selected(initial,variant):
    result={};objects=initial['domain']['objects']
    for need in initial['world']['needs']:
        products=[objects[item['id']] for item in initial['items']]
        candidates=[p for p in products if p['category']==need['category'] and p['spec']==need['spec'] and p['price']<=need['budget'] and p['stock']>=need['quantity']]
        candidates.sort(key=lambda p:p['record_code'])
        key={'A':lambda p:p['rating'],'B':lambda p:p['price'],'C':lambda p:p['stock']}[variant]
        result[need['id']]=sorted(candidates,key=key,reverse=variant!='C')[0]['id']
    return result


def inventory(initial,variant):
    w=initial['world'];cart=deepcopy(w['cart']);favorites=set(w['favorites'])
    for r in w['requests']:
        for id in r['products']:
            if r['label'] not in initial['domain']['objects'][id]['tags']:continue
            if variant=='A':cart.setdefault(id,r['quantities'][id])
            elif variant=='B':cart.pop(id,None)
            else:favorites.add(id)
    return cart,favorites


def evaluate(initial,final,variant,events):
    checks=[]
    def check(key,value):checks.append(dict(id=key,passed=bool(value)))
    for key in initial.keys()-{'world','domain','next_order','next_receipt'}:check('input:'+key,initial[key]==final.get(key))
    for key in initial['domain'].keys()-{'files'}:check('input:domain:'+key,initial['domain'][key]==final['domain'].get(key))
    start=initial['world'];w=final['world']
    for key in start.keys()-{'cart','favorites','stock','orders','handovers','receipts','discussion'}:check('input:world:'+key,start[key]==w.get(key))
    files=deepcopy(initial['domain']['files']);stock=deepcopy(start['stock'])
    if initial['task_id']==52:
        choices=selected(initial,variant)
        check('order_count',len(w['orders'])==len(start['departments']))
        for dep in start['departments']:
            orders=[o for o in w['orders'].values() if o['department']==dep['id']]
            check(dep['id']+':one_order',len(orders)==1)
            lines={choices[n['id']]:n['quantity'] for n in start['needs'] if n['department']==dep['id']}
            for id,q in lines.items():stock[id]-=q
            if len(orders)!=1:continue
            order=orders[0];id=order['id']
            expected=dict(id=id,department=dep['id'],address=dep['address'],lines=lines,status='confirmed',confirmation='SIM-'+id)
            check(dep['id']+':order',order==expected)
            files['order-'+id]=file_record(id+'-订单回执.md',order_text(initial,expected))
        check('unrelated_cart',w['cart']==start['cart']);check('unrelated_favorites',set(w['favorites'])==set(start['favorites']))
        check('no_handovers',not w['handovers'] and not w['receipts'])
    else:
        cart,favorites=inventory(initial,variant)
        check('final_cart',w['cart']==cart);check('final_favorites',set(w['favorites'])==favorites)
        check('no_orders',w['orders']=={})
        check('handover_set',set(w['handovers'])=={r['id'] for r in start['requests']})
        reference=deepcopy(initial);reference['world'].update(cart=cart,favorites=sorted(favorites))
        for r in start['requests']:
            rows=request_rows(reference,r);body=handover_text(initial,r,rows)
            check(r['id']+':handover',w['handovers'].get(r['id'])==dict(rows=rows,body=body))
            files['handover-'+r['id']]=file_record(r['id']+'-采购交接单.md',body)
            receipts=[x for x in w['receipts'] if x['request']==r['id']]
            check(r['id']+':one_receipt',len(receipts)==1)
            for receipt in receipts:check(r['id']+':recipient_and_body',receipt['recipient']==r['recipient'] and receipt['body']==body)
        check('receipt_count',len(w['receipts'])==len(start['requests']))
    check('inventory',w['stock']==stock)
    check('unique_favorites',len(w['favorites'])==len(set(w['favorites'])))
    check('real_files',final['domain']['files']==files);check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
