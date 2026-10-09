"""Tool/contact tasks with real rigid contents and private process evidence."""
RECIPES = {"F36": "push_delivery", "F37": "hook_retrieval", "F38": "shovel_delivery", "F39": "sweep_beads", "F41": "corner_push",
           "F40": "pour_solids", "F42": "extend_hook", "F43": "clip_transport", "F44": "guide_ball", "F45": "pass_long_bar"}


def build(recipe, v, rng, obj, position):
    if recipe == "push_delivery": return push_delivery(v, rng, obj, position)
    if recipe == "hook_retrieval": return hook_retrieval(v, rng, obj, position)
    if recipe == "pass_long_bar": return pass_long_bar(v, rng, obj, position)
    if recipe == "sweep_beads": return sweep_beads(v, rng, obj, position)
    if recipe == "corner_push": return corner_push(v, rng, obj, position)
    if recipe == "shovel_delivery": return shovel_delivery(v, rng, obj, position)
    if recipe == "guide_ball": return guide_ball(v, rng, obj, position)
    if recipe == "clip_transport": return clip_transport(v, rng, obj, position)
    if recipe == "extend_hook": return extend_hook(v, rng, obj, position)
    if recipe != "pour_solids": raise NotImplementedError(recipe)
    return pour_solids(v, rng, obj, position)


def extend_hook(v, rng, obj, position):
    from .mechanical import annulus
    rod_parts = [dict(size=[.130, .012, .012], pos=[0., 0., -.055]),
                 dict(size=[.014, .016, .050], pos=[-.100, 0., .015]),
                 dict(size=[.090, .025, .010], pos=[-.050, 0., -.080])]
    objects = [obj("rod", [-.22, -.18], "yellow", "bar", (.13, .025, .09),
                   components=rod_parts, bottom=.8, density=150, condim=4,
                   grasp_local=[-.100, 0., .035], friction=[1.5, .006, .0001])]
    socket = []
    for yy in [-.0185, .0185]:
        socket.append(dict(size=[.045, .0075, .026], pos=[-.070, yy, -.055]))
    for zz in [-.0185, .0185]:
        socket.append(dict(size=[.045, .011, .0075], pos=[-.070, 0., -.055+zz]))
    hook_parts = socket+[dict(size=[.100, .008, .008], pos=[.070, 0., -.055]),
                         dict(size=[.008, .008, .020], pos=[.160, 0., -.065]),
                         dict(size=[.014, .016, .050], pos=[-.100, 0., .015]),
                         dict(size=[.080, .025, .010], pos=[-.040, 0., -.080])]
    # A slightly compressible, friction-lined socket retains the inserted
    # shaft through real contact. The two objects remain separate free bodies.
    objects.append(obj("hook", [-.15, .18], "white", "bar", (.17, .026, .09),
                       components=hook_parts, bottom=.8, density=150, condim=4,
                       grasp_local=[-.100, 0., .035], friction=[1.5, .006, .0001], solref=[.005, 1]))
    colors = ["red", "green", "blue"]; rng.shuffle(colors)
    for i in range(3):
        length = .025+i*.015
        pieces = annulus(.040, .025, .008)
        pieces.append(dict(size=[.010, length/2, .004], pos=[0., -.040-length/2, 0.]))
        objects.append(obj(f"ring{i}", [.27, -.20+i*.20], colors[i], "ring",
                           (.040, .040+length, .008), components=pieces, inner_radius=.025,
                           bottom=.8, density=200, condim=4, friction=[1, .005, .0001]))
    fixtures = [dict(type="box", xy=[.19, 0.], z=.900, size=[.13, .31, .008], rgba=[.6, .75, .85, .28])]
    fixtures += [dict(type="box", xy=[x, y], z=.846, size=[.012, .012, .046], rgba=[.4, .45, .5, 1])
                 for x in [.075, .305] for y in [-.325, .325]]
    zones = [dict(id="delivery", xy=[0., -.25], half_size=[.09, .14], marker=0)]
    goals = [dict(type="place", object=f"ring{v}", target="delivery"),
             dict(type="extended_hook", object=f"ring{v}", rod="rod", hook="hook"),
             position("rod", [-.22, -.18], .045), position("hook", [-.15, .18], .045)]
    goals += [dict(type="not_place", object=f"ring{i}", target="delivery") for i in range(3) if i != v]
    plan = [dict(object="rod", operation="extend_hook", hook="hook", ring=f"ring{v}",
                 xy=[0., -.25], return_xy=[-.22, -.18], hook_home=[-.15, .18])]
    return objects, goals, plan, zones, fixtures


def clip_transport(v, rng, obj, position):
    # A spring clip: squeezing the rear handles opens the front jaws. A
    # separate upright grip lets a robot carry it without opening those jaws.
    parts = [dict(size=[.090, .006, .012], pos=[.025, -.025, -.055]),
             dict(size=[.045, .006, .025], pos=[.080, -.025, -.075], friction=[3, .006, .0001]),
             dict(size=[.018, .040, .010], pos=[-.200, 0., -.090]),
             dict(size=[.075, .010, .010], pos=[-.130, -.025, -.090]),
             dict(size=[.012, .014, .060], pos=[-.200, 0., .015])]
    objects = [obj("clip", [-.16, 0.], "yellow", "spring_clip", (.220, .065, .100),
                   components=parts, bottom=.8, density=450, condim=4,
                   grasp_local=[-.200, 0., .055], friction=[1.5, .006, .0001])]
    starts = [[.04, -.18], [.04, 0.], [.04, .18]]
    rng.shuffle(starts)
    colors = ["red", "green", "blue"]; rng.shuffle(colors)
    for i in range(3):
        objects.append(obj(f"plate{i}", starts[i], colors[i], "box",
                           (.025+i*.005, .015+i*.005, .025), bottom=.8,
                           density=180, friction=[1.5, .006, .0001], condim=4))
    zones = [dict(id="rack", xy=[.22, 0.], half_size=[.09, .110], marker=0)]
    fixtures = [dict(type="box", xy=[.32, 0.], z=.815, size=[.008, .13, .015], rgba=[.4, .45, .5, 1])]
    fixtures += [dict(type="box", xy=[.22, y], z=.815, size=[.10, .008, .015], rgba=[.4, .45, .5, 1]) for y in [-.13, .13]]
    goals = [dict(type="place", object=f"plate{v}", target="rack"),
             dict(type="clipped", object=f"plate{v}", target="clip"),
             position("clip", [-.16, 0.], .045)]
    goals += [dict(type="not_place", object=f"plate{i}", target="rack") for i in range(3) if i != v]
    plan = [dict(object="clip", operation="clip_transport", plate=f"plate{v}", xy=[.22, 0.], return_xy=[-.16, 0.])]
    return objects, goals, plan, zones, fixtures


def guide_ball(v, rng, obj, position):
    import math
    slope = .15
    fixtures = [dict(type="box", xy=[0., 0.], z=.86, size=[.20, .31, .01],
                     quat=[math.cos(slope/2), 0., math.sin(slope/2), 0.], rgba=[.65, .7, .74, 1])]
    for x in [-.17, .16]:
        top = .85-math.tan(slope)*x
        for y in [-.25, .25]:
            fixtures.append(dict(type="box", xy=[x, y], z=(.8+top)/2,
                                 size=[.015, .015, (top-.8)/2], rgba=[.4, .45, .5, 1]))
    # A removable gate slides vertically between two pairs of real cheek
    # blocks, like a wooden marble-run stopper. The supports resist downhill
    # drift; lifting the gate is unconstrained and releases the ball.
    gate_surface = .87+math.tan(slope)*.10
    for x in [-.13, -.07]:
        for y in [-.090, .090]:
            fixtures.append(dict(type="box", xy=[x, y], z=gate_surface+.025,
                                 size=[.010, .018, .035], rgba=[.45, .5, .55, 1]))
    objects = [obj("ball", [-.145, 0.], "red", "sphere", (.019, .019, .019),
                   bottom=.87+math.tan(slope)*.145, density=450)]
    gate_parts = [dict(size=[.015, .090, .020], pos=[0., 0., -.060]),
                  dict(size=[.012, .015, .055], pos=[0., 0., -.005])]
    objects.append(obj("gate", [-.10, 0.], "yellow", "bar", (.015, .090, .080),
                       components=gate_parts, bottom=.87+math.tan(slope)*.10,
                       grasp_local=[0., 0., .025], density=600, condim=4,
                       friction=[1.5, .006, .0001]))
    board_parts = [dict(size=[.075, .018, .014], pos=[0., 0., -.044],
                        friction=[.06, .001, .0001], priority=1),
                   dict(size=[.012, .015, .050], pos=[0., 0., -.010])]
    # Rubber feet hold the board on the slope; its smooth vertical faces let
    # the ball slide/roll along them. A single high-friction material on both
    # surfaces can wedge a ball against an otherwise correctly placed wall.
    board_parts += [dict(size=[.008, .018, .001], pos=[x, 0., -.059],
                         friction=[1.5, .006, .0001], priority=2) for x in [-.060, .060]]
    for i, color in enumerate(["blue", "green", "purple"]):
        board = obj(f"guide{i}", [-.29, -.16+i*.16], color, "bar", (.075, .018, .060),
                    components=board_parts, bottom=.8, grasp_local=[0., 0., .020], density=250,
                    friction=[1.5, .006, .0001], condim=4)
        board["yaw"] = 0.
        objects.append(board)
    slots = [[.29, -.26], [.29, -.09], [.29, .22]]; rng.shuffle(slots)
    for i, xy in enumerate(slots):
        x, y, z, w = .095, .075, .015, .004
        # Open approach edge avoids a lip that would stop a slowly rolling ball.
        parts = [dict(size=[x, y, w], pos=[0., 0., -z+w]),
                 dict(size=[w, y, z], pos=[x-w, 0., 0.]),
                 dict(size=[x, w, z], pos=[0., -y+w, 0.]),
                 dict(size=[x, w, z], pos=[0., y-w, 0.])]
        objects.append(obj(f"catch{i}", xy, "white", "tray", (x, y, z),
                           components=parts, bottom=.8, inner_size=[x, y, z], marker=i, density=600))
    goals = [dict(type="nest", object="ball", target=f"catch{v}"),
             dict(type="guided_roll", object="ball", guides=[f"guide{i}" for i in range(3)], ramp="fixture0")]
    plan = [dict(object="gate", operation="guide_roll", target=f"catch{v}", xy=slots[v],
                 guides=[f"guide{i}" for i in range(3)], return_xy=[-.29, 0.], slope=slope)]
    return objects, goals, plan, [], fixtures


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
