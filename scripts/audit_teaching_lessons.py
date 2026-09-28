#!/usr/bin/env python3
"""Inspect complete teaching lessons; dataset checks do not certify video usability."""
import argparse
from collections import Counter
import json
import re
from pathlib import Path

from vic import business, games, lessons
from vic.catalog import catalog
from vic_apps.domain import initialize
from audit_teaching_cases import BOUNDARIES, NUMERIC, selected

ROOT = Path(__file__).resolve().parents[1]


def signature(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def inspect_lesson(task, base_seed):
    task_id = task['id']
    seeds = lessons.seeds_for(task_id, base_seed)
    states = [initialize(business.generate(task_id, seed)) for seed in seeds]
    effects = [{v: (games.stopping_paths(state)[v] if task_id == 69 else
                     games.expected(task_id, v, state) if task_id >= 66 else
                     business.expected_effect(task_id, v, state)) for v in 'ABC'}
               for state in states]
    series = {v: [effect[v] for effect in effects] for v in 'ABC'}
    risks = []
    if len({signature(value) for value in series.values()}) != 3:
        risks.append('whole_lesson_variant_collision')
    report = dict(base_seed=base_seed, seeds=seeds, episodes=len(seeds),
                  objects_per_episode=[len(s.get('items', s.get('candidates', []))) for s in states],
                  distinct_variant_series=len({signature(value) for value in series.values()}))
    if task['type'] == 'T':
        report['distinct_sources'] = len({signature(s['source']) for s in states})
        report['distinct_outputs'] = {v: len({signature(e[v]) for e in effects}) for v in 'ABC'}
        if report['distinct_sources'] < 6:
            risks.append('repeated_editing_material')
        texts = [s['source']['text'] for s in states]
        coverage = dict(lengths=sorted({len(t) for t in texts}),
                        line_counts=[len(t.splitlines()) for t in texts],
                        single_word=sum(len(t.split()) == 1 for t in texts),
                        multiple_words=sum(len(t.split()) > 1 for t in texts),
                        space_widths=sorted({len(m) for t in texts for m in re.findall(' +',t)}),
                        endings=sorted({t[-1:] for t in texts}))
        report['source_coverage'] = coverage
        if task_id == 1 and not (coverage['single_word'] >= 2 and coverage['multiple_words'] >= 4):
            risks.append('missing_single_or_multiword_contrast')
        if task_id == 2 and not (coverage['single_word'] and {1,2,3} <= set(coverage['space_widths'])):
            risks.append('missing_spacing_contrast')
        if task_id == 3 and not {'.','!','?','。'} <= set(coverage['endings']):
            risks.append('missing_existing_punctuation_contrast')
        if task_id == 19:
            coverage['publisher_short_names'] = sorted({s['source']['publisher_short'] for s in states})
            if len(coverage['publisher_short_names']) < 6:
                risks.append('fixed_news_source_prefix')
        if task_id == 21 and len(coverage['lengths']) < 4:
            risks.append('insufficient_collection_name_lengths')
        if task_id in (37,59) and min(coverage['line_counts']) < 6:
            risks.append('insufficient_multiline_examples')
    if task_id < 66:
        if task_id in (31, 47, 51):
            minima = [min(item['duration'] for item in state['items']) for state in states]
            distractors = [item['duration'] for state, minimum in zip(states, minima)
                           for item in state['items'] if item['duration'] != minimum]
            report['minimum_duration_series'] = minima
            if len(set(minima)) < 3:
                risks.append('fixed_or_near_fixed_shortest_duration')
            if max(minima) < min(distractors):
                risks.append('fixed_duration_threshold_explains_minimum')
        material_field = {5:'text',13:'text',16:'text',39:'text',42:'name',43:'code',49:'text',56:'name',65:'code'}.get(task_id)
        if material_field:
            counts = [len({item[material_field] for item in state['items']}) for state in states]
            report['distinct_batch_materials'] = dict(field=material_field, counts=counts)
            if any(count != len(state['items']) for count,state in zip(counts,states)):
                risks.append('duplicated_batch_materials')
        report['positions'] = {v: [[s['order'].index(i) + 1 for i in (selected(e[v]) or [])]
                                  for s, e in zip(states, effects)] for v in 'ABC'}
        report['shared_extrema_explanations'] = {}
        for v in 'ABC':
            rivals = []
            for state, effect in zip(states, effects):
                chosen = selected(effect[v])
                if not chosen or len(chosen) != 1:
                    break
                rivals.append({f'{field}:{direction}' for field in NUMERIC for direction in ('min', 'max')
                    if sorted(state['items'], key=lambda x: x[field], reverse=direction == 'max')[0]['id'] == chosen[0]})
            if len(rivals) == len(states):
                report['shared_extrema_explanations'][v] = sorted(set.intersection(*rivals))
                positions = report['positions'][v]
                if len(seeds) > 1 and len({signature(p) for p in positions}) == 1 and task_id != 10:
                    risks.append(f'fixed_selected_position_{v}')
        if task_id in BOUNDARIES:
            field, threshold = BOUNDARIES[task_id]
            observed = {len(i['text']) if field == 'text_length' else len(i['code']) if field == 'code_length' else i[field]
                        for s in states for i in s['items']}
            report['threshold'] = dict(field=field, value=threshold, observed=sorted(observed),
                                       missing=[n for n in (threshold-1, threshold, threshold+1) if n not in observed])
            if report['threshold']['missing']:
                risks.append('missing_threshold_neighbors')
    else:
        report['expected_series'] = series
        if task_id == 69:
            report['stopping_steps'] = {v:[len(path) for path in paths] for v,paths in series.items()}
            if any(len(set(lengths)) < 2 for lengths in report['stopping_steps'].values()):
                risks.append('fixed_2048_stopping_step')
        if task_id == 72:
            report['candidate_quadrants'] = [sorted({f'{r//4},{c//4}' for r,c in state['candidates']}) for state in states]
            if any(len(quadrants) < 4 for quadrants in report['candidate_quadrants']):
                risks.append('spatially_concentrated_mines_candidates')
        if task_id in (74,75):
            report['player_colors'] = [state['color'] for state in states]
        if task_id == 68:
            report['distinct_directions'] = {v: len(set(series[v])) for v in 'ABC'}
            if any(n < 2 for n in report['distinct_directions'].values()):
                risks.append('fixed_2048_direction')
    report['measured_risks'] = risks
    return report


def audit():
    records = []
    for task in catalog()['tasks'][:75]:
        cases = []
        for seed in (0, 10, 20):
            try:
                cases.append(inspect_lesson(task, seed))
            except Exception as exc:
                cases.append(dict(base_seed=seed, error=str(exc), measured_risks=['audit_or_generation_failure']))
        records.append(dict(task_id=task['id'], title=task['title'], lessons=cases,
                            acceptance='pending_ui_and_human_video_review'))
        if task['id'] == 68:
            queries = [games.fixture(68, seed) for seed in range(1000,1040)]
            records[-1]['query_direction_counts'] = {
                v: dict(Counter(games.expected(68,v,state) for state in queries)) for v in 'ABC'}
    return dict(scope=list(range(1, 76)), lesson_version=lessons.VERSION, cases=records,
                limits='Extrema use candidate data fields; their visibility and causal relevance require per-task UI review. '
                       'Distinct A/B/C outputs do not exclude unenumerated rival rules. No human learnability acceptance is inferred.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/reviews/teaching-lessons-v3.json')
    args = parser.parse_args()
    result = audit()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(cases=len(result['cases']), risks=dict(Counter(
        risk for case in result['cases'] for lesson in case['lessons'] for risk in lesson['measured_risks'])))))
