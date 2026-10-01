"""Offline protocol tests. Fake model responses are NOT ICL benchmark results."""
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import hosted_operator as h

D = {'left':'MV_UP','right':'STILL','step_m':.005,'finish':False,'summary':'Lift slightly.'}

class FakeEnvironment:
    def __init__(self):
        self.status='running'; self.rev=0; self.steps=0; self.actions=[]
    def __call__(self, path, body):
        state={'status':self.status,'steps':self.steps,'max_pairs':5,'gripper_closed':{'left':False,'right':False},
               'ee_pos':'DO_NOT_SEND', 'variant':'DO_NOT_SEND', 'task_done':'DO_NOT_SEND'}
        if path=='/api/observe':
            return {'ok':True,'observation_id':str(self.rev),'state':state,'images':{k:'aW1hZ2U=' for k in h.CAMERAS}}
        if body['expected_observation']!=str(self.rev):
            raise ValueError('stale')
        self.actions.append((path,body));self.rev+=1;self.steps+=1
        if path=='/api/stop':self.status='submitted'
        state.update(status=self.status, steps=self.steps)
        return {'ok':True,'state':state}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.op=h.Operator('http://env','https://model/v1','test-model','test-secret',self.tmp.name)
        self.env=FakeEnvironment();self.op.env=self.env;self.op.demos=['aW1hZ2U=']*12

    def response(self, d=D):
        return json.dumps({'choices':[{'message':{'content':json.dumps(d),'reasoning_content':'DO_NOT_SEND'}}]}).encode()

    def test_whitelist_exact_inputs(self):
        obs=self.op.observe();p=h.payload('test',self.op.demos,obs,[])
        self.assertNotIn('DO_NOT_SEND',json.dumps(p));self.assertNotIn('observation_id',json.dumps(p))
        self.assertEqual(sum(x['type']=='image_url' for x in p['messages'][1]['content']),16)
        with patch.object(h,'request',return_value=self.response()):self.op.turn(0)
        self.assertEqual(self.env.actions[0][1]['left'],['MV_UP'])
        all_logs=''.join(p.read_text() for p in self.op.run_dir.iterdir())
        self.assertNotIn('test-secret',all_logs);self.assertNotIn('DO_NOT_SEND',all_logs)

    def test_invalid_decisions(self):
        for change in ({'left':'PICK_RED'}, {'step_m':1}, {'finish':'false'}, {'summary':'x'*401}, {'tcp':[0,0,0]}, {'finish':True}):
            with self.subTest(change=change),self.assertRaises(ValueError):h.decision(json.dumps({**D,**change}))

    def test_pause_discards_inflight_response(self):
        def response(*args,**kwargs):
            self.op.control('pause');return self.response()
        with patch.object(h,'request',side_effect=response):self.op.turn(0)
        self.assertFalse(self.env.actions)
        self.assertEqual(self.op.events[-1]['kind'],'discarded')

    def test_stale_action_rejected(self):
        def response(*args,**kwargs):
            self.env.rev+=1;return self.response()
        with patch.object(h,'request',side_effect=response),self.assertRaises(ValueError):self.op.turn(0)
        self.assertFalse(self.env.actions)

    def test_finish_is_submission(self):
        d={**D,'left':'STILL','finish':True}
        with patch.object(h,'request',return_value=self.response(d)):self.op.turn(0)
        self.assertEqual(self.env.actions[0][0],'/api/stop');self.assertEqual(self.op.mode,'stopped')

    def test_failure_pauses_no_retry(self):
        with patch.object(h,'request',side_effect=RuntimeError('test-secret')) as r:self.op.loop(0)
        self.assertEqual(r.call_count,1);self.assertFalse(self.env.actions);self.assertFalse(self.op.busy)
        self.assertEqual(self.op.mode,'paused');self.assertNotIn('test-secret',json.dumps(self.op.status()))

    def test_call_budget(self):
        self.op.max_calls=1;self.op.mode='running'
        with patch.object(h,'request',return_value=self.response()) as r:self.op.loop(0)
        self.assertEqual(r.call_count,1);self.assertEqual(len(self.env.actions),1)

    def test_stop_is_terminal(self):
        self.op.control('stop');self.op.control('pause')
        with self.assertRaises(ValueError):self.op.control('run')

if __name__=='__main__':unittest.main()
