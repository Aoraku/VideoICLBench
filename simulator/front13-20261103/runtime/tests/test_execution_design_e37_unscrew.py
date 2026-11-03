from types import SimpleNamespace as N
import numpy as np
from videoicl_isaaclab.execution_design_e37_unscrew import finish_role


def test_held_tool_outside_slot_can_reset_and_reenter_before_turn(tmp_path,monkeypatch):
    state=dict(angle=0.,axial=0.,overlap=.019,fixture_contact=0.,driver_force=0.,depth=0.,cos=1.,aligned=True)
    inserted=[False];calls=[];rooms=iter([.03,2.])
    c=N(steps=0,evaluator=N(screw_measure=lambda entry:dict(state),thread_history_valid=True),_engineering_diagnostic_only=True)
    a=N(out=tmp_path,_engineering_stage_checkpoints=False,scene=N())
    p=N(a=a,c=c,start=0,limit=10,objects={'screw':{'size':[.018,.021,.026]}},
        point=lambda ref:np.array([0.,0.,.001]),require_held=lambda *args:None,
        snapshot=lambda:({'driver':{'pos':[0,0,1.15],'mat':np.eye(3)}},set()),
        _e37_table_readback=lambda:dict(read_errors={},all_link_table_peak_force_n={'left/panda_link6':0.}))
    p.stage=lambda stage:setattr(a,'stage',stage)
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_regrip._scope',lambda p:None)
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_blade.Blade',lambda *args:N(
        local=[np.array([[0,0,-.01],[0,0,.01]])],
        physical_groove_measurement=lambda:dict(physical_tip_inside_original_groove=inserted[0])))
    monkeypatch.setattr('videoicl_isaaclab.execution_design_thin_edge.table_bounds_task',lambda scene:dict(top=.8))
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_regrip._hand',lambda *args:np.eye(3))
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_regrip._plan',lambda *args,**kwargs:{'verified':True})
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_regrip._execute',lambda *args,**kwargs:calls.append('real-withdraw'))
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_planned_approach.run',lambda *args,**kwargs:calls.append('real-return'))
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_regrip.measured_turn_room',lambda *args:dict(safe_angle_rad=next(rooms)))
    def reset(*args,**kwargs):
        assert args[4]()and not a._engineering_stage_checkpoints
        calls.append('real-reset')
    def reseat(*args,**kwargs):
        assert kwargs['torque_degrees']==0.
        calls.append('real-reentry');inserted[0]=True
    def turn(*args,**kwargs):
        kwargs['extra_guard']();calls.append('real-turn')
        state.update(angle=.5,axial=.00024,overlap=0.,fixture_contact=0.,driver_force=.5)
        c.steps+=1
        return dict(target_reached=True)
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_regrip.regrip',reset)
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_planned_slot.run',reseat)
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_regrip.helical_turn',turn)
    entry=dict(screw='screw',pitch_m=.00299,unscrew_direction=1,driver=dict(actor='driver',tip_local=[0,0,0]))
    result=finish_role(p,{'actor':'driver'},'left',entry,[0,0,1],lambda:np.zeros(3))
    assert calls==['real-withdraw','real-reset','real-return','real-reentry','real-turn']
    assert result['actual_original_thread_separated']and not result['native_task_acceptance']
