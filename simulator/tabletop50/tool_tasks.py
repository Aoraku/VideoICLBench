"""Tool/contact tasks with real rigid contents and private process evidence."""
RECIPES = {"F36": "push_delivery", "F37": "hook_retrieval", "F38": "shovel_delivery", "F39": "sweep_beads", "F41": "corner_push",
           "F40": "pour_solids", "F45": "pass_long_bar"}


def build(recipe, v, rng, obj, position):
    if recipe == "push_delivery": return push_delivery(v, rng, obj, position)
    if recipe == "hook_retrieval": return hook_retrieval(v, rng, obj, position)
    if recipe == "pass_long_bar": return pass_long_bar(v, rng, obj, position)
    if recipe == "sweep_beads": return sweep_beads(v, rng, obj, position)
    if recipe == "corner_push": return corner_push(v, rng, obj, position)
    if recipe == "shovel_delivery": return shovel_delivery(v, rng, obj, position)
    if recipe != "pour_solids": raise NotImplementedError(recipe)
    return pour_solids(v, rng, obj, position)


def shovel_delivery(v, rng, obj, position):
    # An ordinary broad scoop and wooden coasters with two low feet provide
    # visible clearance for the lip. No contact attachment or weld is used.
    parts = [dict(size=[.080, .022, .002], pos=[.06, 0., -.073], friction=[.35, .005, .0001], priority=1),
             dict(size=[.015, .018, .055], pos=[0., 0., -.005])]
    objects = [obj("scoop", [-.25, 0.], "yellow", "bar", (.14, .022, .075),
                   components=parts, bottom=.8, grasp_local=[0., 0., .035], density=150,
                   friction=[1.5, .006, .0001], condim=4)]
    slots = [[.23, -.25], [.23, 0.], [.23, .25]]; rng.shuffle(slots)
    zones = [dict(id=f"plate{i}", xy=xy, half_size=[.14, .09], marker=i) for i, xy in enumerate(slots)]
    goals, plan = [], []
    for i, color in enumerate(["red", "green", "blue"]):
        width = .027+i*.002
        pieces = [dict(size=[width, .035, .009], pos=[0., 0., .011])]
        pieces += [dict(size=[width-.004, .004, .011], pos=[0., y, -.009]) for y in [-.031, .031]]
        name = f"coaster{i}"
        objects.append(obj(name, [.02, -.12+i*.12], color, "bar", (width, .035, .020),
                           components=pieces, bottom=.8, density=180, condim=4))
        goals += [dict(type="place", object=name, target=f"plate{v}"),
                  dict(type="scooped", object=name, target="scoop")]
        xy = [slots[v][0]+(i-1)*.075, slots[v][1]]
        plan.append(dict(object="scoop", operation="shovel", block=name, xy=xy, return_xy=[-.25, 0.]))
    return objects, goals, plan, zones, []


def corner_push(v, rng, obj, position):
    parts = [dict(size=[.018, .035, .018], pos=[0., 0., -.057], friction=[.3, .005, .0001], priority=1),
             dict(size=[.014, .018, .055], pos=[0., 0., -.005])]
    objects = [obj("paddle", [-.22, .22], "yellow", "bar", (.018, .035, .075),
                   components=parts, bottom=.8, grasp_local=[0., 0., .035], density=180,
                   friction=[1.5, .006, .0001], condim=4),
               obj("slider", [-.14, 0.], "blue", size=(.025, .025, .020))]
    slots = [[.23, -.20], [.23, 0.], [.23, .20]]; rng.shuffle(slots)
    zones = [dict(id=f"exit{i}", xy=xy, half_size=[.055, .055], marker=i) for i, xy in enumerate(slots)]
    # The solid barrier is shared by every rule. There is no prescribed route:
    # either end is a valid way around it, provided the real tool moves the piece.
    fixtures = [dict(type="box", xy=[.035, 0.], z=.83, size=[.018, .080, .03], rgba=[.4, .45, .5, 1])]
    goals = [dict(type="place", object="slider", target=f"exit{v}"),
             dict(type="swept", object="slider", target="paddle", distance=.10)]
    side = .15
    plan = [dict(object="paddle", operation="corner_push", block="slider", xy=slots[v],
                 waypoints=[[-.14, side], [.23, side], slots[v]], return_xy=[-.22, .22])]
    return objects, goals, plan, zones, fixtures


def sweep_beads(v, rng, obj, position):
    parts = [dict(size=[.012, .10, .018], pos=[0., 0., -.057], friction=[.3, .005, .0001], priority=1),
             dict(size=[.014, .025, .055], pos=[0., 0., -.005])]
    objects = [obj("brush", [-.20, 0.], "yellow", "bar", (.014, .10, .075),
                   components=parts, bottom=.8, grasp_local=[0., 0., .035], density=150,
                   friction=[1.5, .006, .0001], condim=4)]
    slots = [[.22, -.22], [.22, 0.], [.22, .22]]; rng.shuffle(slots)
    zones = [dict(id=f"collect{i}", xy=xy, half_size=[.09, .09], marker=i) for i, xy in enumerate(slots)]
    goals = []
    palette = ["red", "green", "blue"]*2; rng.shuffle(palette)
    for i in range(6):
        name = f"bead{i}"; radius = rng.uniform(.017, .019)
        xy = [-.08+(i//2)*.05, -.026+(i%2)*.052]
        objects.append(obj(name, xy, palette[i], "sphere", (radius, radius, radius), bottom=.8))
        goals += [dict(type="place", object=name, target=f"collect{v}"),
                  dict(type="swept", object=name, target="brush", distance=.10)]
    fixtures = [dict(type="box", xy=[x, 0.], z=.815, size=[.006, .34, .015], rgba=[.4, .45, .5, 1])
                for x in [-.28, .35]]
    fixtures += [dict(type="box", xy=[.035, y], z=.815, size=[.315, .006, .015], rgba=[.4, .45, .5, 1])
                 for y in [-.34, .34]]
    plan = [dict(object="brush", operation="sweep", xy=slots[v], bottom=.8,
                 return_xy=[-.20, 0.], contents=[f"bead{i}" for i in range(6)])]
    return objects, goals, plan, zones, fixtures


def pass_long_bar(v, rng, obj, position):
    import math
    parts = [dict(size=[.15, .024, .014], pos=[0., 0., -.061]),
             dict(size=[.025, .014, .055], pos=[0., 0., -.005])]
    bar = obj("long_bar", [-.16, 0.], "yellow", "arrow_bar", (.15, .024, .075),
              components=parts, bottom=.8, grasp_local=[0., 0., .035], density=100,
              condim=4, friction=[1.5, .006, .0001], arrow_z=-.047)
    bar["yaw"] = math.pi/2
    fixtures = [dict(type="box", xy=[.12, sign*.142], z=.99,
                     size=[.012, .012, .19], rgba=[.4, .45, .5, 1]) for sign in [-1, 1]]
    fixtures.append(dict(type="box", xy=[.12, 0.], z=1.192,
                         size=[.012, .154, .012], rgba=[.4, .45, .5, 1]))
    heading = [0., math.pi/2, -math.pi/2][v]
    goals = [dict(type="passed_gate", object="long_bar", apertures=[[.12, 0., .99]],
                  half_opening=[.13, .19], half_depth=.012),
             position("long_bar", [.30, 0.]),
             dict(type="yaw", object="long_bar", value=heading, tolerance=.13)]
    plan = [dict(object="long_bar", operation="pass_gate", xy=[.30, 0.], bottom=.8,
                 approach=[-.20, 0., .90], yaw=heading)]
    zones = [dict(id="delivery", xy=[.30, 0.], half_size=[.08, .20], marker=0)]
    return [bar], goals, plan, zones, fixtures


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
    fixtures.append(dict(type="box", xy=[-.29, -.05], z=.82, size=[.03, .075, .02], rgba=[.4, .45, .5, 1]))
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
                     start_xy=[.15, -.22+v*.22], xy=[-.18, -.24], bottom=.8, return_xy=[-.20, -.10]))
    return objects, goals, plan, zones, fixtures
