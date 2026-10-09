"""Tool/contact tasks with real rigid contents and private process evidence."""
RECIPES = {"F36": "push_delivery", "F37": "hook_retrieval", "F40": "pour_solids"}


def build(recipe, v, rng, obj, position):
    if recipe == "push_delivery": return push_delivery(v, rng, obj, position)
    if recipe == "hook_retrieval": return hook_retrieval(v, rng, obj, position)
    if recipe != "pour_solids": raise NotImplementedError(recipe)
    return pour_solids(v, rng, obj, position)


def pour_solids(v, rng, obj, position):
    objects, goals, plan, zones, fixtures = [], [], [], [], []
    start = [-.18, 0.]
    x, y, z, w = .038, .038, .055, .004
    components = [dict(size=[x, y, w], pos=[0., 0., -z+w]),
                  dict(size=[w, y, z], pos=[-x+w, 0., 0.]), dict(size=[w, y, z], pos=[x-w, 0., 0.]),
                  dict(size=[x, w, z], pos=[0., -y+w, 0.]), dict(size=[x, w, z], pos=[0., y-w, 0.]),
                  dict(size=[.013, .018, .013], pos=[0., -.052, .012]),
                  dict(size=[.013, .018, .013], pos=[0., .052, .012])]
    cup = obj("cup", start, "white", "cup", (x, .070, z), bottom=.8,
              components=components, grasp_local=[0., -.052, .012], cavity_size=[x, y, z], friction=[3, .1, .01],
              grasp_sides=[[0., -.052, .012], [0., .052, .012]])
    cup["rgba"][3] = .35
    objects.append(cup)
    for i in range(3):
        xy = [.17, -.22+i*.22]
        parts = [dict(size=[.09, .09, .008], pos=[0., 0., -.017]),
                 dict(size=[.004, .09, .025], pos=[-.086, 0., 0.]),
                 dict(size=[.004, .09, .025], pos=[.086, 0., 0.]),
                 dict(size=[.09, .004, .025], pos=[0., -.086, 0.]),
                 dict(size=[.09, .004, .025], pos=[0., .086, 0.])]
        objects.append(obj(f"bin{i}", xy, "white", "tray", (.09, .09, .025),
                           components=parts, density=700, solref=[.004, 1]))
    for i in range(6):
        name = f"wood{i}"
        xy = [start[0]-.010+(i % 2)*.020, start[1]-.019+(i//2)*.019]
        objects.append(obj(name, xy, ["red", "green", "blue"][i//2], size=(.009, .009, .009), bottom=.808))
        goals += [dict(type="nest", object=name, target=f"bin{v}"),
                  dict(type="poured", object=name, target="cup")]
    plan.append(dict(object="cup", operation="pour", xy=[.17, -.22+v*.22], bottom=.8,
                     return_xy=start, contents=[f"wood{i}" for i in range(6)]))
    return objects, goals, plan, zones, fixtures


def push_delivery(v, rng, obj, position):
    objects, goals, plan, zones, fixtures = [], [], [], [], []
    parts = [dict(size=[.12, .014, .014], pos=[0., 0., -.061], friction=[.3, .005, .0001], priority=1),
             dict(size=[.025, .014, .055], pos=[0., 0., -.005])]
    objects.append(obj("pusher", [-.22, 0.], "yellow", "bar", (.12, .014, .075),
                       components=parts, grasp_local=[0., 0., .035], density=180, friction=[1.5, .006, .0001], condim=4))
    for i, color in enumerate(["red", "green", "blue"]):
        y = -.22+i*.22
        objects.append(obj(color, [-.035, y], color, size=(.022, .022, .022)))
        for sign in [-1, 1]:
            fixtures.append(dict(type="box", xy=[.025, y+sign*.040], z=.817,
                                 size=[.11, .006, .017], rgba=[.4, .45, .5, 1]))
        zones.append(dict(id=f"exit{i}", xy=[.20, y], half_size=[.04, .04], marker=i))
    order = ["red", "green", "blue"][v:]+["red", "green", "blue"][:v]
    for slot, name in enumerate(order):
        start = next(o["xy"] for o in objects if o["id"] == name)
        delivery = [.20, -.22+slot*.22]
        goals += [dict(type="pushed", object=name, target="pusher", distance=.10), position(name, delivery)]
        plan.append(dict(object="pusher", operation="push", block=name, start_xy=list(start),
                         xy=delivery, bottom=.8, return_xy=[-.22, 0.]))
    return objects, goals, plan, zones, fixtures


def hook_retrieval(v, rng, obj, position):
    objects, goals, plan, fixtures = [], [], [], []
    zones = [dict(id="delivery", xy=[-.18, -.24], half_size=[.075, .075], marker=0)]
    parts = [dict(size=[.12, .010, .010], pos=[0., 0., -.025]),
             dict(size=[.010, .010, .025], pos=[.10, 0., -.050]),
             dict(size=[.010, .010, .025], pos=[-.09, 0., -.005]),
             dict(size=[.025, .014, .030], pos=[-.09, 0., .030])]
    objects.append(obj("hook", [-.20, 0.], "yellow", "bar", (.12, .025, .075), components=parts,
                       bottom=.8, grasp_local=[-.09, 0., .045], density=80,
                       friction=[1.5, .006, .0001], condim=4))
    fixtures.append(dict(type="box", xy=[-.29, 0.], z=.82, size=[.03, .025, .02], rgba=[.4, .45, .5, 1]))
    # A transparent document stand keeps the tool tip visible while blocking
    # the robot palm. The clearance is deliberately generous for the hook.
    fixtures.append(dict(type="box", xy=[.17, 0.], z=.925, size=[.12, .34, .015], rgba=[.65, .8, .9, .18]))
    for x in [.05, .29]:
        for y in [-.34, .34]:
            fixtures.append(dict(type="box", xy=[x, y], z=.855, size=[.01, .01, .055], rgba=[.4, .45, .5, 1]))
    colors = ["red", "green", "blue"]; rng.shuffle(colors)
    for i, (outer, inner) in enumerate([(.042, .025), (.050, .030), (.058, .035)]):
        objects.append(obj(f"ring{i}", [.15, -.22+i*.22], colors[i], "ring", (outer, outer, .014),
                           inner_radius=inner, density=350, condim=4, friction=[1.5, .006, .0001]))
        goals.append(dict(type="place" if i == v else "not_place", object=f"ring{i}", target="delivery"))
    goals.append(dict(type="hooked", object=f"ring{v}", target="hook", distance=.10))
    plan.append(dict(object="hook", operation="hook", block=f"ring{v}",
                     start_xy=[.15, -.22+v*.22], xy=[-.18, -.24], bottom=.8, return_xy=[-.20, 0.]))
    return objects, goals, plan, zones, fixtures
