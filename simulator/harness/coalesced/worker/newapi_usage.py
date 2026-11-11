"""Observe NewAPI final upstream billing separately from Anthropic start estimates.

Does not alter a request, response, history, effort or CLI token accounting.
"""
def record_provider_usage(receipt, event):
    if not isinstance(event, dict):
        return
    message = event.get('message')
    if not isinstance(message, dict):
        message = {}
    for candidate in (message.get('usage'), event.get('usage')):
        if not isinstance(candidate, dict):
            continue
        billing = candidate.get('billing_usage')
        if not isinstance(billing, dict) or billing.get('semantic') != 'openai':
            continue
        usage = billing.get('openai_usage')
        if not isinstance(usage, dict):
            continue
        prompt, output = usage.get('prompt_tokens'), usage.get('completion_tokens')
        if type(prompt) is not int or type(output) is not int or min(prompt, output) < 0:
            continue
        details = usage.get('prompt_tokens_details') or {}
        completion = usage.get('completion_tokens_details') or {}
        cached = details.get('cached_tokens') if isinstance(details, dict) else None
        reasoning = completion.get('reasoning_tokens') if isinstance(completion, dict) else None
        normalized = {
            'source': 'newapi.billing_usage.openai_usage',
            'input_tokens_including_cached': prompt,
            'output_tokens_including_reasoning': output,
            'cached_input_tokens': cached if type(cached) is int and 0 <= cached <= prompt else None,
            'reasoning_output_tokens': reasoning if type(reasoning) is int and 0 <= reasoning <= output else None,
            'input_semantics': 'cached_tokens_already_included_in_prompt_tokens',
        }
        normalized['uncached_input_tokens'] = None if normalized['cached_input_tokens'] is None else prompt - normalized['cached_input_tokens']
        receipt['provider_usage'] = normalized
        receipt['provider_usage_final_event'] = event.get('type')
        if message.get('id'):
            receipt['provider_message_id'] = message['id']
    if event.get('type') == 'message_start' and isinstance(message.get('id'), str):
        receipt['provider_message_id'] = message['id']
