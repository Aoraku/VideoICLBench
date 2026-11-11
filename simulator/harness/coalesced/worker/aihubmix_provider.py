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
    if engine == 'gemini':
        return https_origin('VIC_GEMINI_PRIMARY'), 'configured', True
    return https_origin('VIC_UPSTREAM_ORIGIN'), 'configured', os.environ.get('VIC_PROVIDER_DIRECT') == '1'
