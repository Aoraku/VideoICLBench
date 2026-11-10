import json

def rows(path):
    raw=path.read_bytes()
    if raw and not raw.endswith(b'\n'):
        raise ValueError('incomplete receipt file')
    return [json.loads(line) for line in raw.splitlines() if line]


def classify(out, summary, stderr, env_error, sid):
    if env_error or summary.get('session_id')!=sid or 'upstream_generation_incomplete' not in stderr:
        return None
    native=[x for x in summary.get('errors',[]) if x.get('type') not in ('missing_native_result','tool_error')]
    matched=[]
    for e in native:
        error=e.get('payload',{}).get('error',{})
        if e.get('type')!='turn.failed' or e.get('sessionId')!=sid or error.get('code')!='upstream_generation_incomplete':
            return None
        att=error.get('attribution') or {}
        if not (att.get('source')=='provider' and att.get('providerErrorCode')=='upstream_generation_incomplete'
                and att.get('errorPhase')=='stream' and att.get('providerId')=='vic' and
                att.get('providerKind')=='anthropic' and att.get('modelId')=='glm-5.3-flash' and att.get('transport')=='sse'):
            return None
        matched.append(e)
    if not matched:
        return None
    requests=[e for e in rows(out/'transport.jsonl') if not e.get('count_only')]
    guards=rows(out/'zcode-stream-guard.jsonl')
    if not requests or not guards:
        return None
    call,guard=requests[-1],guards[-1]
    if not (call.get('outcome')=='failure' and call.get('upstream_origin')=='https://aihubmix.com'
            and call.get('upstream_http')==200 and call.get('curl_exit') in (0,18)
            and call.get('failure_class')=='incomplete_upstream_response'
            and call.get('upstream_completed') is False and call.get('downstream_complete_write') is False
            and guard.get('inner_http')==200 and guard.get('failure_class')=='incomplete_or_invalid_upstream_sse'
            and guard.get('delivered') is False and guard.get('downstream_complete_write') is False):
        return None
    if not (-2<=guard['ended']-call['ended']<=2 and -2<=matched[-1]['timestamp']/1000-guard['ended']<=60):
        return None
    return dict(failure='transport',sid=sid,transport_request_id=call['id'],curl_exit=call['curl_exit'],
                upstream_ended=call['ended'],guard_ended=guard['ended'],native_event=matched[-1].get('eventId'))


def classify_dsh(out, summary, stderr, env_error, sid):
    if env_error or summary.get('session_id') != sid:
        return None
    expected = {'kind': 'error', 'error': {'code': 'SERVER', 'message': 'Upstream generation did not complete.'}}
    reason = summary.get('native_turn_end_reason') or {}
    error = reason.get('error') or {}
    if (reason.get('kind') != expected['kind'] or any(error.get(k) != v for k, v in expected['error'].items())
            or 'dsh: SERVER: Upstream generation did not complete.' not in stderr):
        return None
    if any(e.get('type') not in ('native_final_not_completed','tool_error','missing_native_final')
           for e in summary.get('errors', [])):
        return None
    requests = [row for row in rows(out/'transport.jsonl') if not row.get('count_only')]
    if len(requests) < 2:
        return None
    tail = requests[-2:]
    for call in tail:
        if not (call.get('outcome') == 'failure' and call.get('upstream_origin') == 'https://aihubmix.com'
                and call.get('route') == '/v1/messages' and call.get('upstream_http') is None
                and call.get('curl_exit') == 35 and call.get('failure_class') == 'MissingUpstreamHTTPStatus'
                and call.get('upstream_completed') is False and call.get('downstream_complete_write') is False):
            return None
    call = tail[-1]
    return dict(failure='transport', sid=sid, transport_request_id=call['id'], curl_exit=35,
                upstream_ended=call['ended'], reason='verified_aihubmix_tls_handshake_error')


def recoverable_exit(engine, out, summary, stderr, env_error, sid):
    try:
        classify_failure = classify_dsh if engine == 'dsh' else classify
        evidence=classify_failure(out,summary,stderr,env_error,sid)
    except (KeyError, ValueError, OSError, TypeError):
        return None
    if evidence:
        with (out/'owned-stream-auto-recovery.private.jsonl').open('a') as log:
            log.write(json.dumps(evidence)+'\n')
        return evidence['failure']
    return None
