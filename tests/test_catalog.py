

def test_reviewed_rules_and_qa_answers_agree():
    from pathlib import Path
    import json
    root = Path(__file__).resolve().parents[1]
    tasks = json.loads((root / 'tasks/catalog.json').read_text())['tasks']
    for task in tasks:
        assert {v: entry['answer'] for v, entry in task['qa'].items()} == task['variants']
