"""Candidate-only QA/no-rule contracts. No model API, sockets, SSH or simulator."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import sys

from mcp.types import CallToolResult,ImageContent
import pytest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from standalone_qa_tools import StandaloneQA,make_server,public_question
sys.path.insert(0,str(HERE.parents[1]/'native-codex-20261106/VideoICLBench/packages/sdk'))


class Reader:
    def info(self):return dict(available=True,duration_seconds=7.3,fps=30)
    def frame(self,t):return CallToolResult(content=[ImageContent(type='image',data=base64.b64encode(b'FAKE').decode(),mimeType='image/png')])


@pytest.fixture
def cfg(tmp_path):
    video=tmp_path/'assigned.mp4';video.write_bytes(b'ORIGINAL_VIDEO_FAKE_FIXTURE')
    return dict(schema='standalone-video-qa-v1',identity=dict(qa_id='qa-one',task='E22',variant='C',seed=4201),
        video_path=str(video),video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),output_dir=str(tmp_path/'qa'),api_timing_log=str(tmp_path/'qa/api-timing.private.jsonl'),
        question=dict(question_id='question-one',prompt='Which public rule is shown?',options=dict(A='one',B='two',C='three',D='four'),response_instruction='A/B/C/D'))


def test_QA_tools_are_video_and_answer_only_no_controller(cfg):
    b=StandaloneQA(cfg,reader=Reader());tools=asyncio.run(make_server(b).list_tools())
    assert {x.name for x in tools}=={'demo_info','demo_frames','qa_question','qa_answer'}
    assert not {'act','observe','done','giveup','program','depth_points'}&{x.name for x in tools}


def test_video_before_question_first_valid_answer_frozen_without_correctness(cfg):
    b=StandaloneQA(cfg,reader=Reader())
    with pytest.raises(ValueError,match='Inspect'):b.issue()
    b.frames([1,2]);q=b.issue();assert q['complete_video_viewing_proven']is False
    assert b.submit('E')['status']=='invalid_format'and not b.answer_path.exists()
    assert b.submit('B')=={'status':'submitted','correctness_returned':False}
    assert b.submit('A')['reused_first_answer']is True
    assert json.loads(b.answer_path.read_text())['selected_option']=='B'
    r=StandaloneQA(cfg,reader=Reader());assert r.submit('D')['reused_first_answer']is True
    with pytest.raises(ValueError,match='already answered'):r.frames([0])


def test_QA_public_packet_rejects_answerkey_and_different_video(cfg):
    with pytest.raises(ValueError,match='public question'):public_question(dict(cfg['question'],correct_option='B'))
    Path(cfg['video_path']).write_bytes(b'CHANGED')
    with pytest.raises(ValueError,match='SHA'):StandaloneQA(cfg,reader=Reader())


def test_first_answer_fences_new_upstream_but_drains_already_active_without_cancel(cfg):
    from vic_sdk.api_timing import append_timing_event
    from vic_sdk.episode_api_admission import register_api_request_start,EpisodeApiClosed
    import threading,time
    b=StandaloneQA(cfg,reader=Reader());b.frames([0]);b.issue()
    register_api_request_start(b.timing,'generating-first-answer')
    thread=threading.Thread(target=lambda:(time.sleep(.08),append_timing_event(b.timing,'request_end',request_id='generating-first-answer',outcome='success',failure_kind=None)))
    thread.start();start=time.monotonic();b.submit('A');thread.join()
    assert time.monotonic()-start>=.07 and b.answer_path.exists()
    with pytest.raises(EpisodeApiClosed):register_api_request_start(b.timing,'unnecessary-after-answer')


def test_unknown_api_does_not_commit_answer_or_silently_clear_ledger(cfg):
    from vic_sdk.api_timing import append_timing_event
    from vic_sdk.episode_api_admission import register_api_request_start
    b=StandaloneQA(cfg,reader=Reader());b.frames([0]);b.issue()
    register_api_request_start(b.timing,'unknown')
    append_timing_event(b.timing,'request_end',request_id='unknown',outcome='unknown',failure_kind='unverified_response_completion')
    with pytest.raises(ValueError,match='not reconciled'):b.submit('A')
    assert not b.answer_path.exists()


@pytest.mark.parametrize('seconds',[[],[-1],[7.3],[float('nan')],[0]*13])
def test_QA_bad_timestamps_never_delivered(cfg,seconds):
    b=StandaloneQA(cfg,reader=Reader())
    with pytest.raises(ValueError):b.frames(seconds)
    assert b.state['delivered']==[]
