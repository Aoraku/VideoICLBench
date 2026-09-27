"""Object counts must represent distinct inputs, including close boundary cases."""
import ast
import re
from collections import Counter
import pytest
from vic import business


FIELDS = {5:'text',13:'text',16:'text',39:'text',42:'name',43:'code',49:'text',56:'name',65:'code'}


@pytest.mark.parametrize('task_id,field', FIELDS.items())
def test_batch_materials_are_distinct_and_query_materials_are_held_out(task_id,field):
    for seed in (0,1,2,10,20,999):
        demo=business.generate(task_id,seed)
        query=business.generate(task_id,1000+seed)
        demonstrated={item[field] for item in demo['items']}
        queried={item[field] for item in query['items']}
        assert len(demonstrated)==24
        assert len(queried)==6
        assert demonstrated.isdisjoint(queried)


@pytest.mark.parametrize('seed',[0,1,2,10,20,999])
def test_message_markers_and_quotes_have_independent_contrasts(seed):
    state=business.generate(5,seed)
    texts=[item['text'] for item in state['items']]
    for marker in ('紧急','收到'):
        assert {(marker in text,'?' in text) for text in texts}=={(a,b) for a in (True,False) for b in (True,False)}
    state=business.generate(39,seed)
    texts=[item['text'] for item in state['items']]
    assert {(bool(re.search(r'\d',text)),'“' in text) for text in texts}=={(a,b) for a in (True,False) for b in (True,False)}
    assert sum('[' in text and '“' not in text for text in texts)>=4


@pytest.mark.parametrize('task_id',[42,56])
def test_latin_names_without_a_cannot_be_mistaken_for_all_latin_names(task_id):
    state=business.generate(task_id,0)
    names=[item['name'] for item in state['items']]
    assert sum('a' in name.lower() for name in names)==8
    assert sum(bool(re.search('[A-Za-z]',name)) and 'a' not in name.lower() for name in names)==8
    assert sum(not re.search('[A-Za-z]',name) for name in names)==8


@pytest.mark.parametrize('seed',[0,1,2,10,20,999,1000,1001,1002,10001])
def test_code_boundaries_use_real_code_and_check_results_match_syntax(seed):
    state=business.generate(65,seed)
    assert {24,25,26}<={len(item['code']) for item in state['items']}
    outcomes=[]
    for item in state['items']:
        assert '#' not in item['code']  # No padding comments to manufacture lengths.
        try:
            ast.parse(item['code'])
            valid=True
        except SyntaxError:
            valid=False
        assert item['check_pass']==valid
        outcomes.append((valid,'solve' in item['code'],len(item['code'])<25))
    if seed<1000:
        for col in range(3):
            counts=Counter(row[col] for row in outcomes)
            assert min(counts[False],counts[True])>=4
        # Passing syntax and the requested name must not select the same files.
        assert {(row[0],row[1]) for row in outcomes}=={(a,b) for a in (True,False) for b in (True,False)}


def test_transaction_remarks_keep_both_sides_and_equality_with_distinct_texts():
    state=business.generate(49,0)
    groups={length:{item['text'] for item in state['items'] if len(item['text'])==length} for length in (14,15,16)}
    assert all(len(values)>=4 for values in groups.values())
