"""Content-safe metadata for already-final request bytes. Never rewrites bytes."""
import hashlib,json,math,re
SCHEMA='videoicl-actual-upstream-budget-metadata-v1'
MAX_TELEMETRY_JSON_BYTES=64*1048576
MAX_SAFE_NUMBER=9007199254740991
MISSING=object()
ENUMS={'thinking.type':frozenset(('enabled','disabled','adaptive')),
       'thinking.effort':frozenset(('none','off','minimal','low','medium','high','xhigh','max','on')),
       'thinking.keep':frozenset(('all','none','last')),
       'output_config.effort':frozenset(('none','off','minimal','low','medium','high','xhigh','max','on')),
       'reasoning_effort':frozenset(('none','off','minimal','low','medium','high','xhigh','max','on')),
       'reasoning.effort':frozenset(('none','off','minimal','low','medium','high','xhigh','max','on'))}
NUMBERS=('max_tokens','max_completion_tokens','max_output_tokens','thinking.budget_tokens')
BOOLEANS=('stream','parallel_tool_calls','stream_options.include_usage')
def unique(pairs):
    obj={}
    for key,value in pairs:
        if key in obj:raise ValueError('duplicate key')
        obj[key]=value
    return obj
def value_at(root,path):
    obj=root
    for key in path.split('.'):
        if not isinstance(obj,dict):return {'state':'unknown_container'}
        if key not in obj:return {'state':'absent'}
        obj=obj[key]
    if obj is None:return {'state':'null','value':None}
    if path in NUMBERS:
        if type(obj)not in(int,float):return {'state':'unknown_type'}
        if not math.isfinite(obj):return {'state':'unknown_nonfinite'}
        if not 0<=obj<=MAX_SAFE_NUMBER:return {'state':'unknown_range'}
        return {'state':'value','value':obj}
    if path in BOOLEANS:
        return {'state':'value','value':obj}if type(obj)is bool else {'state':'unknown_type'}
    if path in ENUMS:
        return {'state':'value','value':obj}if isinstance(obj,str)and obj in ENUMS[path]else {'state':'unknown_enum'}
    return {'state':'unknown_field'}
def metadata(body,expected_model):
    """Return only hashes/counts and finite standard budget fields; never raise."""
    unknown={'schema':SCHEMA,'status':'unknown'}
    result={'actual_upstream_budget_metadata':unknown}
    try:
        if type(body)is not bytes:return result
        result['actual_upstream_body_sha256']=hashlib.sha256(body).hexdigest()
        result['actual_upstream_body_bytes']=len(body)
        if len(body)>MAX_TELEMETRY_JSON_BYTES:
            result['actual_upstream_budget_metadata']={'schema':SCHEMA,'status':'unknown_size_bound'}
            return result
        data=json.loads(body,object_pairs_hook=unique)
        if not isinstance(data,dict):return result
        model=data.get('model',MISSING)
        # Only echo the factory's expected model after exact equality; never echo
        # a mismatching arbitrary string supplied in an incoming request.
        valid_expected=isinstance(expected_model,str)and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}',expected_model)is not None
        model_meta=({'state':'value','value':expected_model,'matches_factory_expected':True}
                    if valid_expected and model==expected_model else
                    {'state':'unknown_model','matches_factory_expected':False})
        selected={name:value_at(data,name)for name in(*NUMBERS,*BOOLEANS,*ENUMS)}
        result['actual_upstream_budget_metadata']={'schema':SCHEMA,'status':'observed','model':model_meta,'fields':selected}
        # Last defensive check: no NaN/Infinity or non-JSON objects escape.
        json.dumps(result,allow_nan=False)
        return result
    except Exception:
        # No exception text, arbitrary values, body, credentials or partial data.
        result['actual_upstream_budget_metadata']=unknown
        return result
