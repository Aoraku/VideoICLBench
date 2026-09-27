"""The OJ list must expose the dates and line counts used to select submissions."""
import importlib.util
from datetime import datetime
import pytest
from vic import business
from vic.config import ROOT
from vic_apps.domain import initialize


@pytest.mark.parametrize('seed',[0,1,1000,10001])
def test_oj_visible_submission_metadata_agrees_with_content_and_selection(seed,monkeypatch):
    spec=importlib.util.spec_from_file_location('metadata_bridge',ROOT/'apps/code/app/benchmark_bridge.py')
    bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
    state=initialize(business.generate(64,seed))
    monkeypatch.setattr(bridge,'business',lambda *args,**kwargs:{'state':state})
    result,error=bridge.api_request('GET','/api/submissions')
    assert error is None and result['code']==200
    rows=result['data']['submissions']
    dates=[datetime.fromisoformat(row['created_at']) for row in rows]
    assert len({date.date() for date in dates})>1
    latest=max(rows,key=lambda row:datetime.fromisoformat(row['created_at']))
    earliest=min(rows,key=lambda row:datetime.fromisoformat(row['created_at']))
    longest=max(rows,key=lambda row:len(row['code'].splitlines()))
    for variant,wanted in enumerate((latest,earliest,longest)):
        assert business.targets(64,variant,state['items'],state['source'])==[wanted['benchmark_object']]
    captions=[]
    monkeypatch.setattr(bridge.st,'caption',captions.append)
    monkeypatch.setattr(bridge.st,'button',lambda *args,**kwargs:False)
    for row in rows:
        assert row['lines']==len(row['code'].splitlines())
        bridge.extra_submission(row)
        stamp=row['created_at'].replace('T',' ').removesuffix('+00:00')
        assert stamp+' UTC' in captions[-1]
        assert '时间序号' not in captions[-1]
