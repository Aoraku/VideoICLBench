"""Contrastive examples must identify transformations beyond one convenient input."""
import json
import pytest
from vic import business, lessons


def texts(task_id, start):
    return [business.generate(task_id,seed)['source']['text'] for seed in lessons.seeds_for(task_id,start)]


@pytest.mark.parametrize('start',[0,10,20])
@pytest.mark.parametrize('task_id',[1,2,3,19,21,37])
def test_whole_text_lesson_separates_all_variants(task_id,start):
    states=[business.generate(task_id,seed) for seed in lessons.seeds_for(task_id,start)]
    assert len({s['source']['text'] for s in states})==6
    signatures=[json.dumps([business.expected_effect(task_id,v,s) for s in states],sort_keys=True) for v in 'ABC']
    assert len(set(signatures))==3


def test_case_lesson_contains_single_and_multiple_words_with_mixed_input_case():
    rows=texts(1,0)
    assert sum(len(t.split())==1 for t in rows)>=2
    assert sum(len(t.split())>1 for t in rows)>=4
    assert all(t!=t.lower() and t!=t.upper() and t!=t.title() for t in rows)
    assert set(rows).isdisjoint(business.generate(1,s)['source']['text'] for s in range(1000,1006))
    single=business.generate(1,1)
    assert [business.transform(1,v,single) for v in range(3)]==['cONFIRM','Confirm','Confirm']
    multi=business.generate(1,0)
    assert [business.transform(1,v,multi) for v in range(3)]==[
        'pLEASE REVIEW THE DESIGN DRAFT','Please review the design draft','Please Review The Design Draft']


def test_nickname_spacing_has_positive_negative_and_repeated_space_examples():
    rows=texts(2,0)
    assert any(' ' not in t for t in rows)
    assert any('  ' in t for t in rows)
    assert any('   ' in t for t in rows)
    s=business.generate(2,1)
    assert [business.transform(2,v,s) for v in range(3)]==['ChloeLin','Chloe__Lin','chloe  lin']
    s=business.generate(2,2)
    assert [business.transform(2,v,s) for v in range(3)]==['eMMA','eMMA','emma']


def test_appending_punctuation_is_distinguishable_from_replacing_it():
    rows=texts(3,0)
    assert {'.','!','?','。'} <= {t[-1] for t in rows}
    assert any(t[-1].isalpha() for t in rows)
    for seed in range(6):
        s=business.generate(3,seed)
        for variant,punctuation in enumerate('.!?'):
            assert business.transform(3,variant,s)==s['source']['text']+punctuation
    assert business.transform(3,0,business.generate(3,1)).endswith('?.')
    assert business.transform(3,1,business.generate(3,2)).endswith('.!')


def test_news_sources_and_punctuation_have_diverse_contexts():
    states=[business.generate(19,s) for s in range(6)]
    assert len({s['source']['publisher_short'] for s in states})==6
    characters=set(''.join(s['source']['text'] for s in states))
    assert set('：？！。(),./「」—') <= characters
    assert all(business.transform(19,2,s)==s['source']['publisher_short']+s['source']['text'] for s in states)
    assert set(s['source']['publisher_short'] for s in states).isdisjoint(
        business.generate(19,s)['source']['publisher_short'] for s in range(1000,1006))


def test_prompt_templates_have_six_lines_and_distinct_instructions():
    states=[business.generate(37,s) for s in range(6)]
    assert all(len(s['source']['text'].splitlines())==6 for s in states)
    assert len({line for s in states for line in s['source']['text'].splitlines()})==36
    for state in states:
        rows=state['source']['text'].splitlines()
        assert business.transform(37,0,state).splitlines()==['-'+line for line in rows]
        assert business.transform(37,1,state).splitlines()==[f'{i}. {line}' for i,line in enumerate(rows,1)]
        assert business.transform(37,2,state).splitlines()==[line+';' for line in rows]
    assert all(len(business.generate(37,s)['source']['text'].splitlines())==6 for s in range(1000,1006))


def test_collection_names_vary_in_length():
    assert len({len(t) for t in texts(21,0)})>=4
    assert min(map(len,texts(21,0)))==2
