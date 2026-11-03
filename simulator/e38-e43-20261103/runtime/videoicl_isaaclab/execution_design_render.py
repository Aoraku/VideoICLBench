"""Explicit renderer configuration for an isolated execution-v2 process.

Isaac's performance defaults disable translucency and make alpha materials
black. Never change rendering for legacy worlds or mix old/new cohorts.
Configuration/readback is not a visual-acceptance certificate.
"""
REVISION = 'embodied50-execution-v2-20261102'
REVISIONS = (REVISION, 'embodied50-execution-v3-20261102')
SETTINGS = {
    '/rtx/translucency/enabled': True,
    '/rtx/reflections/enabled': True,
    '/rtx/raytracing/fractionalCutoutOpacity': True,
    '/rtx/pathtracing/fractionalCutoutOpacity': True,
    '/rtx/material/translucencyAsOpacity': False,
    '/rtx/post/backgroundZeroAlpha/enabled': False,
    '/rtx/translucency/maxRefractionBounces': 8,
}


def configure_render_for_specs(specs, settings):
    specs = list(specs)
    revisions = [s.get('execution_design', {}).get('revision') for s in specs]
    revised = [r in REVISIONS for r in revisions]
    if not any(revised):
        return dict(applied=False, profile='legacy_unchanged')
    if not all(revised) or len(set(revisions)) != 1:
        raise ValueError('Revised renderer requires an isolated revision-only process')
    before = {key: settings.get(key) for key in SETTINGS}
    for key, value in SETTINGS.items():
        if type(value) is bool:
            settings.set_bool(key, value)
        else:
            settings.set_int(key, value)
    actual = {key: settings.get(key) for key in SETTINGS}
    if actual != SETTINGS:
        raise RuntimeError('Execution renderer setting readback mismatch')
    return dict(applied=True, profile='execution-v2-transmission-v1',
                before=before, actual=actual, visual_acceptance='pending_native_review')
