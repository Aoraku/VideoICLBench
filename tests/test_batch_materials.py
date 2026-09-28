"""Object counts must represent distinct inputs, including close boundary cases."""
import ast
import re
from collections import Counter
import pytest
from vic import business
from vic import teaching, teaching_materials


@pytest.mark.parametrize('seed', [0, 1, 2, 5, 10, 999, 1000, 1001, 10001])
def test_contact_group_materials_cross_parity_and_vowels(seed):
    items = business.generate(6, seed)['items']
    cells = Counter((len(x['name'].replace(' ', '')) % 2, bool(re.search('[aeiou]', x['name'], re.I))) for x in items)
    assert set(cells) == {(parity, vowel) for parity in (0, 1) for vowel in (False, True)}
    assert min(cells.values()) >= (5 if seed < 1000 else 1)
    assert all(x['name_length'] == len(x['name'].replace(' ', '')) for x in items)
    full_vowels = {x['id'] for x in items if re.search('[aeiou]', x['name'], re.I)}
    first_vowels = {x['id'] for x in items if re.search('[aeiou]', x['name'].split()[0], re.I)}
    last_vowels = {x['id'] for x in items if re.search('[aeiou]', x['surname'], re.I)}
    assert full_vowels != first_vowels
    assert full_vowels != last_vowels


def test_contact_names_disallow_a_surname_lookup_for_vowels_and_hold_out_query():
    demo = teaching_materials.grouped_contacts()
    query = teaching_materials.grouped_contacts(True)
    assert set(demo).isdisjoint(query)
    both_classes = 0
    for surname in {n.split()[-1] for n in demo}:
        classes = {bool(re.search('[aeiou]', n, re.I)) for n in demo if n.split()[-1] == surname}
        both_classes += len(classes) == 2
    assert both_classes >= 6


@pytest.mark.parametrize('seed', [*range(30), 999, *range(1000, 1020), 10001])
def test_recipient_choices_have_unique_surnames_and_visible_chronology(seed):
    from datetime import datetime
    items = business.generate(9, seed)['items']
    assert len({x['surname'] for x in items}) == 6
    assert all(x['surname'] == x['name'].split()[-1] for x in items)
    assert [x['id'] for x in sorted(items, key=lambda x: x['contact_time'])] == [
        x['id'] for x in sorted(items, key=lambda x: datetime.fromisoformat(x['last_contact_at']))]
    assert len({x['last_contact_at'] for x in items}) == 6


def test_recipient_lesson_includes_surnames_sharing_first_letter():
    episodes = [business.generate(9, seed)['items'] for seed in range(6)]
    assert any(sum(x['surname'][0] == min(items, key=lambda x: x['surname'])['surname'][0] for x in items) > 1 for items in episodes)
    for variant in 'ABC':
        winners = [business.targets(9, 'ABC'.index(variant), items, {'threshold': 50})[0] for items in episodes]
        assert len({next(i for i, x in enumerate(items) if x['id'] == winner) for items, winner in zip(episodes, winners)}) >= 3


def test_recipient_unread_rule_requires_relative_comparison():
    episodes = [business.generate(9, seed)['items'] for seed in range(6)]
    positives = [max(x['unread'] for x in items) for items in episodes]
    negatives = [x['unread'] for items, maximum in zip(episodes, positives) for x in items if x['unread'] != maximum]
    assert len(set(positives)) == 6
    assert min(positives) < max(negatives)
    assert set(positives) & set(negatives)


@pytest.mark.parametrize('seed', [*range(12), 999, *range(1000, 1012), 10001])
def test_chat_files_have_real_sizes_and_distinct_selection_rules(seed):
    import base64
    from vic_apps.domain import initialize
    state = initialize(business.generate(11, seed))
    items = state['items']
    assert len({x['file_text'] for x in items}) == 6
    for item in items:
        assert item['file_text'].startswith('# ' + item['name'][:-3] + '\n')
        assert item['name_length'] == len(item['name'])
        assert item['size'] == len(item['file_text'].encode('utf-8'))
        assert base64.b64decode(state['domain']['files'][item['id']]['content']) == item['file_text'].encode('utf-8')
    smallest = min(items, key=lambda x: x['size'])
    largest = max(items, key=lambda x: x['size'])
    shortest = min(items, key=lambda x: x['name_length'])
    assert len({x['id'] for x in (smallest, largest, shortest)}) == 3
    assert sum(x['name_length'] == shortest['name_length'] for x in items) == 1
    assert len({x['size'] for x in items}) == 6


def test_chat_file_lesson_cannot_be_solved_by_fixed_name_or_absolute_length():
    episodes = [business.generate(11, seed)['items'] for seed in range(6)]
    positives, negatives = set(), set()
    for key, reverse in [('size', False), ('size', True), ('name_length', False)]:
        winners = [sorted(items, key=lambda x: x[key], reverse=reverse)[0] for items in episodes]
        assert len({x['name'] for x in winners}) >= 4
        assert len({next(i for i, x in enumerate(items) if x['id'] == win['id']) for items, win in zip(episodes, winners)}) >= 3
        if key == 'size':
            other_sizes = [x['size'] for items, win in zip(episodes, winners) for x in items if x['id'] != win['id']]
            # No single byte threshold should reproduce the relative choice.
            assert min(other_sizes) < max(x['size'] for x in winners)
            assert max(other_sizes) > min(x['size'] for x in winners)
        if key == 'name_length':
            positives = {x[key] for x in winners}
            negatives = {x[key] for items, win in zip(episodes, winners) for x in items if x['id'] != win['id']}
    assert len(positives) >= 3
    assert positives & negatives
    demo_names = {x['name'] for items in episodes for x in items}
    query_names = {x['name'] for seed in range(1000, 1006) for x in business.generate(11, seed)['items']}
    assert demo_names.isdisjoint(query_names)


@pytest.mark.parametrize('task_id', [19, 20, 23, 24, 29, 30, 33])
@pytest.mark.parametrize('seed', [0, 1, 2, 999, 1000, 10001])
def test_news_bodies_follow_titles_and_remain_distinct(task_id, seed):
    items = business.generate(task_id, seed)['items']
    for item in items:
        title = item['name'].removeprefix('紧急：')
        assert item['text'] == teaching_materials.NEWS_ARTICLES[title]
        assert len(item['text']) >= 50
        assert item['text'].endswith('。')
    assert len({x['text'] for x in items}) == len(items)


def test_news_materials_cover_titles_and_keep_query_bodies_held_out():
    demo = teaching.NAMES['news']
    query = teaching.QUERY_NAMES['news']
    assert set(teaching_materials.NEWS_ARTICLES) == set(demo + query)
    assert {teaching_materials.NEWS_ARTICLES[x] for x in demo}.isdisjoint(
        teaching_materials.NEWS_ARTICLES[x] for x in query)


FIELDS = {5:'text',13:'text',16:'text',24:'publisher',38:'text',39:'text',42:'name',43:'code',49:'text',56:'name',65:'code'}


@pytest.mark.parametrize('seed', [0, 1, 2, 999, 1000, 1001, 10001])
def test_news_source_lengths_have_close_boundaries_and_independent_initials(seed):
    items = business.generate(24, seed)['items']
    assert {4, 5, 6} <= {len(x['publisher']) for x in items}
    contrasts = Counter((x['publisher'][0].lower() in 'aeiou', len(x['publisher']) > 5) for x in items)
    assert set(contrasts) == {(a, b) for a in (False, True) for b in (False, True)}
    if seed < 1000:
        assert min(contrasts.values()) >= 4


@pytest.mark.parametrize('task_id', [36, 38, 40, 42])
@pytest.mark.parametrize('seed', [0, 1, 2, 999, 1000, 10001])
def test_blog_counts_match_complete_visible_bodies(task_id, seed):
    state = business.generate(task_id, seed)
    for item in state['items']:
        assert item['words'] == len(item['text'])
        assert item['text'].endswith('。')
        assert len(item['text']) >= 30
    assert len({item['text'] for item in state['items']}) == len(state['items'])


def test_blog_boundary_bodies_are_distinct_and_held_out():
    demo = business.generate(38, 0)['items']
    query = business.generate(38, 1000)['items']
    assert {49, 50, 51} <= {len(x['text']) for x in demo}
    assert {49, 50, 51} <= {len(x['text']) for x in query}
    assert len({len(x['text']) for x in demo}) == 21
    assert len([x for x in demo if len(x['text']) == 50]) == 4
    assert {x['text'] for x in demo}.isdisjoint(x['text'] for x in query)


@pytest.mark.parametrize('task_id', [38, 40])
def test_blog_evaluation_uses_body_text_instead_of_stale_count_metadata(task_id):
    state = business.generate(task_id, 0)
    items = state['items']
    if task_id == 38:
        expected = {x['id'] for x in items if len(x['text']) > state['source']['threshold']}
        variant = 0
    else:
        expected = {min(items, key=lambda x: len(x['text']))['id']}
        variant = 2
    for x in items:
        x['words'] = 0 if x['id'] in expected else 10000
    assert set(business.targets(task_id, variant, items, state['source'])) == expected


def test_blog_query_shortest_post_varies_across_instances():
    names = set()
    for seed in range(1000, 1012):
        items = business.generate(40, seed)['items']
        names.add(min(items, key=lambda x: len(x['text']))['name'])
    assert len(names) >= 3


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


@pytest.mark.parametrize('seed', [0, 1, 2, 3, 4, 5, 20, 999, 1000, 1001, 1002, 10001])
def test_model_choice_has_unique_shortest_name_and_visible_lengths(seed):
    items = business.generate(41, seed)['items']
    assert all(x['name_length'] == len(x['name']) for x in items)
    shortest = min(x['name_length'] for x in items)
    assert sum(x['name_length'] == shortest for x in items) == 1


@pytest.mark.parametrize('base_seed', [0, 6, 1000, 10000])
def test_shortest_model_name_is_relative_and_varies_across_lessons(base_seed):
    groups = [business.generate(41, base_seed + index)['items'] for index in range(6)]
    minima = [min(group, key=lambda x: len(x['name'])) for group in groups]
    assert len({len(x['name']) for x in minima}) >= 2
    assert len({x['name'] for x in minima}) >= 3
    assert max(len(x['name']) for x in minima) > min(len(x['name']) for group, winner in zip(groups, minima) for x in group if x['id'] != winner['id'])


@pytest.mark.parametrize('seed', [0, 1, 2, 1000, 1001, 10001])
def test_studio_code_has_distinct_file_names_and_saved_content_matches(seed, tmp_path):
    from vic import application_eval
    from vic_apps.domain import initialize
    from vic_apps.store import ApplicationStore
    from vic.schemas import Mutation
    initial = initialize(business.generate(43, seed))
    assert len({x['name'] for x in initial['items']}) == len(initial['items'])
    assert all(x['name'].endswith('.py') for x in initial['items'])
    store = ApplicationStore(tmp_path)
    for variant, action in [('A', '保存'), ('B', '复制'), ('C', '发送')]:
        store.initialize('studio', initial)
        for index, item in enumerate(initial['items']):
            store.mutate('studio', Mutation(epoch=0, action_id=f'check-{index}', op='action', target=item['id'], value='检查'))
            if item['check_pass']:
                store.mutate('studio', Mutation(epoch=0, action_id=f'act-{index}', op='action', target=item['id'], value=action))
        final = store.snapshot('studio'); domain = final['domain']
        if variant == 'A':
            records = [(x['target'], x['body']) for x in domain['artifacts']]
        elif variant == 'B':
            records = [(x['target'], x['text']) for x in domain['clipboard_history']]
        else:
            records = [(x['reference'], x['body']) for x in domain['messages']]
            assert all(x['recipient'] == 'contact-a' for x in domain['messages'])
        assert all(body == domain['objects'][target]['code'] for target, body in records)
        result = application_eval.evaluate(initial, final, variant, store.events('studio'), records[-1][1] if variant == 'B' else None)
        assert result['success'], result
        if variant == 'B':
            target, body = records[0]
            store.mutate('studio', Mutation(epoch=0, action_id='copy-again', op='action', target=target, value='复制'))
            final = store.snapshot('studio')
            assert application_eval.evaluate(initial, final, variant, store.events('studio'), body)['success']
            assert not application_eval.evaluate(initial, final, variant, store.events('studio'), 'wrong clipboard')['success']


@pytest.mark.parametrize('seed', [*range(12), 999, 1000, 1001, 10001])
def test_group_names_and_size_boundaries_are_independent(seed):
    items = business.generate(8, seed)['items']
    assert len({x['name'] for x in items}) == len(items)
    cells = Counter((bool(re.search(r'\d', x['name'])), x['members'] > 5) for x in items)
    assert set(cells) == {(digit, large) for digit in (False, True) for large in (False, True)}
    assert min(cells.values()) >= (6 if seed < 1000 else 1)
    assert {4, 5, 6} <= {x['members'] for x in items}
    if seed < 1000:
        assert len({x['members'] for x in items}) >= 10
    assert set(teaching_materials.chat_groups()).isdisjoint(teaching_materials.chat_groups(True))


@pytest.mark.parametrize('seed', [*range(12), 999, 1000, 1001, 10001])
def test_search_request_matches_all_six_distinct_results(seed):
    state = business.generate(10, seed)
    assert state['source']['search_keyword']
    texts = [x['text'] for x in state['items']]
    assert len(set(texts)) == 6
    assert all(state['source']['search_keyword'] in text for text in texts)
    assert set(teaching_materials.search_messages(seed % 6)[1]).isdisjoint(
        teaching_materials.search_messages(1000 + seed % 6)[1])


@pytest.mark.parametrize('task_id,reverse', [(7, True), (7, False), (10, True)])
def test_chat_relative_unread_selection_excludes_fixed_values_and_thresholds(task_id, reverse):
    selected, others = [], []
    for seed in range(6):
        values = [x['unread'] for x in business.generate(task_id, seed)['items']]
        assert len(set(values)) == 6
        winner = (max if reverse else min)(values)
        selected.append(winner)
        others.extend(x for x in values if x != winner)
    assert len(set(selected)) == 6
    assert min(selected) < max(others)
    assert max(selected) > min(others)
