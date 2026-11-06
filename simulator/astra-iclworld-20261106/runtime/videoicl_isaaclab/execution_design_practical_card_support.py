"""Opt-in visible passive pickup supports for the practical card revision."""
SCHEMA='practical-card-passive-pickup-supports-v1'


def configure_spec(spec):
    if spec['id']not in('E47','E48','E49','E50'):raise ValueError('Practical card support task scope')
    if spec['semantic'].get('engineering_pickup_supports'):raise ValueError('Fresh support layout required')
    cards=spec['semantic']['groups']['cards'];objects={o['id']:o for o in spec['objects']};records={}
    for index,name in enumerate(cards):
        obj=objects[name]
        if obj.get('engineering_practical_card',{}).get('approximate_thickness_m')!=.001:
            raise ValueError('Explicit practical1mm card required')
        if spec['id']=='E50':obj['xy']=[-.075,.1]
        top=.81 if spec['id']=='E50'else .84-.01*index
        if top<=.800001:continue
        fixture='fixture'+str(len(spec['fixtures']));height=top-.8
        spec['fixtures'].append(dict(type='box',size=[.0075,.0075,height/2],
            xy=list(obj['xy']),z=.8+height/2,rgba=[.42,.44,.47,1.],literal_rgba=True,
            passive=True,source_fixture=SCHEMA))
        obj['bottom']=top;obj['center_z']=top+.0005
        obj['engineering_practical_card']['pickup_support']=dict(fixture=fixture,top_z=top,
            source_initial_layout_changed=True,passive=True)
        records[name]=dict(fixture=fixture,xy=list(obj['xy']),top_z=top)
    spec['semantic']['engineering_pickup_supports']=dict(schema=SCHEMA,cards=records,
        approximation=True,visible_passive_fixtures=True,rule_and_face_order_unchanged=True,
        full_native_functional_validation='pending')
    return records
