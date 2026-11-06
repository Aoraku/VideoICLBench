"""Native Stop hook for standalone QA; reads only its first-answer receipt."""
import argparse
import json
from pathlib import Path
import sys

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--answer',type=Path,required=True);a=p.parse_args();sys.stdin.read()
    if a.answer.is_file():print('{}')
    else:print(json.dumps(dict(decision='block',reason='Inspect the assigned video using demo tools, call qa_question, then qa_answer with one uppercase option A/B/C/D. This is QA only; no robot/world or workspace task exists.')))
