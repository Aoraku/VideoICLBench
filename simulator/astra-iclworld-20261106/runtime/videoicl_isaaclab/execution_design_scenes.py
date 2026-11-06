"""Opt-in physical scenes for the execution-design revision.

Only reset-time geometry is authored here. No transport, snapping, or scripted
completion occurs during execution. Native acceptance remains mandatory.
"""
from copy import deepcopy
import math
import random
from .task_recipes import box, prop, vessel, qaxis, cylinder

TASKS = ('E01', 'E09', 'E17', 'E20', 'E39')
REVISION = 'execution-design-v2'


def build_execution_scene(base_spec, *, condition='I', seed=None, revision=None,
                          e09_operable_packaging=False):
    s = deepcopy(base_spec)
    task = s['id']
    if type(e09_operable_packaging) is not bool or (e09_operable_packaging and task!='E09'):
        raise ValueError('Operable packaging requires explicit E09-only boolean opt-in')
    if task not in TASKS or condition not in ('I', 'E'):
        raise ValueError('Long workflows support only I/E and the five declared tasks')
    seed = s['seed'] if seed is None else seed
    if type(seed) is not int or seed < 0:
        raise ValueError('Nonnegative integer seed required')
    rng = random.Random(seed)
    objects = {o['id']: o for o in s['objects']}
    sem = s['semantic']
    s['goals'] = []  # Old author target trajectories are not whole-workflow demonstrations.
    s['zones'] = []
    s['fixtures'] = []
    s['joints'] = []
    destination = seed % 2
    d = dict(schema=REVISION, revision=REVISION, condition=condition,
             paired_input_id=f'{task}-{s["variant"]}-{seed}', seed=seed,
             destination_zone=f'delivery_{destination}', delivery_support_actor='table',
             packages=[], local_regions=[], cleanup_regions=[], target_members=[],
             unused_members=[], reference_objects=[], initial_preserved={},
             stability=dict(seconds=.5, translation_envelope_m=.002, rotation_matrix_envelope=.02),
             native_acceptance_required=True, batch_id=1 + seed % 3,
             environment_changes=['table_material', 'station_translation', 'packaging_appearance'] if condition=='E' else [])
    s['execution_design'] = d
    if condition=='E':
        s['table_surface']=dict(color=[.32,.43,.48],roughness=.8,static_friction=.65,dynamic_friction=.5,restitution=0.)
    # I changes which delivery station is requested and the batch object layout;
    # E preserves that same input and moves the whole workspace coherently.
    shift = [.035, -.025] if condition == 'E' else [0., 0.]
    rgba = [.52,.66,.73,1.] if condition=='E' else [.82,.83,.78,1.]

    def add(o):
        if o['id'] in objects:
            raise ValueError('Duplicate execution asset '+o['id'])
        objects[o['id']] = o
        return o

    def tray(name, xy, size, *, bottom=.805):
        return add(vessel(name,xy,rgba,hx=size[0],hy=size[1],hz=size[2],bottom=bottom))

    def region(name, actor, lower, upper, members=None, **kw):
        return dict(id=name,actor=actor,lower=lower,upper=upper,
                    **({'members':list(members)} if members is not None else {}),**kw)

    def bounds(o):
        hx,hy,hz=o['size'];return [-hx+.008,-hy+.008,-hz+.006],[hx-.008,hy-.008,hz]

    def package(name, xy, size, members, *, hinge=False, bottom=.805):
        o=tray(name,xy,size,bottom=bottom);hx,hy,hz=size
        if task in ('E09','E39'):o['opacity']=.15
        lid=prop(name+'_lid','box',[hx,hy,.003],[xy[0],xy[1]+2*hy+.035],rgba,
                 bottom=.805,mass=.06,physical_mass_kg=.06)
        if hinge:
            opening=math.radians(100)
            lid.update(xy=[xy[0],xy[1]-hy+hy*math.cos(opening)],
                       center_z=o['bottom']+2*hz+.003+hy*math.sin(opening),
                       quaternion=qaxis(0,opening))
            s['joints'].append(dict(type='revolute',parent=name,child=lid['id'],axis='X',
                anchor0=[0,-hy,hz+.003],anchor1=[0,-hy,0],limits=[0,100]))
        lid['opacity']=.15
        add(lid)
        lo,hi=bounds(o)
        d['packages'].append(dict(container=name,lid=lid['id'],members=list(members),
            lower=lo,upper=hi,lid_local_center=[0,0,hz+.003],
            lid_position_tolerance=.008,lid_orientation_tolerance=.12,
            hinge_joint_index=len(s['joints'])-1 if hinge else None))
        return o

    def pose_object(name, xy, bottom=.806):
        o=objects[name]
        offset=o['center_z']-o.get('bottom',.802) if 'center_z' in o else None
        o.update(xy=list(xy),bottom=bottom)
        if offset is not None:o['center_z']=bottom+offset
        return o

    if task=='E01':
        # Keep reviewed food and tray geometry; the box holds the same tray.
        d['storage_lift']={'meal_box':dict(support_top_z=1.008,clearance_m=.015)}
        pose_object('tray',[-.05,0],.811);package('meal_box',[.10,0],[.128,.178,.09],['tray'],hinge=True,bottom=1.011)
        selected=list(sem['selected']);foods=list(sem['groups']['foods'])
        for i,name in enumerate(foods):pose_object(name,[(-.30,-.21,-.125)[i],-.24])
        c=sem['containers']['plate']
        d['local_regions']=[region('meal','tray',c['lower'],[c['upper'][0],c['upper'][1],.18],selected)]
        d.update(delivery_actor='meal_box',local_support_actor='tray',target_members=selected,
                 unused_members=list(sem['unselected']))
    elif task=='E09':
        groups=sem['expected_groups'];pieces=list(sem['groups']['pieces'])
        # The real open gripper spans 80 mm plus finger thickness. Native
        # action 124 hit the adjacent triangle on the former 65-mm grid.
        # Keep source identities/geometry unchanged and provide physical
        # finger clearance between independent supply rails.
        for i,name in enumerate(pieces):pose_object(name,[-.28+(i%3)*.10,-.30+(i//3)*.10])
        boxes=[]
        for i in range(3):
            name='group_box'+str(i);o=package(name,[-.20+i*.15,.10],[.063,.055,.022],[])
            boxes.append(name);lo,hi=bounds(o)
            d['local_regions'].append(region(name,name,lo,hi,candidates=pieces))
        d['unordered_expected_groups']=deepcopy(groups)
        # Three small boxes fit side-by-side on the long axis of the crate.
        crate=tray('shipping_crate',[.22,-.16],[.09,.20,.055])
        lo,hi=bounds(crate)
        d['packages'].append(dict(container='shipping_crate',members=boxes,lower=lo,upper=hi))
        d.update(delivery_actor='shipping_crate',target_members=pieces)
    elif task=='E17':
        stand=objects['stand'];stand['role']='movable';stand['mass']=.45;stand['dynamic_mechanical_asset']=True
        from .execution_design import REVISION as current_revision, REVISION_V3
        if (revision or current_revision)==REVISION_V3:
            from .execution_design_e17_stand import descriptor,LIFT_M,MASS_KG
            stand['e17_stand_geometry']=descriptor()
            stand['mass']=MASS_KG
            stand['size'][2]+=LIFT_M/2
            stand['local_bounds_center'][2]+=LIFT_M/2
            sem['shelves']['upper']['center_local'][2]+=LIFT_M
            d['physical_asset_revision']=stand['e17_stand_geometry']
        pose_object('stand',[.04,.05])
        # Source collision mesh: lower rim z <= .016796, upper plate starts
        # at .132994, outer plate x <= .104992. The native reference must
        # still establish robot/palm clearance and successful contacts.
        d['shelf_insertion']={'lower':dict(entry_abs_x=.15,carry_bottom_z=.025,retreat_lift_m=.025)}
        pieces=list(sem['groups']['pieces'])
        for i,name in enumerate(pieces):pose_object(name,[-.24+(i%2)*.07,-.17+(i//2)*.07])
        for layer,shelf in sem['shelves'].items():
            c=shelf['center_local'];h=shelf['half_size']
            d['local_regions'].append(region(layer,'stand',[c[0]-h[0],c[1]-h[1],c[2]-.002],
                 [c[0]+h[0],c[1]+h[1],c[2]+.06],
                 [k for k,v in sem['required_layers'].items() if v==layer]))
        packing=tray('packing_box',[-.20,-.12],[.09,.17,.018])
        # Integral low cradles leave a real finger gap below the six-mm
        # teaching pieces. They travel with the box; no source item is welded.
        # Actual open-finger mesh spans about 127mm in X. One column
        # avoids both the old side-wall collision and neighboring pieces.
        for y in (-.12,-.04,.04,.12):
            packing['collision_shapes'].append(box([.003,.014,.006],[0,y,-.006]))
        # Props start inside real packaging, not magically unpacked at runtime.
        for i,name in enumerate(pieces):pose_object(name,[-.20,-.24+i*.08],.823)
        # A real raised pinch tab keeps the fingertips above the closed box
        # rim. The former thin-lid centre grasp pushed the whole box over in
        # native testing; this remains an unaccepted fresh-engineering design.
        add(prop('packing_lid','box',[.09,.17,.021],[-.20,-.12],rgba,bottom=.841,
                 center_z=.844,local_bounds_center=[0,0,.018],
                 parts=[box([.09,.17,.003]),box([.010,.022,.018],[0,0,.021])]))
        recycle=tray('recycle_box',[-.18,.32],[.11,.20,.045]);lo,hi=bounds(recycle)
        d['cleanup_regions']=[region('recycling','recycle_box',lo,hi,['packing_box','packing_lid'])]
        d.update(delivery_actor='stand',local_support_actor='stand',target_members=pieces)
    elif task=='E20':
        # One portable rigid tray, three real wells; no world-fixed painted bins.
        t=tray('compartment_tray',[0,.10],[.195,.065,.018])
        for x in (-.065,.065):t['collision_shapes'].append(box([.003,.057,.018],[x,0,0]))
        colors=('yellow','red','blue');centers=(-.13,0,.13)
        chips=list(sem['groups']['chips']);initial=[]
        for i,color in enumerate(colors):
            ids=[k for k in chips if k.startswith(color+'_')]
            n=rng.randrange(0,3)  # Shared 0..2 support for every private A/B/C target.
            rng.shuffle(ids)
            preserved=ids[:n];initial.extend(preserved)
            for j,name in enumerate(ids):
                if j<n:pose_object(name,[centers[i]+(j%2-.5)*.038,.10+(j//2-.5)*.038],.813)
                else:pose_object(name,[-.23+(j%5)*.046,-.14-i*.05])
            rid=sem['mapping'][color];d['initial_preserved'][rid]=preserved
            d['local_regions'].append(region(rid,'compartment_tray',[centers[i]-.057,-.057,-.012],
                 [centers[i]+.057,.057,.05],candidates=chips,count=sem['target_total'],required_color=color))
            # Marker moves physically with tray through attached visual shapes.
            ink=[.05,.05,.05,1.]
            if i==0:mark=cylinder(.010,.0005,[centers[i],0,-.010],rgba=ink)
            elif i==1:mark=box([.010,.010,.0005],[centers[i],0,-.010],rgba=ink)
            else:
                mark=dict(type='mesh',size=[.01,.01,.001],pos=[centers[i],0,-.010],quat=[1,0,0,0],rgba=ink,literal_rgba=True,
                    mesh_data=dict(vertices=[-.012,-.008,0,.012,-.008,0,0,.012,0],faces=[0,1,2]))
            t.setdefault('visual_shapes',[]).append(mark)
        # A real raised pinch tab leaves room for a public full-opening
        # gripper without placing its lower finger through the support table.
        lid=add(prop('compartment_lid','box',[.195,.065,.021],[0,.26],rgba,bottom=.805,
                     center_z=.808,local_bounds_center=[0,0,.018],opacity=.15,
                     parts=[box([.195,.065,.003]),box([.010,.022,.018],[0,0,.021])]))
        lo,hi=bounds(t)
        d['packages']=[dict(container=t['id'],lid=lid['id'],members=[],lower=lo,upper=hi,
                            lid_local_center=[0,0,.021],lid_position_tolerance=.008,lid_orientation_tolerance=.12)]
        d.update(delivery_actor=t['id'],local_support_actor=t['id'],target_members=chips,
                 unused_supply_bounds=dict(lower=[-.28,-.30,.80],upper=[.03,-.08,1.05]))
    else:  # E39: movable slotted work tray, separately identified reference.
        active=list(sem['groups']['active']);refs=list(sem['groups']['reference'])
        from .execution_design import REVISION as current_revision, REVISION_V3
        reset_x=-.025 if (revision or current_revision)==REVISION_V3 else 0.
        work_x,ref_x,box_x=-.12+reset_x,.015+reset_x,.17+reset_x
        d['e39_engineering_reset_translation_x_m']=reset_x
        work=tray('work_tray',[work_x,0],[.065,.185,.018])
        for y in (-.12,0,.12):
            work['collision_shapes'].append(box([.004,.015,.009],[0,y,-.003]))
        # Actual-native IK screening found the previous far-side box seat
        # beyond bounded solutions. Shift only reset-time reference/package
        # 60mm nearer, preserving identities, dimensions and source rules.
        ref=tray('reference_tray',[ref_x,0],[.065,.185,.018]);ref['role']='fixture'
        for t in (work,ref):
            for y in (-.06,.06):t['collision_shapes'].append(box([.057,.003,.018],[0,y,0]))
        initial_order=list(active);rng.shuffle(initial_order)
        for i,name in enumerate(initial_order):
            pose_object(name,[work_x,.12-i*.12],.829)['yaw']=rng.choice([0.,math.pi/2,math.pi])
        for i,name in enumerate(refs):pose_object(name,[ref_x,.12-i*.12],.813)
        package('protective_box',[box_x,.05],[.077,.197,.036],['work_tray'],hinge=True)
        expected=sorted(active,key=lambda n:sem['targets'][n]['xy'][1],reverse=True)
        d['local_order']=dict(actor='work_tray',axis=1,descending=True,pieces=active,
            expected_order=expected if sem['match_order'] else initial_order,
            reference_pieces=refs,reference_by_object=deepcopy(sem['reference_by_object']),
            match_order=sem['match_order'],match_orientation=sem['match_orientation'],
            expected_yaws={n:sem['targets'][n]['yaw'] if sem['match_orientation'] else objects[n]['yaw'] for n in active})
        d.update(delivery_actor='protective_box',local_support_actor='work_tray',target_members=active,
                 reference_objects=refs+['reference_tray'])

    # Two visibly distinct marked receiving stations and a public order card.
    # The selected station is an input, not an ABC rule hint.
    station_y=.39 if task=='E01' else .35
    delivered=objects[d['delivery_actor']]
    station_half=[delivered['size'][0]+.010,delivered['size'][1]+.007]
    station_centers=([.05,station_y],[.05,-station_y])
    if task=='E39':
        # Keep both receiving footprints clear of the fixed supply shelf and
        # temporary T cradles. The former (-.22,-.30) station intersected
        # fixture0 and the right cradle, blocking a genuine table placement.
        # Order identities, dimensions and table-height scoring stay fixed.
        station_centers=([.225,.30],[.225,-.30])
    if task=='E17':station_centers=([.05,.35],[-.22,-.35])
    for i,xy in enumerate(station_centers):
        s['zones'].append(dict(id=f'delivery_{i}',xy=xy,half_size=station_half,surface_z=.8,
                              marker=i,rgba=[.92,.92,.88,1.]))
    s['zones'].append(dict(id='order_card',xy=[0,-.31],half_size=[.035,.025],surface_z=.8,
                          digit=destination+1,rgba=[.95,.95,.95,1.]))
    for i,z in enumerate(s['zones'][:2]):z['digit']=i+1
    # A visibly numbered distractor batch remains outside the requested shipment.
    exemplar='burger' if task=='E01' else next(n for n in sorted(d['target_members']) if objects[n].get('source_asset'))
    spare=deepcopy(objects[exemplar]);spare_id='other_batch_'+exemplar
    spare.update(id=spare_id,identity=spare_id)
    add(spare);pose_object(spare_id,[-.34,.23],.805)
    d['unused_members'].append(spare_id)
    d['batch_members']=dict(requested=list(d['target_members']),distractor=[spare_id])
    d['public_order']=dict(batch=d['batch_id'],destination=destination+1)
    for name,xy,digit in [('requested_batch',[-.24,-.32],d['batch_id']),
                           ('other_batch',[-.32,.29],1+d['batch_id']%3),
                           ('order_batch',[-.08,-.31],d['batch_id'])]:
        s['zones'].append(dict(id=name,xy=xy,half_size=[.025,.018],surface_z=.8,digit=digit,rgba=[.96,.96,.86,1.]))
    d['cleanup_regions'].append(region('other_batch_supply',None,[-.38,.17,.80],[-.26,.29,1.10],[spare_id]))
    # Explicit staging shelf with two physical levels. Not a spawn-time weld.
    if task=='E01':
        # The real lower shelf projects 150mm forward of the upper one.
        # A wrist can approach the lower tray rim outside the upper platform's
        # footprint; both levels still physically store separate movable items.
        shelf_centers=[[-.05,0],[.10,0]]
        for xy,height in zip(shelf_centers,(.805,1.005)):
            s['fixtures'].append(dict(type='box',size=[.14,.19,.003],xy=xy,z=height))
        for x in (-.045,.245):
            for y in (-.195,.195):
                s['fixtures'].append(dict(type='box',size=[.004,.004,.105],xy=[x,y],z=.905))
        d['initial_storage']={'tray':'fixture0','meal_box':'fixture1'}
        d['storage_extraction']={'tray':dict(approach_offset_task=[-.18,0,0],lift_m=.015,exit_offset_task=[-.15,0,0])}
        d['storage_surfaces']={name:dict(actor='fixture'+str(i),xy=list(shelf_centers[i]),half_size=[.14,.19],surface_z=z+.003) for i,(name,z) in enumerate((('rack_lower',.805),('rack_upper',1.005)))}
    else:
        # Low rigid supply shelf; objects remain separately manipulable.
        shelf_xy=[-.32,-.04]
        s['fixtures'].append(dict(type='box',size=[.04,.12,.003],xy=shelf_xy,z=.802))
    def storage_platform(label, xy, half_size, names, lift=.008):
        index=len(s['fixtures'])
        s['fixtures'].append(dict(type='box',size=list(half_size)+[.004],xy=list(xy),z=.804))
        for name in names:
            o=objects[name];pose_object(name,o['xy'],o['bottom']+lift)
        d.setdefault('initial_storage',{}).update({n:'fixture'+str(index) for n in names})
        d.setdefault('storage_surfaces',{})[label]=dict(actor='fixture'+str(index),xy=list(xy),half_size=list(half_size),surface_z=.808)
    if task=='E09':
        storage_platform('teaching_supply_rack',[-.18,-.20],[.13,.13],d['target_members'])
        # Real narrow rails support the thin source pieces while leaving X
        # finger clearance. A center peg would fall through a ring's hole.
        for name in d['target_members']:
            o=objects[name];index=len(s['fixtures'])
            s['fixtures'].append(dict(type='box',size=[.003,.024,.014],xy=list(o['xy']),z=.822))
            pose_object(name,o['xy'],.836)
            d['initial_storage'][name]='fixture'+str(index)
            d['storage_surfaces']['piece_rail_'+name]=dict(actor='fixture'+str(index),xy=list(o['xy']),half_size=[.003,.024],surface_z=.836)
    if task=='E20':
        stored=set(n for ns in d['initial_preserved'].values() for n in ns)
        spare_chips=[n for n in d['target_members'] if n not in stored]
        spare_chips.sort(key=lambda n:(objects[n]['xy'][1],objects[n]['xy'][0]))
        for i,name in enumerate(spare_chips):
            pose_object(name,[-.29+(i%5)*.09,-.12-(i//5)*.08])
        storage_platform('supply_rack',[-.10,-.20],[.23,.12],spare_chips)
        d['unused_supply_support']=d['storage_surfaces']['supply_rack']['actor']
        d['unused_supply_supports']=[d['unused_supply_support']]
        for name in spare_chips:
            o=objects[name];index=len(s['fixtures']);support='fixture'+str(index)
            s['fixtures'].append(dict(type='box',size=[.003,.012,.014],xy=list(o['xy']),z=.822))
            pose_object(name,o['xy'],.836)
            d['initial_storage'][name]=support;d['unused_supply_supports'].append(support)
            d['storage_surfaces']['chip_rail_'+name]=dict(actor=support,xy=list(o['xy']),half_size=[.003,.012],surface_z=.836)
        d['unused_supply_bounds']=dict(lower=[-.33,-.32,.80],upper=[.13,-.08,1.10])
        for z in s['zones']:
            if z['id'] in ('requested_batch','order_batch','order_card'):
                z['xy']=[.20,{'requested_batch':-.12,'order_batch':-.18,'order_card':-.25}[z['id']]]
        storage_platform('tray_storage',[0,.10],[.20,.07],['compartment_tray']+list(stored))
    if task=='E17':
        storage_platform('packing_storage',[-.20,-.12],[.095,.175],
                         ['packing_box','packing_lid']+d['target_members'])
    storage_platform('other_batch_rack',[-.34,.23],[.045,.045],[spare_id])
    d['unused_members'] = d.get('unused_members',[])
    original_unused=[n for n in d['unused_members'] if n!=spare_id]
    if original_unused:
        # Cleanup verifies actual unused props still occupy the supply area.
        d['cleanup_regions'].append(region('unused_supply',None,[-.32,-.30,.80],[.15,-.08,1.10],original_unused))
    d['staging']={}
    if task=='E01':
        d['staging']={'tray':dict(xy=[-.18,.10],surface_z=.8),'meal_box':dict(xy=[.15,.38 if destination==0 else -.38],surface_z=.8)}
    elif task=='E17':
        # Native empty-retreat hit Panda joint4's upper limit at X=.15 after
        # a successful real release. This nearer, empty table patch retains
        # 35mm X clearance from the source packing box and avoids that far
        # forward low workspace. Geometry/rules of the source pieces stay fixed.
        d['staging']={'packing_lid':dict(xy=[.015,-.36],surface_z=.8)}
    elif task=='E39':
        d['staging']={}
        for i,n in enumerate(d['target_members']):
            stage=dict(xy=[-.22+i*.12,-.25],surface_z=.826,
                       xy_by_hand={'left':[-.22+i*.12,.25],'right':[-.22+i*.12,-.25]},
                       support_by_hand={})
            # Real narrow staging cradles keep the fingers clear on release
            # and on the later regrasp; thin T pieces cannot be pinched on a
            # bare table without the fingers hitting that table first.
            for side,xy in stage['xy_by_hand'].items():
                stage['support_by_hand'][side]='fixture'+str(len(s['fixtures']))
                s['fixtures'].append(dict(type='box',size=[.004,.015,.013],xy=list(xy),z=.813))
            d['staging'][n]=stage
    for name,stage in d['staging'].items():
        stage['xy']=[stage['xy'][i]+shift[i] for i in range(2)]
        for side,xy in stage.get('xy_by_hand',{}).items():
            stage['xy_by_hand'][side]=[xy[i]+shift[i] for i in range(2)]
    for surface in d.get('storage_surfaces',{}).values():
        surface['xy']=[surface['xy'][i]+shift[i] for i in range(2)]
    for o in objects.values():
        o['xy']=[o['xy'][i]+shift[i] for i in range(2)]
    for z in s['zones']:
        z['xy']=[z['xy'][i]+shift[i] for i in range(2)]
    for f in s['fixtures']:
        f['xy']=[f['xy'][i]+shift[i] for i in range(2)]
    if 'unused_supply_bounds' in d:
        for i in range(2):
            d['unused_supply_bounds']['lower'][i]+=shift[i]
            d['unused_supply_bounds']['upper'][i]+=shift[i]
    for r in d['cleanup_regions']:
        if r['actor'] is None:
            for i in range(2):r['lower'][i]+=shift[i];r['upper'][i]+=shift[i]
    from .execution_design import build_task_contract
    contract=build_task_contract(task,s['variant'],seed,condition=condition,revision=revision)
    d.update({k:v for k,v in contract['execution_design'].items() if k not in d})
    d['revision']=contract['execution_design']['revision']
    if task=='E17' and objects['stand'].get('e17_stand_geometry'):
        from .execution_design_e17_stand import bind_environment_identity
        bind_environment_identity(d)
    s['instruction']=contract['instruction']
    s['objects']=list(objects.values());s['source_asset_only']=False
    s['head_view']=dict(eye_task=[-.45,.10,2.35],target_task=[0,.10,.83],profile='execution-design-full-workspace-v2')
    s.update(task_revision=d['revision'],release_ready=False,status='execution-design-pending-native-validation',
             demo_scope='local_rule_only',generalization_condition=condition)
    d['grasps']=deepcopy(sem.get('structural_grasps',{}))
    for o in s['objects']:
        if o.get('source_asset'):
            if o['id'] not in d['grasps']:
                d['grasps'][o['id']]=dict(local=[0,0,0],jaw_axis_local=[1,0,0])
            continue
        hx,hy,hz=o['size']
        if o['id'].endswith('_lid') or o['id']=='compartment_lid':
            d['grasps'][o['id']]=dict(local=[hx-.012,0,0],jaw_axis_local=[0,0,1])
        else:
            d['grasps'][o['id']]=dict(local=[hx-.004,0,hz-.008],jaw_axis_local=[1,0,0])
    if task=='E09':
        # The source triangle's bounding-box origin is above its area centroid.
        # Its three holes leave this central strip solid. This is a geometric
        # candidate, not a claim of validated frictional grasp stability.
        for n in d['target_members']:
            if objects[n].get('identity_attributes',{}).get('shape')=='triangle':
                d['grasps'][n]=dict(local=[0,-.017320508/3,0],jaw_axis_local=[1,0,0])
    if task=='E39':
        # This visible rigid rim tab supplies opposing 20mm-wide grasp faces.
        # The original 6mm wall grip rolled the loaded tray by 52 degrees;
        # moving that same grip upward also failed its native lift diagnostic.
        work=objects['work_tray']
        work['center_z']=work.get('center_z',work['bottom']+work['size'][2])
        work['collision_shapes'].append(box([.010,.020,.012],[-.055,0,.030]))
        work['size'][2]=.030;work['local_bounds_center']=[0,0,.012]
        d['grasps']['work_tray']=dict(local=[-.055,0,.030],jaw_axis_local=[1,0,0],hand='left')
    if task=='E20':d['grasps']['compartment_lid']=dict(local=[0,0,.025],jaw_axis_local=[1,0,0])
    if task=='E01':d['grasps']['tray']=dict(local=[-.10,0,.005],jaw_axis_local=[1,0,0],hand='left' if destination==0 else 'right')
    if task=='E01':
        # A genuine rigid grasp tab gives both fingers 20 mm of pinch width
        # below the thin box rim. It is part of the same simulated body.
        container=objects['meal_box']
        # Native mass-weighted box/lid origins put the open empty package at
        # y=-40.43mm in the box frame. The former +80mm tab made it roll about
        # the pinch axis. This candidate reduces that moment; only a fresh
        # physical grasp/transport can establish whether it works.
        container['collision_shapes'].append(box([.010,.025,.015],[-.124,-.040,.055]))
        container['size'][0]=.131
        container['local_bounds_center']=[-.003,0,0]
        d['grasps']['meal_box']=dict(local=[-.124,-.040,.055],jaw_axis_local=[1,0,0],hand='left' if destination==0 else 'right')
    if task=='E17':
        lift=objects['stand'].get('e17_stand_geometry',{}).get('upper_tier_lift_m',0.)
        d['grasps']['stand']=dict(local=[.060,0,.13971+lift],jaw_axis_local=[0,0,1])
        d['grasps']['packing_lid']=dict(local=[0,0,.025],jaw_axis_local=[1,0,0])
        for name in d['target_members']:
            d['grasps'][name]=dict(local=[0,0,0],jaw_axis_local=[1,0,0])
    # Empty packaging masses are explicit design estimates, not measured
    # source-asset properties. Conservative collision wall thickness must not
    # silently make a paper/PET container weigh as much as solid wood.
    packaging_masses={
        'meal_box':(.25,'corrugated meal carton, 256x356x180mm'),
        'meal_box_lid':(.06,'attached carton lid, 256x356mm'),
        'shipping_crate':(.55,'moulded PP carrier, 180x400x110mm'),
        'packing_box':(.09,'light carton, 180x340x36mm'),
        'packing_lid':(.05,'light carton cover, 180x340mm'),
        'recycle_box':(.36,'PP bin, 220x400x90mm'),
        'compartment_tray':(.15,'PP tray with dividers, 390x130x36mm'),
        'compartment_lid':(.04,'thin PP tray cover, 390x130mm'),
        'protective_box':(.20,'PET protective shell, 154x394x72mm'),
        'protective_box_lid':(.06,'thin PET cover, 154x394mm'),
        'work_tray':(.18,'PP slotted tray with 10g raised rim tab, 130x370x60mm envelope'),
        'reference_tray':(.17,'matching PP reference tray, 130x370x36mm'),
    }
    for i in range(3):
        packaging_masses['group_box'+str(i)]=(.05,'thin PET sorting box, 126x110x44mm')
        packaging_masses['group_box'+str(i)+'_lid']=(.02,'thin PET cover, 126x110mm')
    d['packaging_mass_estimates']={}
    for name,(mass,basis) in packaging_masses.items():
        if name in objects:
            objects[name]['physical_mass_kg']=mass
            d['packaging_mass_estimates'][name]=dict(mass_kg=mass,basis=basis,measured=False,native_load_validation='pending')
    d['initial_actor_poses']={o['id']:dict(xy=list(o['xy']),bottom=o['bottom'],yaw=o.get('yaw',0)) for o in s['objects']}
    if e09_operable_packaging:
        from .execution_design_e09_packaging import apply
        apply(s)
    return s
