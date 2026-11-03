"""Opt-in payload-contact command braking; no object/joint state writes."""
import math


def parameters(control):
    enabled=control.get('public_gripper_payload_contact_hold',False)
    if type(enabled)is not bool:raise ValueError('Payload contact hold must be boolean')
    if not enabled:return None
    if 'public_gripper_reference_speed_m_s'not in control:raise ValueError('Contact braking requires rolling gripper reference')
    preload=control.get('public_gripper_payload_preload_m',.00005)
    if type(preload)not in(int,float)or not math.isfinite(preload)or not 0<=preload<=.0002:raise ValueError('Finite bounded gripper preload required')
    return float(preload)


def brake(reference,proposed,velocity,actual_q,forces,anchor,active,closing,preload,xp):
    """Each finger brakes on its own real payload contact; release clears it."""
    # Stop-on-contact is latched until explicit RELEASE. Missing warm-cache
    # contact samples after a native restore must not create another preload.
    contacts=((active>0)|((forces>.02)&(actual_q>.001)))&closing
    anchor=xp.where(contacts&(active<=0),reference,anchor)
    both=contacts.all(axis=-1,keepdims=True) if xp.__name__=='numpy' else contacts.all(dim=-1,keepdim=True)
    stop=xp.maximum(anchor-preload*both,xp.zeros_like(anchor))
    held=xp.maximum(proposed,stop)
    bounded=xp.where(contacts,held,proposed)
    velocity=xp.where(contacts&(proposed<=stop),xp.zeros_like(velocity),velocity)
    return bounded,velocity,anchor,contacts


def surface_contact_force(buffers,xp,tolerance_m=.000002):
    """Ignore positive-gap speculative contacts; valid native manifold only."""
    force,point,normal,separation,counts,starts=buffers
    count=int(counts.reshape(-1)[0]);start=int(starts.reshape(-1)[0])
    if count<=0:return 0.
    f=force.reshape(-1);sep=separation.reshape(-1)
    if start<0 or start+count>len(f):raise ValueError('Actual contact buffer overflow')
    f=f[start:start+count];sep=sep[start:start+count]
    return xp.where(sep<=tolerance_m,xp.abs(f),xp.zeros_like(f)).sum()


def payload_forces(controller,side,reference,xp):
    """Only movable rigid payloads with actual surface contact; no goal data."""
    forces=xp.zeros_like(reference)
    if float(controller.grips[side])>=.001:return forces
    cache=getattr(controller,'_public_gripper_payload_contact_views',None)
    if cache is None:controller._public_gripper_payload_contact_views={};cache=controller._public_gripper_payload_contact_views
    for name,asset in controller.scene.objects.items():
        spawn=getattr(getattr(asset,'cfg',None),'spawn',None)
        rigid=getattr(spawn,'rigid_props',None)
        if getattr(rigid,'kinematic_enabled',False)is True:continue
        entry=controller.scene.contacts.get(name)
        if entry is None:continue
        sensor,labels=entry
        for i,finger in enumerate(controller.scene.embodiment.fingers):
            if f'{side}_finger{i+1}'not in labels:continue
            key=(name,side,finger)
            if key not in cache:
                root=controller.scene.root_path
                view=sensor._physics_sim_view.create_rigid_contact_view(
                    f'{root}/Props/{name}',filter_patterns=[f'{root}/{side}_robot/{finger}'],max_contact_data_count=256)
                if view.sensor_count!=1 or view.filter_count!=1:raise ValueError('Exact payload/finger contact pair required')
                cache[key]=view
            value=surface_contact_force(cache[key].get_contact_data(controller.dt),xp)
            if hasattr(value,'to'):value=value.to(reference)
            forces[:,i]+=value
    return forces
