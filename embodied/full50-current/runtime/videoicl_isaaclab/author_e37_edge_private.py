"""Actual axial handle pinch outside the table for the original screwdriver."""
import json
import numpy as np
from .author_mplib_planner import plan,_quat
from .realworld_tool_expert import ToolExecutionError


def acquire_driver_edge(policy,ref,side):
    p=policy
    p.stage('E37-original-driver-axial-edge-grip')
    if not p.contact(ref['actor'],'table'):
        raise ToolExecutionError('Original source driver lacks initial real table support')
    p.act(side,'RELEASE')
    p.c.grips[side]=.024;p.act()
    # After the real90deg tool lift this equivalent finger assignment becomes
    # the ordinary palm-down grasp above the screw head.
    hand=np.array([[0.,0.,1.],[0.,-1.,0.],[1.,0.,0.]])
    point=p.point(ref)
    for distance in (.06,.02,0.):
        target=point-np.array([distance,0.,0.])
        proposal=plan(p.a.scene,p.c,side,target.tolist(),task_tcp_quaternion=_quat(hand).tolist())
        with(p.a.out/'E37-source-edge-plans.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(target=target.tolist(),status=proposal.get('status'),verified=proposal.get('verified'),diagnostics=proposal.get('diagnostics')),default=lambda v:v.tolist())+'\n')
        if proposal.get('status')!='Success' or proposal.get('verified')is not True:
            raise ToolExecutionError('No wholeworld verified axial driver approach')
        p.a.execute_joint_path(side,proposal)
    if p.a.scene.embodiment.config.get('author_recording',{}).get('e37_gradual_source_grip',False):
        # Re-measure the source material point before squeezing. The source
        # SDF handle can roll on the table; a frozen old endpoint is insufficient.
        p.a.move_smooth({side:p.point(ref)},tolerance=.0005,max_speed=.015,max_acceleration=.08)
        stable=0;closing=.020
        for index in range(35):
            p.c.grips[side]=closing;p.act()
            sensor,labels=p.a.scene.contacts[ref['actor']]
            matrix=sensor.data.force_matrix_w[0].sum(axis=0).cpu().numpy()
            forces=[matrix[labels.index(f'{side}_finger{i}')]for i in (1,2)]
            norms=[float(np.linalg.norm(v))for v in forces]
            opposition=float(-forces[0]@forces[1]/max(norms[0]*norms[1],1e-12))
            valid=p.held(ref,side)and min(norms)>.7 and opposition>.7
            stable=stable+1 if valid else 0
            with(p.a.out/'E37-real-gradual-handle-grip.private.jsonl').open('a')as stream:
                stream.write(json.dumps(dict(iteration=index,commanded_half_opening_m=closing,
                    actual_point_task=p.point(ref).tolist(),actual_tcp_task=p.tip(side).tolist(),
                    native_finger_forces_world_n=[v.tolist()for v in forces],opposition=opposition,
                    genuine_opposed_grip=bool(valid)))+'\n')
            if stable>=3:break
            if not p.contact(ref['actor'],'table')and not all(n>.1 for n in norms):
                raise ToolExecutionError('Source handle left table without actual supported pinch')
            if not valid:closing=max(.002,closing-.0005)
        else:raise ToolExecutionError('No stable actual opposed source handle grip')
    else:
        for _ in range(5):
            p.act(side,'GRASP')
            if p.held(ref,side):break
        else:raise ToolExecutionError('Original driver did not acquire actual opposed handle grip')
    # Separate the real source before the subsequent loaded-world planning.
    p.move(side,p.tip(side)+[0.,0.,.008],lambda:p.require_held(ref,side),tolerance=.002)
