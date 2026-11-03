"""Pin a per-profile GUI-only native tool registry; never consult user-global configuration."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re

SUPPORTED_NATIVE_CLI_VERSIONS = frozenset(('codex-cli 0.163.0', 'codex-cli 0.164.0'))
GUI_ONLY_NATIVE_CONFIG_LINES = (
    'tools.experimental_request_user_input.enabled = false',
    'tools.update_plan.enabled = false',
)


def _read_validated(source_path, expected_sha256, model):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256):
        raise ValueError('A complete model catalog SHA256 is required')
    raw = Path(source_path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256.lower():
        raise ValueError('Model catalog SHA256 mismatch')
    catalog = json.loads(raw)
    models = catalog.get('models') if isinstance(catalog, dict) else None
    if not isinstance(models, list) or not all(isinstance(m, dict) for m in models):
        raise ValueError('Model catalog must contain a models array')
    targets = [m for m in models if m.get('slug') == model]
    if len(targets) != 1:
        raise ValueError('Model catalog must contain exactly one matching model slug')
    original = targets[0].get('tool_mode')
    if original not in ('direct', 'code_mode_only'):
        raise ValueError('Missing or unvalidated model tool_mode')
    return raw, catalog, {'model': model, 'source_sha256': actual,
                          'source_path': str(Path(source_path).resolve()),
                          'original_tool_mode': original, 'model_count': len(models)}


def validate_model_catalog(source_path, expected_sha256, model):
    """Fail closed on absent/mismatched input; does not create any files."""
    return _read_validated(source_path, expected_sha256, model)[2]


def _write_once(path, raw):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError('Refusing to replace a different profile catalog: ' + str(path))
        return
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)


def freeze_direct_model_catalog(profile, source_path, expected_sha256, model, *, cli_version):
    """Copy exact pinned source and derive target-only GUI registry policy plus a receipt.

    Caller supplies the actual CLI --version output. This operation does not launch
    the CLI, change any global config, or assert that a provider supports the schema.
    The returned catalog_path can be used in native config model_catalog_json.
    """
    if cli_version not in SUPPORTED_NATIVE_CLI_VERSIONS:
        raise ValueError('Native CLI version has not passed the GUI direct registry probe')
    raw, source, meta = _read_validated(source_path, expected_sha256, model)
    direct = copy.deepcopy(source)
    target = next(m for m in direct['models'] if m.get('slug') == model)
    original_target = copy.deepcopy(target)
    registry_policy = {'tool_mode': 'direct', 'apply_patch_tool_type': None,
                       'experimental_supported_tools': [], 'supports_search_tool': False}
    target.update(registry_policy)
    # Explicit v1/v2 overrides the disabled native multi_agent feature. Omit
    # it so the feature switch governs registration, including eager tools.
    target.pop('multi_agent_version', None)
    changes = {k: {'before': original_target.get(k), 'after': v}
               for k, v in registry_policy.items() if k not in original_target or original_target[k] != v}
    if 'multi_agent_version' in original_target:
        changes['multi_agent_version'] = {'before': original_target['multi_agent_version'], 'removed': True}
    output = (json.dumps(direct, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    profile = Path(profile).resolve()
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_copy = profile / 'model-catalog.source.private.json'
    catalog_path = profile / 'model-catalog.direct.private.json'
    receipt = dict(meta, schema='videoicl-native-direct-catalog-v3', policy='gui_only_eager_native_registry_v1', cli_version=cli_version,
                   catalog_path=str(catalog_path), source_copy_path=str(source_copy),
                   output_sha256=hashlib.sha256(output).hexdigest(), tool_mode='direct',
                   registry_changes=changes,
                   changed_fields=[f'models[slug={model}].{k}' for k in changes])
    receipt_bytes = (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode()
    # Verify all pre-existing outputs before writing any missing file.
    outputs = [(source_copy, raw), (catalog_path, output),
               (profile / 'model-catalog.receipt.private.json', receipt_bytes)]
    for path, value in outputs:
        if path.exists() and path.read_bytes() != value:
            raise ValueError('Refusing to replace a different profile catalog: ' + str(path))
    for path, value in outputs:
        _write_once(path, value)
    return receipt


def validate_context_window(source_path, expected_sha256, model, context_window, compact_tokens):
    """Check local native configuration consistency, not provider capacity."""
    if context_window is None:
        return
    if type(context_window) is not int or context_window <= 0:
        raise ValueError('Context window must be a positive integer')
    if type(compact_tokens) is not int or not 0 < compact_tokens < context_window:
        raise ValueError('Compaction threshold must be below context window')
    _, catalog, _ = _read_validated(source_path, expected_sha256, model)
    target = next(m for m in catalog['models'] if m.get('slug') == model)
    for field in ('context_window', 'max_context_window'):
        limit = target.get(field)
        if type(limit) is not int or limit < context_window:
            raise ValueError('Pinned model catalog does not support requested ' + field)
