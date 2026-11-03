"""E08 guard preserves every actual cooked shoe piece instead of filling its gaps."""
import numpy as np
from .execution_design_branch_geometry import HeldGeometry,collision_parts_task,swept_pose_clearance


class SourceShoeGeometry(HeldGeometry):
    def check(self,target=None,rotation=None):
        from .execution_design_e33_grasp import actual_mesh
        from .execution_design_thin_edge import table_bounds_task
        if self.require_hold:self.p.require_held(dict(actor=self.actor),self.side)
        tip=self.p.tip(self.side);target=tip if target is None else target;rotation=np.eye(3)if rotation is None else rotation
        bodies={n:actual_mesh(self.p.a,self.side,n)for n in('panda_hand',*self.p.a.scene.embodiment.fingers)}
        state,_=self.p.snapshot();obstacles={n:collision_parts_task(self.p,n)for n in state if not self.require_hold or n!=self.actor}
        top=table_bounds_task(self.p.a.scene)['top'];report=swept_pose_clearance(bodies,tip,target,rotation,obstacles,top)
        pieces=collision_parts_task(self.p,self.actor)if self.require_hold else[]
        reports=[]
        for piece in pieces:
            reports.append(swept_pose_clearance({'payload':piece},tip,target,rotation,obstacles,top,self.allowed))
        report.update(payload_representation='all_actual_native_cooked_convex_pieces',payload_convex_piece_count=len(pieces),
            minimum_table_clearance_m=min([report['minimum_table_clearance_m']]+[r['minimum_table_clearance_m']for r in reports]),
            obstacle_convex_piece_counts={n:len(a)for n,a in obstacles.items()},collision_representation_evidence=getattr(self.p.a,'_branch_collision_parts_evidence',{}))
        self.last_report=report
        return report


class UpwardBoxDepartureGeometry(SourceShoeGeometry):
    """Only leave measured1259 nonpenetrating box proximity upwards."""
    def __init__(self,p,actor,side,context):
        super().__init__(p,actor,side);self.context=context;self.start_tip=p.tip(side).copy();self.rows=[]
    def check(self,target=None,rotation=None):
        import math
        from scipy.spatial import ConvexHull
        from scipy.optimize import linprog
        from .execution_design_e33_grasp import actual_mesh
        from .execution_design_thin_edge import table_bounds_task
        from .execution_design_branch_rotation import accepted_pose_task
        from .execution_design_contact_retreat import convex_exit_certificate
        from .realworld_tool_expert import ToolExecutionError
        p=self.p;p.require_held(dict(actor=self.actor),self.side);tip=p.tip(self.side);target=tip if target is None else np.asarray(target,float)
        if rotation is not None and not np.allclose(rotation,np.eye(3),atol=1e-8):raise ToolExecutionError('Measured box departure may only move UP')
        delta=target-tip
        if np.linalg.norm(delta[:2])>1e-7 or delta[2]<-1e-7:raise ToolExecutionError('Measured box departure permits only UP')
        feedback=p.c.action_feedback()['control_feedback'][self.side]
        if float(feedback['orientation_error_rad'])>float(feedback['orientation_tolerance_rad']):raise ToolExecutionError('Box departure requires the previous public rotation already reached')
        _,r=accepted_pose_task(p,self.side);r=r@np.asarray(p.a.tcp_rotation_task(self.side)).T
        state,_=p.snapshot();obstacles={n:collision_parts_task(p,n)for n in state if n not in(self.actor,'box')};box=collision_parts_task(p,'box');pieces=collision_parts_task(p,self.actor);top=table_bounds_task(p.a.scene)['top']
        if not getattr(self,'saved',False):
            import json
            path=p.a.out/'e08-box-up-departure-cooked-evidence.private.json'
            path.write_text(json.dumps(dict(native_action=p.c.steps,shoe_pieces_task=[a.tolist()for a in pieces],box_pieces_task=[a.tolist()for a in box],tcp_task=tip.tolist())))
            self.saved=True
        bodies={n:actual_mesh(p.a,self.side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)}
        report=swept_pose_clearance(bodies,tip,target,r,{**obstacles,'box':box},top)
        force=float(getattr(p.c,'contact_forces',{}).get(frozenset((self.actor,'box')),0.))
        if force>1.:raise ToolExecutionError('Actual shoe/box force increased during UP departure')
        proofs=[]
        angle=math.acos(float(np.clip((np.trace(r)-1)/2,-1,1)))
        for i,piece in enumerate(pieces):
            swept_pose_clearance({'payload':piece},tip,target,r,obstacles,top)
            end=(piece-tip)@r.T+target;cloud=np.r_[piece,end];arc=float(np.linalg.norm(piece-tip,axis=1).max())*(1-math.cos(angle/2))
            for j,solid in enumerate(box):
                if np.any(cloud.max(0)+.002+arc<solid.min(0))or np.any(solid.max(0)+.002+arc<cloud.min(0)):continue
                h=ConvexHull(cloud);b=ConvexHull(solid);a=np.r_[h.equations[:,:3],b.equations[:,:3]];rhs=-np.r_[h.equations[:,3],b.equations[:,3]]
                padded=linprog([0.,0.,0.],A_ub=a,b_ub=rhs+.001+arc,bounds=[(None,None)]*3,method='highs')
                if padded.status==2:continue
                if not padded.success:raise ToolExecutionError('Box UP separation solver unresolved')
                cert=convex_exit_certificate(piece,solid,[0.,0.,1.],margin=0.)
                raw=linprog([0.,0.,0.],A_ub=a,b_ub=rhs+arc,bounds=[(None,None)]*3,method='highs')
                if raw.success or not cert['monotone_for_entire_translation']:
                    raise ToolExecutionError('Measured box UP departure has actual raw penetration or does not leave it monotonically')
                if raw.status!=2:raise ToolExecutionError('Raw box UP separation unresolved')
                proofs.append(dict(shoe_piece=i,box_piece=j,raw_signed_translation_depth_m=cert['expanded_translation_penetration_m'],
                    upward_normal_projection=cert['outward_public_axis_projection'],raw_complete_sweep_separated=True,padding_only=True))
        record=dict(actual_box_force_n=force,nonpenetrating_padding_departure=proofs,actual_shoe_pieces=len(pieces),actual_box_pieces=len(box),accepted_public_orientation_error_rad=float(feedback['orientation_error_rad']))
        self.context['right_box_up_departure_actual']=record;self.rows.append(record)
        # Preserve exact native cooker vertices and every proof for local audit.
        if not getattr(self,'saved',False):
            import json
            path=p.a.out/'e08-box-up-departure-cooked-evidence.private.json';path.write_text(json.dumps(dict(shoe_pieces_task=[a.tolist()for a in pieces],box_pieces_task=[a.tolist()for a in box],proof=record)))
            self.saved=True
        self.last_report=report;return report
