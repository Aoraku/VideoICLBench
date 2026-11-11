import os
from urllib.parse import urlsplit


def https_origin(name):
    value = os.environ.get(name, '').rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ValueError(name + ' must be an HTTPS base URL without credentials, query or fragment')
    return value


def route_for(engine):
    # Codex (Responses) and Claude (Messages) use the same explicitly configured
    # provider as the other CLI adapters; no model-specific credential fallback.
    if engine == 'gemini':
        return https_origin('VIC_GEMINI_PRIMARY'), 'configured', True
    return https_origin('VIC_UPSTREAM_ORIGIN'), 'configured', os.environ.get('VIC_PROVIDER_DIRECT') == '1'


def upstream_url(origin, route):
    """Accept either a provider origin or an already versioned API base URL."""
    base = urlsplit(origin).path.rstrip('/')
    path = urlsplit(route).path
    # CLI adapters always send the public /v1 route to their local relay. A
    # configured .../v1 API base must not turn it into .../v1/v1/responses.
    if base.endswith('/v1') and path.startswith('/v1/'):
        return origin.rstrip('/') + route[len('/v1'):]
    return origin.rstrip('/') + route
