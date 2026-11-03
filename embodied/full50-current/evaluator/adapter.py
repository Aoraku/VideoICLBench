"""Opt-in, offline QA sidecar for future exported tasks; never starts an episode."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def binding_from_native(native_path, condition, episode_id, generalization, sim_review=None, source_binding=None):
    """Read only a future exported task's native.json; runner condition names supported."""
    if condition not in ('real', 'sim'):
        raise ValueError('QA requires real or sim video; text_rule is a separate control')
    native_path = Path(native_path).resolve()
    spec = read_json(native_path)
    media = spec['demo' if condition == 'real' else 'demo_sim']
    path = Path(os.path.expandvars(media['path']))
    if not path.is_absolute():
        path = native_path.parent.parent / path
    return dict(episode_id=episode_id, task_id=spec['task_id'], variant=spec['variant'],
                input_mode='real_demo' if condition == 'real' else 'sim_demo',
                generalization=generalization, demo_path=str(path), demo_sha256=media['sha256'],
                sim_review=sim_review, source_binding=source_binding)


def prepare(manifest, bank_dir=ROOT):
    """Return (public packets, private grading metadata). No API, simulator, or file mutation."""
    if manifest.get('enabled') is not True or manifest.get('run_state') != 'planned':
        raise ValueError('explicit enabled=true and run_state=planned required')
    if manifest.get('protocol') not in ('qa_then_act', 'isolated_qa'):
        raise ValueError('protocol must explicitly identify QA-assisted or isolated evaluation')
    bank, keys = (read_json(Path(bank_dir) / n) for n in ('questions.json', 'answer_key.private.json'))
    if bank['bank_version'] != keys['bank_version']:
        raise ValueError('bank/key versions differ')
    questions = {q['task_id']: q for q in bank['questions']}
    answers = {q['task_id']: q for q in keys['questions']}
    public, private, seen = [], [], set()
    for binding in manifest['bindings']:
        eid = binding['episode_id']
        if not isinstance(eid, str) or not eid or eid in seen:
            raise ValueError('episode_id must be unique and nonempty')
        seen.add(eid)
        task, variant = binding['task_id'], binding['variant']
        if variant not in ('A', 'B', 'C') or binding['generalization'] not in ('G0', 'G1', 'G2'):
            raise ValueError('unknown variant or generalization')
        q, key = questions[task], answers[task]
        if q['question_id'] != key['question_id'] or set(q['options']) != set('ABCD'):
            raise ValueError('invalid question/key identity or option layout')
        digest = sha256(binding['demo_path'])
        if digest != binding['demo_sha256']:
            raise ValueError('demo bytes do not match binding SHA256')
        mode = binding['input_mode']
        if mode == 'real_demo':
            if digest != key['sources'][variant]['sha256']:
                source = binding.get('source_binding') or {}
                if not (source.get('status') == 'reviewed' and source.get('task_id') == task
                        and source.get('variant') == variant and source.get('sha256') == digest
                        and source.get('source_sha256') == key['sources'][variant]['sha256']
                        and source.get('rule_preserving_transcode') is True
                        and str(source.get('reviewer', '')).strip()
                        and str(source.get('evidence', '')).strip()):
                    raise ValueError('real transcode requires reviewed source provenance')
        elif mode == 'sim_demo':
            review = binding.get('sim_review') or {}
            if not (review.get('status') == 'reviewed' and review.get('task_id') == task
                    and review.get('variant') == variant and review.get('sha256') == digest
                    and review.get('rule_matches_source') is True
                    and str(review.get('reviewer', '')).strip()
                    and str(review.get('evidence', '')).strip()):
                raise ValueError('sim video requires an explicit matching rule review')
        else:
            raise ValueError('only real_demo and sim_demo are supported')
        packet_id = 'qp_' + hashlib.sha256((bank['bank_version'] + '\0' + eid).encode()).hexdigest()[:20]
        public.append(dict(packet_id=packet_id, question_id=q['question_id'], prompt=q['prompt'],
                           options=q['options'], response_instruction='只输出一个大写选项字母：A、B、C或D。'))
        private.append(dict(packet_id=packet_id, question_id=q['question_id'], episode_id=eid,
                            task_id=task, variant=variant, input_mode=mode,
                            generalization=binding['generalization'], demo_sha256=digest,
                            demo_path=str(Path(binding['demo_path']).resolve()),
                            correct_option=key['answers'][variant], protocol=manifest['protocol']))
    common = dict(bank_version=bank['bank_version'], bank_sha256=sha256(Path(bank_dir)/'questions.json'))
    return ({**common, 'packets': public}, {**common, 'records': private})


def question_after_video(public_packet, private_record, watched_sha256):
    """Runner calls after delivering the bound video. Receipt must identify the same bytes.

    The runner is responsible for establishing actual delivery; a SHA alone cannot prove viewing.
    """
    if (public_packet['packet_id'] != private_record['packet_id']
            or public_packet['question_id'] != private_record['question_id']
            or watched_sha256 != private_record['demo_sha256']):
        raise ValueError('video/packet receipt mismatch')
    return dict(public_packet)



def _stage_identity(packet, record):
    if record['protocol'] != 'qa_then_act':
        raise ValueError('durable action gate supports qa_then_act only')
    if packet['packet_id'] != record['packet_id'] or packet['question_id'] != record['question_id']:
        raise ValueError('packet identity mismatch')
    identity = {k: record[k] for k in ('packet_id', 'question_id', 'episode_id', 'task_id',
                'variant', 'input_mode', 'generalization', 'demo_sha256', 'protocol')}
    identity['packet_sha256'] = hashlib.sha256(json.dumps(packet, ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return identity


def _stage_paths(packet, record, state_dir):
    identity = _stage_identity(packet, record)
    # Hash instead of trusting caller-provided packet_id as a filesystem path.
    name = hashlib.sha256(record['packet_id'].encode()).hexdigest()
    directory = Path(state_dir) / name
    return identity, directory, directory / 'video-delivered.private.json', directory / 'first-answer.private.json'


def _atomic_new(path, value):
    """Publish fully flushed JSON atomically without replacing any prior record."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.qa-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.link(temporary, path)  # Atomic exclusive publication, including concurrent writers.
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        os.unlink(temporary)


def _check_identity(path, identity):
    saved = read_json(path)
    if saved.get('identity') != identity:
        raise ValueError('saved QA state belongs to another episode, video, or question')
    return saved


def stage_after_video(packet, record, watched_sha256, state_dir):
    """Persist delivery receipt, then offer question or reopen the action gate on resume.

    State directory is private runner storage, never a model mount. No answer key is persisted.
    """
    question_after_video(packet, record, watched_sha256)
    identity, directory, watched, answer = _stage_paths(packet, record, state_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        _atomic_new(watched, dict(identity=identity, watched_sha256=watched_sha256))
    except FileExistsError:
        _check_identity(watched, identity)
    if answer.exists():
        _check_identity(answer, identity)
        return dict(status='submitted', action_allowed=True, packet_id=packet['packet_id'])
    return dict(status='awaiting_answer', action_allowed=False, question=dict(packet))


def record_first_answer(packet, record, raw_answer, state_dir):
    """Commit the first response and unlock actions; never teach, correct, or overwrite."""
    if not isinstance(raw_answer, str):
        raise ValueError('raw answer must be text')
    identity, directory, watched, answer = _stage_paths(packet, record, state_dir)
    if not watched.exists():
        raise ValueError('cannot answer before matching video delivery receipt')
    _check_identity(watched, identity)
    try:
        _atomic_new(answer, dict(identity=identity, raw_answer=raw_answer))
        reused = False
    except FileExistsError:
        _check_identity(answer, identity)
        reused = True
    # Even invalid format is a completed submission; offline grading handles validity.
    return dict(status='submitted', action_allowed=True,
                packet_id=packet['packet_id'], reused_first_answer=reused)


def grade(private_record, raw_answer):
    """Offline only: never feed this result to the acting model."""
    choice = raw_answer.strip() if isinstance(raw_answer, str) else ''
    valid = re.fullmatch('[ABCD]', choice) is not None
    return dict(packet_id=private_record['packet_id'], episode_id=private_record['episode_id'],
                question_id=private_record['question_id'], task_id=private_record['task_id'],
                variant=private_record['variant'], input_mode=private_record['input_mode'],
                generalization=private_record['generalization'], protocol=private_record['protocol'],
                demo_sha256=private_record['demo_sha256'], raw_answer=raw_answer,
                selected_option=choice if valid else None, format_valid=valid,
                qa_correct=(choice == private_record['correct_option']) if valid else None)


def write_new(path, value):
    """Exclusive create, private permissions. Never replace an existing answer or artifact."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--manifest', required=True)
    p.add_argument('--bank-dir', type=Path, default=ROOT)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('grade')
    p.add_argument('--private', required=True)
    p.add_argument('--packet-id', required=True)
    p.add_argument('--answer-file', required=True)
    p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        public, private = prepare(read_json(args.manifest), args.bank_dir)
        args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
        write_new(args.out/'packets.json', public)
        write_new(args.out/'grading.private.json', private)
    else:
        records = read_json(args.private)['records']
        matches = [r for r in records if r['packet_id'] == args.packet_id]
        if len(matches) != 1:
            raise ValueError('packet id must have exactly one grading record')
        write_new(args.out, grade(matches[0], Path(args.answer_file).read_text(encoding='utf-8')))


if __name__ == '__main__':
    main()
