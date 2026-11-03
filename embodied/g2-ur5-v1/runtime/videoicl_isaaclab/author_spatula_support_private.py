"""Private E28/E46 source support author; unchanged native scoring."""
from __future__ import annotations
import json
import numpy as np
from .realworld_tool_expert import ToolAuthor,_push_rotation,_unit


class SourceSupportAuthor(ToolAuthor):
    def acquire(self,ref,side):
        self._source_acquire_ref=ref
        try:return super().acquire(ref,side)
        finally:self._source_acquire_ref=None
    def move(self,side,target,guard=None,follower=None,tolerance=.002):
        ref=getattr(self,'_source_acquire_ref',None)
        if ref is not None and np.asarray(target)[2]<.9:
            with(self.a.out/'source-acquire-floor.private.jsonl').open('a')as stream:
                stream.write(json.dumps(dict(stage=self.a.stage,side=side,source_point_task=self.point(ref).tolist(),actuator_target_task=np.asarray(target).tolist(),actual_native_finger_floor_tcp_m=self.a.floor_clear_tcp(side),actual_tip_task=self.tip(side).tolist(),source_object_pose_changed=False))+'\n')
        return super().move(side,target,guard,follower,tolerance)
    def tool(self):
        tool,grip,side=super().tool()
        self.stage('held-spatula-clearance-before-level')
        self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2])],lambda:self.require_held(grip,side))
        normal=_unit(tool['support_normal_local']);outward=_unit(self.s.get('edge_outward_normal_local',[1,0,0]))
        _,actual=self.frame(grip);direction=actual@outward;direction[2]=0
        if np.linalg.norm(direction)<1e-9:raise RuntimeError('Actual support tool has no horizontal source-forward direction')
        target=_push_rotation(normal,outward,direction)
        self.stage('held-spatula-real-level')
        self.rotate_actor(tool['actor'],side,target)
        _,measured=self.frame(grip);normal_z=float((measured@normal)[2]);self.require_held(grip,side)
        with(self.a.out/'source-spatula-level.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(task=self.task,side=side,source_normal_local=normal.tolist(),target_tool_rotation_task=target.tolist(),actual_tool_rotation_task=measured.tolist(),actual_blade_normal_z=normal_z,object_pose_written=False,source_score_modified=False))+'\n')
        if normal_z<=.98:raise RuntimeError('Measured source blade did not level before loading')
        return tool,grip,side


def solve_source_spatula(author):
    if author.scene.spec['id']not in('E28','E46'):raise ValueError('Independent support author accepts onlyE28/E46')
    policy=SourceSupportAuthor(author);policy.spatula()
    (author.out/'spatula-support-operations.private.json').write_text(json.dumps(policy.operations,indent=2)+'\n')
