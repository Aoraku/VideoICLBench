"""Engineering RGB admission diagnostics; never changes camera or physics state."""
import numpy as np

VIEWS=('head','left_wrist','right_wrist')


def camera_audit(scene, images):
    errors=[];views={};centered=[]
    for name in VIEWS:
        a=np.asarray(images[name]);values=a.astype(float)
        if a.ndim!=3 or a.shape[2]!=3 or a.dtype!=np.uint8:
            raise ValueError('Native RGB uint8 HxWx3 required: '+name)
        std=values.std(axis=(0,1));dynamic=np.percentile(values,99,axis=(0,1))-np.percentile(values,1,axis=(0,1))
        chroma=np.max(values,axis=2)-np.min(values,axis=2)
        # Conservative failure of the entire three-view set, not a claim that
        # one occluded wrist or naturally white surface is itself invalid.
        flat_gray=bool(max(std)<6 and max(dynamic)<30 and np.percentile(chroma,99)<8)
        row=dict(channel_std=std.tolist(),percentile_1_99_range=dynamic.tolist(),
                 chroma_percentile_99=float(np.percentile(chroma,99)),near_uniform_gray=flat_gray)
        gradient=max(float(np.abs(np.diff(values,axis=0)).mean()),float(np.abs(np.diff(values,axis=1)).mean()))
        row['mean_neighbor_gradient']=gradient
        row['smooth_low_content_gray']=bool(max(std)<12 and max(dynamic)<55
            and np.percentile(chroma,99)<30 and gradient<.5)
        yy=np.linspace(0,a.shape[0]-1,32,dtype=int);xx=np.linspace(0,a.shape[1]-1,32,dtype=int)
        sample=values[yy[:,None],xx[None,:]];centered.append(sample-sample.mean(axis=(0,1)))
        try:
            calibration=scene.rgb_camera_calibration(name);row['actual_calibration']=calibration
            if calibration.get('available')is not True:raise ValueError('Actual camera pose unavailable')
            world=np.asarray(calibration['T_world_from_camera_optical'],float)
            task=np.asarray(calibration['T_task_from_camera_optical'],float)
            if world.shape!=(4,4)or task.shape!=(4,4)or not np.isfinite(np.r_[world.ravel(),task.ravel()]).all():
                raise ValueError('Invalid actual camera transform')
            if name=='head' and scene.spec.get('head_view'):
                view=scene.spec['head_view'];eye=np.asarray(view['eye_task'],float);target=np.asarray(view['target_task'],float)
                forward=(target-eye)/np.linalg.norm(target-eye);actual=task[:3,2]/np.linalg.norm(task[:3,2])
                distance=float(np.linalg.norm(task[:3,3]-eye));angle=float(np.rad2deg(np.arccos(np.clip(actual@forward,-1,1))))
                row.update(declared_eye_task_m=eye.tolist(),actual_eye_error_m=distance,actual_view_axis_error_deg=angle)
                if distance>.005 or angle>1.:raise ValueError('Actual head camera differs from declared task view')
        except Exception as exc:
            row['calibration_error']=type(exc).__name__+': '+str(exc);errors.append(name+': '+row['calibration_error'])
        views[name]=row
    strict_gray=all(v['near_uniform_gray']for v in views.values())
    pair_mae=[float(np.abs(centered[i]-centered[j]).mean())for i,j in ((0,1),(0,2),(1,2))]
    # Observed failure: all three distinct cameras returned the same softly
    # shaded wall, just above the original flat-gray threshold. Require both
    # low content and cross-view similarity; one occluded camera is allowed.
    # Scope the new guard to this session's assigned engineering tasks.
    low_content=(scene.spec.get('id')in {f'E{i:02}'for i in range(26,38)}
        and all(v['smooth_low_content_gray']for v in views.values())and max(pair_mae)<6)
    if strict_gray or low_content:errors.append('All three native views are near-uniform gray; task visibility not established')
    return dict(schema='engineering-camera-admission-v1',views=views,errors=errors,
                cross_view_centered_mae=pair_mae,low_content_gray_set=low_content,
                admission_passed=not errors,physics_changed=False,
                visual_acceptance='requires_content_review'if not errors else'blocked_camera_evidence')
