"""Restored thin-task engineering suffixes; never whole-task acceptance."""
import json,math
import numpy as np
from .realworld_tool_expert import ToolAuthor,ToolExecutionError

ENTRIES={'e50-cooked-ray-only':'E50','e50-seated-push':'E50','e50-pre-pinch':'E50','e50-direct-card-grasp':'E50','e50-positioned-direct-card-grasp':'E50','e50-side-band-grasp':'E50','e44-before-rail-contact':'E44','e44-counterpress-geometry-only':'E44'}

def save_stage(a,stage,context=None):
    from .engineering_checkpoint import capture
    checkpoint=capture(a.c,stage,context or{})
    path=a.out/('thin-checkpoint-'+stage+'-'+str(a.c.steps)+'.private.json')
    path.write_text(json.dumps(checkpoint,indent=2))
    return dict(path=str(path),checkpoint_sha256=checkpoint['checkpoint_sha256'])

def _ray_queries(a,p,ref):
    """Optional read-only native cooked-shape evidence; no physics advance."""
    try:
        import omni.physx,carb
        query=omni.physx.get_physx_scene_query_interface();point=p.frame(ref)[0];rows=[]
        for dx in(0.,.035,-.035):
            origin=a.scene.task_to_world(np.asarray(point)+[dx,0,.020]);hits=[]
            def report(hit):
                from .source_reviewed_collisions import ray_hit_value
                from pxr import PhysicsSchemaTools
                try:
                    body=ray_hit_value(hit,'rigidBody','rigid_body');body=body if isinstance(body,str)else str(PhysicsSchemaTools.intToSdfPath(body))
                    hits.append(dict(position=list(ray_hit_value(hit,'position')),normal=list(ray_hit_value(hit,'normal')),rigid_body=body,collision=str(ray_hit_value(hit,'collision'))))
                except Exception as exc:
                    hits.append(dict(decode_error=type(exc).__name__+': '+str(exc)));return False
                return len(hits)<40
            query.raycast_all(carb.Float3(*map(float,origin)),carb.Float3(0.,0.,-1.),.05,report);rows.append(dict(origin_world=origin.tolist(),hits=hits))
        return dict(available=True,scene_query_support=carb.settings.get_settings().get('/physics/enableSceneQuerySupport'),rays=rows)
    except Exception as exc:return dict(available=False,error=type(exc).__name__+': '+str(exc))

def _orient_actual_surface(p,side,floor,outward):
    """Choose nearby public half-degree turns from the actual closed mesh.

    A fixed0.1degree target is finer than the API's0.5degree minimum; the
    physical goal here is the actual contact face, not that arbitrary angle.
    """
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_card_push_surface import leading_surface
    from .realworld_tool_expert import _axis_rotation
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    for _ in range(8):
        tcp=p.tip(side);meshes=[actual_mesh(p.a,side,n)-tcp for n in p.a.scene.embodiment.fingers];palm=actual_mesh(p.a,side,'panda_hand')-tcp
        def score(turn):
            transformed=[m@turn.T for m in meshes];z=floor+.00002-min(float(m[:,2].min())for m in transformed)
            if float((palm@turn.T+[0,0,z])[:,2].min())<floor+.0002:return None
            try:face=leading_surface([m+[0,0,z]for m in transformed],floor+.000175,outward)
            except ValueError:return None
            return face
        current=score(np.eye(3))
        if current is not None:return current
        choices=[]
        for degrees in(.5,1.,1.5,2.):
            for axis in range(3):
                for sign in(-1.,1.):
                    face=score(_axis_rotation(np.eye(3)[axis],math.radians(sign*degrees)))
                    if face is not None:choices.append((degrees,abs(face['vertical_normal']),axis,sign,face))
            if choices:break
        if not choices:raise ToolExecutionError('No nearby actual table-clear horizontal card push surface')
        degrees,_,axis,sign,face=min(choices,key=lambda x:(x[0],x[1]));p.act(side,labels[axis][int(sign<0)],degrees=degrees)
    raise ToolExecutionError('Actual card push face did not converge under bounded public turns')


def _lower_to_table_band(p,side,floor):
    from .execution_design_card_direct import refine_open_toe_height
    low=float(p.a.finger_geometry(side)['lowest_z_task_m'])
    if low>floor+.00025:
        target=p.tip(side).copy();target[2]+=floor+.00020-low
        p.move(side,target,tolerance=.0001)
    return refine_open_toe_height(p,side,floor)


def solve(author,checkpoint,context):
    request=context;entry=request.get('entry');options=request.get('context',{})
    if entry not in ENTRIES or author.scene.spec['id']!=ENTRIES[entry]:raise ValueError('Unknown thin-task restored suffix')
    if not getattr(author,'_engineering_resume_checkpoint',None):raise ValueError('Native startup restore required before thin suffix')
    if not author.control_report.get('engineering_reference_only'):raise ValueError('Engineering-only suffix authorization required')
    p=ToolAuthor(author);start=p.c.steps;report=dict(entry=entry,diagnostic_only=True,whole_task_positive=False,restored=True)
    save_stage(author,'suffix-start',dict(entry=entry))
    try:
        if entry=='e44-counterpress-geometry-only':
            from .engineering_thin_arm_audit import audit
            result=audit(author);save_stage(author,'arm-geometry-audit',dict(entry=entry))
            report.update(actions=p.c.steps-start,diagnostic_measurement_completed=True,segment_passed=False,native_positive_passed=False)
            (author.out/'thin-suffix-result.private.json').write_text(json.dumps(report,indent=2));return report
        if entry=='e44-before-rail-contact':
            from .execution_design_fold_rails import raise_onto_rails
            observer=None
            if options.get('native_cross_arm_readback'):
                from .engineering_thin_arm_audit import audit
                from .engineering_thin_arm_contacts import install
                audit(author);observer=install(author)
            try:
                if options.get('normal_fold_only'):
                    result=dict(preparation_reused_from_actual_raised_checkpoint=True)
                else:
                    result=raise_onto_rails(p,resume=True,counterpress_override=not p.s['execution_design_fold_fixture'].get('single_pusher',False),left_clear_already_raised=options.get('left_clear_already_raised',False),left_clear_already_high=options.get('left_clear_already_high',False),avoid_cross_arm=options.get('avoid_cross_arm',False),left_low_side_lane=options.get('left_low_side_lane',False),presser_y_local=float(options.get('presser_y_local',-.040)),presser_x_local=float(options.get('presser_x_local',-.025)),relocate_presser=options.get('relocate_presser',False),retain_existing_push_setup=options.get('retain_existing_push_setup',False),minimum_raise_deg=float(options.get('minimum_raise_deg',20.)),minimum_edge_z=float(options.get('minimum_edge_z',.835)))
                save_stage(author,'rail-raised',dict(entry=entry,result=result));report['result']=result
                if options.get('contact_compress_only'):
                    from .execution_design_fold_contact_push import complete as contact_complete
                    report['contact_fold_result']=contact_complete(p,reuse_grip=options.get('reuse_actual_leaf_grip',False))
                if options.get('finish_passive_guide_after_raise'):
                    from .execution_design_fold_contact_push import complete_passive_guide
                    report['released_guide_result']=complete_passive_guide(p,raised_result=result)
                if options.get('continue_normal_fold'):
                    from .execution_design_fold_normal_grasp import complete
                    report['normal_fold_result']=complete(p,clearance_target_z=options.get('clearance_target_z'),grasp_side=options.get('fold_grasp_side','left'),face_normal_only=options.get('face_normal_only',False))
            finally:
                if observer:observer()
        else:
            ref=p.s['card_grasp'];ref=dict(ref,actor=ref.get('actor','card'))
            side=options.get('side','left')
            if side not in('left','right'):raise ValueError('Physical hand required')
            from .execution_design_thin_edge import table_bounds_task,material_collision_points_task
            from .execution_design_e33_grasp import actual_mesh
            floor=table_bounds_task(author.scene)['top']
            def log(phase,**values):
                state,contacts=p.snapshot();row=dict(phase=phase,step=p.c.steps,card_state={k:(v.tolist()if hasattr(v,'tolist')else v)for k,v in state[ref['actor']].items()},
                    tcp=p.tip(side).tolist(),rotation=author.tcp_rotation_task(side).tolist(),
                    material_vertices=material_collision_points_task(p,ref).tolist(),fingers=[actual_mesh(author,side,n).tolist()for n in author.scene.embodiment.fingers],
                    contacts=[sorted(pair)for pair in contacts if ref['actor']in pair],contact_forces=[dict(pair=sorted(pair),force_n=float(force))for pair,force in p.c.contact_forces.items()if ref['actor']in pair],**values)
                with(author.out/'thin-suffix.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
            log('restored-native-state',native_queries=_ray_queries(author,p,ref))
            if entry=='e50-cooked-ray-only':
                from .engineering_cooked_geometry_audit import audit
                result=audit(author,p,ref,side);save_stage(author,'cooked-ray-audit',dict(entry=entry))
                report.update(actions=p.c.steps-start,diagnostic_measurement_completed=result['all_bodies_observed'],segment_passed=False,native_positive_passed=False,native_queries_available=result['native_queries_available'])
                (author.out/'thin-suffix-result.private.json').write_text(json.dumps(report,indent=2));return report
            if entry=='e50-side-band-grasp':
                if options.get('clear_existing_plate_rim'):
                    from .execution_design_e50_card_plate_clearance import clear_plate_rim
                    clear_plate_rim(p,ref,side,resume_pusher=bool(options.get('resume_plate_pusher',False)))

                if options.get('trace_current_grasp'):
                    from .engineering_thin_grasp_trace import close_current
                    report['raised_m']=close_current(p,ref,side,options['expected_q_m'],card_face_fraction=float(options.get('card_face_fraction',.85)),initial_lift_step_mm=float(options.get('initial_lift_step_mm',2.)))
                else:
                    from .engineering_card_side_grasp import acquire
                    report['raised_m']=acquire(p,ref,side,empty_clear_completed=options.get('empty_clear_completed',False),card_face_fraction=float(options.get('card_face_fraction',.85)),precision_full_down=bool(options.get('precision_full_down',False)),initial_lift_step_mm=float(options.get('initial_lift_step_mm',2.)),centered_com_grasp=bool(options.get('centered_com_grasp',False)),resume_side_trim=bool(options.get('resume_side_trim',False)))
                if options.get('continue_after_lift') is False:
                    if p.s.get('engineering_contact_skin_diagnostic',{}).get('diagnostic_only') is not True:
                        raise ValueError('Lift-only comparison requires explicit skin diagnostic')
                    report.update(actions=p.c.steps-start,segment_passed=True,native_positive_passed=False,numerical_skin_lift_comparison_only=True)
                    (author.out/'thin-suffix-result.private.json').write_text(json.dumps(report,indent=2));return report
                clip,=p.s['clips'].values()
                save_stage(author,'before-card-flip-and-clip',dict(entry=entry))
                p.clip_card_after_grasp(ref['actor'],clip,ref)
            elif entry in('e50-direct-card-grasp','e50-positioned-direct-card-grasp'):
                from .execution_design_cutlery_grasp import orient
                from .execution_design_card_direct import acquire_direct_card
                if entry=='e50-direct-card-grasp':
                    p.stage('restored-card-empty-full-down');p.act(side,'UP',mm=10.)
                    p.act(side,'RELEASE');orient(author,side,np.diag([1.,-1.,-1.]))
                save_stage(author,'before-direct-thin-pinch',dict(entry=entry))
                acquire_direct_card(p,ref,side)
                log('actual-direct-card-grasp',bilateral=p.held(ref,side));save_stage(author,'real-card-lift',dict(entry=entry))
            elif entry=='e50-pre-pinch':
                from .execution_design_card_direct import refine_open_toe_height
                _lower_to_table_band(p,side,floor);log('actual-toe-refined');save_stage(author,'before-real-pinch',dict(entry=entry))
                for _ in range(6):
                    p.act(side,'GRASP');log('real-pinch',bilateral=p.held(ref,side))
                    if p.held(ref,side):break
                else:raise ToolExecutionError('Restored thin pinch has no actual bilateral grip')
                save_stage(author,'first-bilateral-contact',dict(entry=entry));original=p.frame(ref)[0].copy()
                for _ in range(30):
                    p.require_held(ref,side);p.act(side,'UP',mm=1.);p.require_held(ref,side)
                    if p.frame(ref)[0][2]-original[2]>=.025:break
                else:raise ToolExecutionError('Restored bilateral grip did not lift actual card25mm')
                log('actual-lift',raised_m=float(p.frame(ref)[0][2]-original[2]));report['raised_m']=float(p.frame(ref)[0][2]-original[2])
                save_stage(author,'real-card-lift',dict(entry=entry))
            else:
                from .execution_design_card_push_surface import leading_surface
                from .execution_design_cutlery_grasp import orient
                from .execution_design_card_direct import refine_open_toe_height
                outward=np.asarray(options.get('outward',[-1.,0.,0.]),float);outward/=np.linalg.norm(outward)
                if abs(outward[2])>.001 or max(abs(outward[:2]))<.999:raise ValueError('Axis-aligned real public push required')
                if 'target_rotation'in options:
                    target=np.asarray(options['target_rotation'],float)
                    if target.shape!=(3,3)or not np.allclose(target.T@target,np.eye(3),atol=1e-6):raise ValueError('Proper target rotation required')
                    if float(author.finger_geometry(side)['lowest_z_task_m'])<floor+.002:p.act(side,'UP',mm=5.)
                    _orient_actual_surface(p,side,floor,outward);_lower_to_table_band(p,side,floor)
                face=leading_surface([actual_mesh(author,side,n)for n in author.scene.embodiment.fingers],floor+.000175,outward)
                log('actual-leading-face-verified',face=face);save_stage(author,'actual-push-face',dict(entry=entry,outward=outward.tolist()))
                def contact():return any(p.contact(ref['actor'],f'{side}_finger{i}')for i in(1,2))
                axis=int(np.argmax(abs(outward)));token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(outward[axis]<0)]
                for _ in range(12):
                    if contact():break
                    p.act(side,token,mm=.5);log('seek-real-contact')
                else:
                    if not contact():raise ToolExecutionError('Restored horizontal toe has no actual card contact')
                save_stage(author,'first-real-push-contact',dict(entry=entry));origin=p.frame(ref)[0].copy();distance=float(options.get('distance_m',.005))
                if not .001<=distance<=.030:raise ValueError('Bounded diagnostic push distance required')
                for _ in range(80):
                    if not p.contact(ref['actor'],'table')or not contact():raise ToolExecutionError('Restored push lost real support or finger contact')
                    p.act(side,token,mm=.5);log('real-contact-push')
                    if not p.contact(ref['actor'],'table')or not contact():raise ToolExecutionError('Restored push lost native support/contact after action')
                    if float((p.frame(ref)[0]-origin)@outward)>=distance:break
                else:raise ToolExecutionError('Restored card did not advance under actual contact')
                report['actual_displacement_m']=float((p.frame(ref)[0]-origin)@outward);save_stage(author,'real-push-distance',dict(entry=entry,displacement=report['actual_displacement_m']))
        report['actions']=p.c.steps-start;report['segment_passed']=True;report['native_positive_passed']=False
        (author.out/'thin-suffix-result.private.json').write_text(json.dumps(report,indent=2));return report
    except Exception as exc:
        try:save_stage(author,'failure',dict(entry=entry,error=type(exc).__name__+': '+str(exc)))
        except Exception as capture_error:
            (author.out/'thin-suffix-capture-error.private.json').write_text(json.dumps(dict(error=type(capture_error).__name__+': '+str(capture_error))))
        raise
