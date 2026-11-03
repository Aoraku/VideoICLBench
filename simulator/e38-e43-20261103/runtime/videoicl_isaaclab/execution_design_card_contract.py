"""Read-only E47-E49 source dependency plan; does not enable a new reference."""
from copy import deepcopy
from .execution_design import REVISION_V3,source_sha256


def card_reference_contract(spec):
    task=spec['id'];design=spec.get('execution_design',{})
    if task not in ('E47','E48','E49') or design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3):
        raise ValueError('Source-checked E47-E49 v3 input required')
    variant=spec['variant'];i='ABC'.index(variant)
    cards=list(spec['semantic']['groups']['cards'])
    n={'E47':2,'E48':i+1,'E49':3}[task]
    active=cards[:n];untouched=cards[n:]
    flips=[deepcopy(g)for g in spec['goals']if g['target'].endswith('_flip')]
    deliveries=[deepcopy(g)for g in spec['goals']if not g['target'].endswith('_flip')]
    if [g['object']for g in flips]!=active:raise ValueError('Flip prefix/order differs from source rule')
    objects={o['id']:o for o in spec['objects']}
    if task=='E47':
        chosen=[c for c in active if i==2 or objects[c]['face_color']==('red','black')[i]]
        if [g['object']for g in deliveries]!=chosen:raise ValueError('Wrong source colour selection')
        if any(g.get('required_support')!='box'for g in deliveries):raise ValueError('Expected actual box support')
    else:
        chosen=active
        if [g['object']for g in deliveries]!=chosen:raise ValueError('Wrong source card delivery prefix')
        if task=='E49':
            support=tuple(g.get('required_support')for g in deliveries)
            expected=(('green_plate','blue_plate','red_plate'),('green_plate','red_plate','blue_plate'),('red_plate','blue_plate','green_plate'))[i]
            if support!=expected:raise ValueError('Wrong original-position to tray mapping')
        elif any(g.get('required_support')!='holder'for g in deliveries):raise ValueError('Expected actual same-holder insertion')
    for name in active:
        practical=objects[name].get('engineering_practical_card',{})
        approximate=(practical.get('schema')=='engineering-practical-card-1mm-v1'
                     and practical.get('source_exact_geometry')is False
                     and float(objects[name]['size'][2])*2==.001)
        if float(objects[name]['size'][2])*2>.0004 and not approximate:
            raise ValueError('Original thickness or explicit practical1mm card required')
    return dict(task=task,variant=variant,flip_order=active,delivery_order=chosen,untouched=untouched,
        flip_goals=flips,delivery_goals=deliveries,
        acquisition_requires=('actual_table_support','finite_table_lower_finger_clearance','actual_bilateral_grasp'),
        flip_requires=('maintained_actual_grasp','actual_face_up_history'),
        intermediate_release_requires=('actual_support','released','stable','unselected_cards_unchanged'),
        delivery_requires=('actual_support','released','stable')+(
            ('actual_lower_card_edge_in_slot_bounds','actual_holder_contact','same_slot_identity')if task=='E48'else()),
        native_verified=False,reference_enabled=False,
        prerequisite='Independent E50 public edge acquisition must first have a reviewed native witness')
