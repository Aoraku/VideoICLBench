"""Bounded native warmup; actual contacts remain a restoration requirement."""


def settle_checkpoint(pool, controllers, resumed, maximum_ticks):
    selected=[(room,row)for room,row in resumed.items()
              if row['request'].get('settle_until_required_contacts')is True]
    for row in resumed.values():
        flag=row['request'].get('settle_until_required_contacts',False)
        if type(flag)is not bool:raise ValueError('Explicit boolean contact warmup flag required')
    if not selected:
        for _ in range(maximum_ticks):pool.tick()
        return None
    if len(selected)!=1 or len(resumed)!=1 or not 1<=maximum_ticks<=120:
        raise ValueError('One admitted checkpoint and bounded contact warmup required')
    room,row=selected[0];required=row['request'].get('required_contacts',[])
    if (not isinstance(required,list)or not required
            or any(not isinstance(pair,list)or len(pair)!=2
                   or any(not isinstance(name,str)or not name for name in pair)
                   or pair[0]==pair[1]for pair in required)):
        raise ValueError('Actual named required contacts needed for contact warmup')
    expected={frozenset(pair)for pair in required};controller=controllers[room]
    # Retargeting has already advanced one real tick and refreshed the native
    # contact sensors. Accept that readback if it satisfies the same gate.
    for ticks in range(maximum_ticks+1):
        _,contacts=controller.snapshot()
        if expected<=set(contacts):
            return dict(maximum_extra_ticks=maximum_ticks,actual_extra_ticks=ticks,
                        required_contacts_observed=True,contacts_fabricated=False)
        if ticks<maximum_ticks:pool.tick()
    # The unchanged restoration validator reports missing contact(s) and fails.
    return dict(maximum_extra_ticks=maximum_ticks,actual_extra_ticks=maximum_ticks,
                required_contacts_observed=False,contacts_fabricated=False)
