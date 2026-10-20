"""Structural contracts shared by the OS workbench, review and release builder."""
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_recording_compatibility_is_explicit_and_does_not_hide_revised_lessons():
    from vic.os_release import recording_current
    release=json.loads((ROOT/'tasks/os/catalog.json').read_text())
    old=next(iter(release['recording_compatibility']))
    entry={'fingerprint':old,'design_version':release['design_version'],'case_id':'OS-E-01'}
    assert recording_current(release,entry)
    assert recording_current(release,{**entry,'case_id':'OS-E-06'})  # Same contact mapping; IDs remain input data.
    for cid in ('OS-E-02','OS-E-03','OS-E-08','OS-M-04'):
        assert not recording_current(release,{**entry,'case_id':cid})
        assert recording_current(release,{**entry,'case_id':cid,'fingerprint':release['implementation']['fingerprint']})
    assert not recording_current(release,{**entry,'fingerprint':'unknown'})

def test_36_independent_families_clear_rules_and_multiple_demo_realizations():
    release=json.loads((ROOT/'tasks/os/catalog.json').read_text());rows=release['cases']
    assert len({t['id'] for t in rows})==36
    assert Counter(t['difficulty'] for t in rows)=={'easy':12,'medium':12,'hard':12}
    for t in rows:
        assert set(t['rules'])==set(t['demo_examples'])==set('ABC')
        assert len(set(t['rules'].values()))==3
        assert t['demo_actor']=='human' and t['demo_scope']=='local-method-only'
        assert len(set(t['demo_seeds']))==t['demo_groups'] and 4201 not in t['demo_seeds']
        assert t['relation'] in t['query_example']
        if t['difficulty']=='hard':assert len(t['dependencies'])>=2 and t['demo_groups']==3
        for groups in t['demo_examples'].values():
            assert len(groups)==t['demo_groups']
            assert all(g['steps'] and g['instruction'] for g in groups)
            # Single desktop lessons must exhibit the method on multiple items.
            if len(groups)==1 and t['id']!='OS-M-05':assert len(groups[0]['steps'])>=2
            if t['id']=='OS-M-05':assert groups[0]['steps'][0]['content'].count('\n')>=2
        # No full query request is used as the demo instructions.
        assert all(g['instruction']!=t['query_example'] for groups in t['demo_examples'].values() for g in groups)


def test_handbook_and_review_use_the_same_36_task_design():
    rows=json.loads((ROOT/'tasks/os/catalog.json').read_text())['cases']
    book=json.loads((ROOT/'docs/task-design-catalog.json').read_text())
    os_rows={t['id']:t for t in book if t['kind']=='os'}
    assert set(os_rows)=={t['id'] for t in rows}
    for t in rows:
        assert os_rows[t['id']]['demo']==t['demo_description']
        assert os_rows[t['id']]['rules']==t['rules']
        assert os_rows[t['id']]['difficulty']==t['difficulty']


def test_recording_guides_distinguish_demo_apps_and_name_real_controls():
    rows=json.loads((ROOT/'tasks/os/catalog.json').read_text())['cases']
    for task in rows:
        for groups in task['demo_examples'].values():
            for group in groups:
                guide=group['guide']
                assert guide['entry'] and guide['apps'] and guide['steps']
                assert all(s['where'] and s['action'] for s in guide['steps'])
                writes=[s for s in group['steps'] if s['op']=='write']
                assert guide['outputs']==list(dict.fromkeys(s['target'] for s in writes))
                if any('Example result.txt' in s['target'] for s in writes):
                    assert guide['inputs'] and 'Example input.json' in guide['entry']
                    assert guide['steps'][0]['expected'] is None  # Read input before editing output.
                for s in writes:
                    assert any(s['target'] in d['where'] and s['content']==d['expected'] for d in guide['steps'])
                for s in group['steps']:
                    if s['op']=='export-log':assert any('Export interval…' in d['where'] for d in guide['steps'])
    hard_notes=next(t for t in rows if t['id']=='OS-H-02')
    assert hard_notes['demo_apps']==['Notepad']
    assert 'Settings' in hard_notes['app'] and len(hard_notes['dependencies'])>=2
