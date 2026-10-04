"""Operational outputs require source joins and current native saved results."""
from copy import deepcopy
import json
import pytest
from vic import v2, v2_worksets
from vic_apps import worksets,workset_delivery


@pytest.mark.parametrize('task_id',sorted(worksets.TASKS))
def test_rules_alone_do_not_deliver_and_source_or_stale_documents_fail(task_id):
    initial=v2.generate(task_id,10007,'eval');state=initial;events=[]
    for op,target,value,ids in v2_worksets.reference_commands(initial,'A',include_delivery=False):
        state=worksets.apply(state,op,target,value,ids);events.append(dict(op=op,target=target,value=value,ids=ids))
    result=v2.evaluate(initial,state,'A',events)
    assert not result['success'] and 'delivery:published' in result['violations']
    for op,target,value,ids in v2_worksets.delivery_commands(initial,'A',v2_worksets.reference_commands(initial,'A',include_delivery=False)):
        state=worksets.apply(state,op,target,value,ids);events.append(dict(op=op,target=target,value=value,ids=ids))
    assert v2.evaluate(initial,state,'A',events)['success']
    for change in ('wrong_recipient','obsolete_request','wrong_reference','wrong_business_detail','missing_object','stale_snapshot','unsaved_document'):
        bad=deepcopy(state);publication=bad['workset_delivery']['publications'][-1];draft=publication['document']
        if change=='wrong_recipient':draft['address']='other@example.test'
        elif change=='obsolete_request':draft['request']=initial['workset_delivery']['requests'][0]['id']
        elif change=='wrong_reference':draft['rows'][0]['reference']='REF-OTHER'
        elif change=='wrong_business_detail':draft['rows'][0]['detail']='未核对的资料'
        elif change=='missing_object':draft['rows'].pop()
        elif change=='stale_snapshot':draft['rows'][0]['snapshot']['object']['label']='过期分类'
        else:bad['workset_delivery']['draft']['title']='交付后修改的草稿'
        assert not v2.evaluate(initial,bad,'A',events)['success'],change
    # Relevant app edits require refreshing the document row before republishing.
    changed=deepcopy(state);key=changed['workset_delivery']['draft']['rows'][0]['object']
    changed['domain']['objects'][key]['label']='需要重新确认'
    with pytest.raises(ValueError,match='数据已变动'):
        worksets.apply(changed,'assignment.publish')


def test_draft_rows_are_editable_and_publish_keeps_real_downloadable_versions():
    initial=v2.generate(23,10007,'eval');state=initial
    for op,target,value,ids in v2_worksets.reference_commands(initial,'B'):
        state=worksets.apply(state,op,target,value,ids)
    first=state['workset_delivery']['publications'][0]
    draft=state['workset_delivery']['draft'];data={k:v for k,v in draft.items() if k!='rows'}
    data['summary']='本期已按分类整理专题文章，责任编辑信息来自轮值登记表。'
    state=worksets.apply(state,'assignment.draft',value=json.dumps(data))
    assert not v2.evaluate(initial,state,'B',[dict(op='assignment.draft')])['success']
    state=worksets.apply(state,'assignment.publish')
    assert len(state['workset_delivery']['publications'])==2
    assert state['workset_delivery']['publications'][0]==first
    assert v2.evaluate(initial,state,'B',[dict(op='assignment.publish')])['success']
    assert len([key for key in state['domain']['files'] if key.startswith('delivery-')])==2


@pytest.mark.parametrize('task_id',[22,47,48,53])
def test_downloaded_business_document_contains_operational_information(task_id):
    initial=v2.generate(task_id,10007,'eval');state=initial
    for op,target,value,ids in v2_worksets.reference_commands(initial,'A'):
        state=worksets.apply(state,op,target,value,ids)
    body=state['workset_delivery']['publications'][-1]['body']
    required={22:['歌手：','版本：录音室版','时长（秒）：'],47:['出发站：北京南','到达站：上海虹桥','出发：','到达：','票价：'],48:['供应商：','询价邮箱：','规格：','需求数量：'],53:['凭证号：PZ-','账户：','金额：','交易时间：']}
    for label in required[task_id]:assert label in body
