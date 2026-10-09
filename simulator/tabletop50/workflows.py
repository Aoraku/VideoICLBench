"""Multi-object dependencies using ordinary rigid household teaching props."""
import math
from .mechanical import annulus

RECIPES = {"F09": "bridge", "F21": "clear_handles", "F22": "layers", "F25": "change_cap",
           "F27": "top_up", "F33": "complete_lengths", "F35": "kit_delivery",
           "F15": "mobile_board", "F47": "air_handover", "F48": "reconfigure_bin",
           "F49": "fold_display", "F46": "unlock_box"}


def handled_tray(obj, name, xy, x, y, z, bottom=None):
    w = .004
    parts = [dict(size=[x, y, w], pos=[0, 0, -z+w]),
             dict(size=[w, y, z], pos=[-x+w, 0, 0]), dict(size=[w, y, z], pos=[x-w, 0, 0]),
             dict(size=[x-w, w, z], pos=[0, -y+w, 0]), dict(size=[x-w, w, z], pos=[0, y-w, 0]),
             dict(size=[.025, .018, .012], pos=[0, -y-.014, 0]),
             dict(size=[.025, .018, .012], pos=[0, y+.014, 0])]
    kwargs = {} if bottom is None else dict(bottom=bottom)
    return obj(name, xy, "white", "tray", (x, y+.032, z), components=parts,
               inner_size=[x, y, z], grasp_sides=[[0, -y-.014, .005], [0, y+.014, .005]], **kwargs)


def build(recipe, v, rng, obj, position):
    objects, goals, plan, zones, fixtures = [], [], [], [], []
    colors = ["red", "green", "blue", "yellow", "purple", "white"]

    def move(name, xy, bottom=.8, yaw=None, fine=False):
        plan.append(dict(object=name, xy=list(xy), bottom=bottom, yaw=yaw, fine=fine))

    def bin_(name, xy, size=(.09, .10, .025), bottom=None, restore=True):
        kwargs = {} if bottom is None else dict(bottom=bottom)
        objects.append(obj(name, xy, "white", "tray", size, **kwargs))
        if restore: goals.append(position(name, xy, .015))

    if recipe == "unlock_box":
        x, y, z, w = .12, .13, .06, .008
        parts = [dict(size=[x, y, .004], pos=[0., 0., -z+.004]),
                 dict(size=[w, y, .05], pos=[-x+w, 0., -.01]),
                 dict(size=[w, y, .05], pos=[x-w, 0., -.01]),
                 dict(size=[x-w, w, .05], pos=[0., -y+w, -.01]),
                 dict(size=[x-w, w, .05], pos=[0., y-w, -.01])]
        # Two fixed rectangular rings flank the matching ring on the lid.
        for yy in [-.075, .075]:
            parts.append(dict(size=[.028, .015, .010], pos=[.14, yy, .005]))
            for xx in [-.018, .018]:
                parts.append(dict(size=[.006, .010, .025], pos=[.165+xx, yy, .035]))
            for zz in [-.018, .018]:
                parts.append(dict(size=[.012, .010, .006], pos=[.165, yy, .035+zz]))
        objects.append(obj("cabinet", [-.06, 0.], "white", "latched_box", (x, y, z),
                           components=parts, bottom=.8, density=3000, inner_size=[x, y, z],
                           leaf_grasp=[.24, 0., .075], leaf_pitch_sign=1, leaf_grasp_feedback=True))
        objects[-1]["yaw"] = math.pi  # Put the lock toward the first-person camera.
        bolt_parts = [dict(size=[.007, .110, .007], pos=[0., 0., -.030]),
                      dict(size=[.014, .018, .050], pos=[0., -.130, 0.])]
        objects.append(obj("bolt", [-.225, 0.], "yellow", "bar", (.014, .150, .050),
                           components=bolt_parts, bottom=.875, density=350,
                           grasp_local=[0., -.130, .035], condim=4, friction=[1.5, .006, .0001]))
        objects[-1]["yaw"] = math.pi
        palette = ["red", "green", "blue"]; rng.shuffle(palette)
        for i in range(3):
            width = .018+i*.007
            # A large wooden knob is an ordinary accessible grasp, avoiding
            # forcing a robot palm into the gap between box contents.
            pieces = [dict(size=[width, width, .020], pos=[0., 0., -.030]),
                      dict(size=[.009, .011, .028], pos=[0., 0., .018])]
            objects.append(obj(f"item{i}", [-.06, -.070+i*.070], palette[i], "box",
                               (width, width, .050), bottom=.808, density=180,
                               components=pieces, grasp_local=[0., 0., .032], approach_height=1.30))
        selected = 2-v
        zones = [dict(id="delivery", xy=[.23, -.22], half_size=[.075, .075], marker=0)]
        goals = [dict(type="place", object=f"item{selected}", target="delivery"),
                 dict(type="hinge_angle", object="cabinet", bounds=[-.03, .04]),
                 dict(type="bolt_engaged", object="bolt", target="cabinet")]
        goals += [dict(type="nest", object=f"item{i}", target="cabinet") for i in range(3) if i != selected]
        # Two ordinary blocks support the removed bolt horizontally, leaving
        # both hands free for the lid and box contents.
        fixtures += [dict(type="box", xy=[-.28, yy], z=.845,
                          size=[.025, .015, .045], rgba=[.65, .48, .28, 1])
                     for yy in [.115, .245]]
        plan = [dict(object="cabinet", operation="unlock_box", bolt="bolt", bolt_arm=1,
                     bolt_rest=[-.28, .18], item=f"item{selected}", xy=[.23, -.22])]
    elif recipe == "clear_handles":
        start = [-.12, 0.]
        slots = [[.18, -.23], [.18, 0.], [.18, .23]]; rng.shuffle(slots)
        objects.append(handled_tray(obj, "carrier", start, .07, .10, .025, bottom=.8))
        zones = [dict(id=f"delivery{i}", xy=xy, half_size=[.095, .12], marker=i)
                 for i, xy in enumerate(slots)]
        guards = []
        for i, y in enumerate([-.15, .15]):
            # Low wooden bridges cover both handles, with a real air gap above
            # the tray. The robots may use any physically valid alternative.
            parts = [dict(size=[.10, .030, .015], pos=[0., 0., .030])]
            parts += [dict(size=[.010, .030, .030], pos=[x, 0., -.015]) for x in [-.09, .09]]
            name = f"guard{i}"; xy = [start[0], y]
            objects.append(obj(name, xy, ["red", "blue"][i], "bar", (.10, .030, .045),
                               components=parts, bottom=.8, grasp_local=[0., 0., .030], density=350,
                               condim=4, friction=[1.5, .006, .0001]))
            zones.append(dict(id=f"home{i}", xy=xy, half_size=[.115, .047], marker=i))
            goals += [dict(type="place", object=name, target=f"home{i}"),
                      dict(type="yaw", object=name, value=0., tolerance=.13)]
            guards.append((name, xy))
            move(name, [-.23, -.28 if i == 0 else .28], fine=True)
        move("carrier", slots[v])
        for name, xy in guards: move(name, xy, fine=True)
        goals.append(position("carrier", slots[v]))
    elif recipe == "fold_display":
        selected = 2-v  # Left-to-right in the first-person camera.
        palette = ["red", "green", "blue"]; rng.shuffle(palette)
        for i in range(3):
            name = f"panel{i}"
            objects.append(obj(name, [.12, -.22+i*.22], palette[i], "hinged_panel", (.10, .065, .015), bottom=.8))
            goals.append(dict(type="hinge_angle", object=name,
                              bounds=[1.02, 1.35] if i == selected else [-.03, .06]))
        support_parts = [dict(size=[.018, .035, .060], pos=[0., 0., 0.]),
                         dict(size=[.050, .014, .014], pos=[.060, 0., -.020])]
        objects.append(obj("support", [-.20, 0.], "white", "bar", (.11, .035, .060),
                           components=support_parts, density=200, grasp_local=[.075, 0., -.020],
                           condim=4, friction=[1.5, .006, .0001]))
        goals.append(dict(type="leaf_support", object=f"panel{selected}", target="support"))
        plan.append(dict(object=f"panel{selected}", operation="fold_display",
                         xy=[.12, -.22+selected*.22], bottom=.8, support="support"))
    elif recipe == "mobile_board":
        start, finish = [-.14, 0.], [.15, 0.]
        components = annulus(.067, .020, .012)
        for sign in [-1, 1]:
            components += [dict(size=[.009, .04, .008], pos=[0., sign*.085, 0.]),
                           dict(size=[.024, .018, .012], pos=[0., sign*.12, 0.])]
        objects.append(obj("board", start, "white", "tray", (.075, .14, .012), components=components,
                           bottom=.88, density=600, grasp_sides=[[0., -.12, .004], [0., .12, .004]]))
        for center in [start, finish]:
            for dx in [-.044, .044]:
                for dy in [-.044, .044]:
                    fixtures.append(dict(type="box", xy=[center[0]+dx, center[1]+dy], z=.84,
                                         size=[.012, .012, .04], rgba=[.4, .45, .5, 1]))
        for i, half in enumerate([.03, .04, .05]):
            parts = [dict(type="cylinder", size=[.013, half], pos=[0., 0., 0.]),
                     dict(type="cylinder", size=[.030, .006], pos=[0., 0., half-.006])]
            objects.append(obj(f"peg{i}", [-.16+i*.16, -.25], colors[i], "bottle", (.03, .03, half), components=parts,
                               grasp_local=[0., 0., half-.004]))
            if i != v: goals.append(position(f"peg{i}", [-.16+i*.16, -.25]))
        half = [.03, .04, .05][v]
        move(f"peg{v}", start, .916-2*half, fine=True)
        move("board", finish, .88)
        goals += [position("board", finish, .015),
                  dict(type="collared", object=f"peg{v}", target="board")]
    elif recipe == "reconfigure_bin":
        center = [.12, 0.]
        x, y, z, w = .17, .12, .032, .004
        parts = [dict(size=[x, y, w], pos=[0., 0., -z+w]),
                 dict(size=[w, y, z], pos=[-x+w, 0., 0.]), dict(size=[w, y, z], pos=[x-w, 0., 0.]),
                 dict(size=[x, w, z], pos=[0., -y+w, 0.]), dict(size=[x, w, z], pos=[0., y-w, 0.])]
        # End guides make real loose slots. All possible configurations are
        # present in every rule, and no divider is welded to its slot.
        for slot in [-.10, -.04, .04, .10]:
            for sign in [-1, 1]:
                for end in [-1, 1]:
                    parts.append(dict(size=[.002, .010, .014], pos=[slot+sign*.011, end*.104, -.010]))
        objects.append(obj("case", center, "white", "tray", (x, y, z), components=parts, density=1000))
        goals.append(position("case", center, .015))
        # Slotted household organisers: full-height dividers remain removable.
        for i, x in enumerate([.08, .16]):
            objects.append(obj(f"divider{i}", [x, 0.], "white", "bar", (.006, .108, .024), bottom=.808,
                               grasp_local=[0., 0., .015]))
        objects.append(obj("lid", [.12, .265], "white", "lid", (.174, .124, .026)))
        for i in range(3):
            objects.append(obj(f"part{i}", [-.30, -.27+i*.27], colors[i], "bar", (.045, .024, .018)))
        offsets = ([.04, .10], [-.10, .10], [-.10, -.04])[v]
        for i in range(2):
            stage = [-.18, -.22+i*.44]
            for side in [-1, 1]:
                for end in [-1, 1]:
                    fixtures.append(dict(type="box", xy=[stage[0]+side*.014, stage[1]+end*.09], z=.82,
                                         size=[.006, .012, .02], rgba=[.4, .45, .5, 1]))
            move(f"divider{i}", stage, fine=True)
        for i, dx in enumerate(offsets):
            move(f"divider{i}", [center[0]+dx, 0.], .808, fine=True)
            goals += [position(f"divider{i}", [center[0]+dx, 0.], .008),
                      dict(type="yaw", object=f"divider{i}", value=0., tolerance=.1)]
        long_center = center[0]+[-.071, 0., .071][v]
        # The three bars form a bundle in the enlarged compartment, rather
        # than fitting through a narrow neighbouring compartment.
        for i in range(3):
            move(f"part{i}", [long_center, -.063+i*.063], .808, fine=True)
            goals += [dict(type="nest", object=f"part{i}", target="case"),
                      position(f"part{i}", [long_center, -.063+i*.063], .012)]
        move("lid", center, .864)
        goals.append(dict(type="cover", object="lid", target="case"))
    elif recipe == "air_handover":
        objects.append(obj("baton", [-.16, -.24], "yellow", "arrow_bar", (.025, .12, .018), density=150))
        angles = [0., 1.5707963267948966, -1.5707963267948966]
        zones.append(dict(id="delivery", xy=[.15, 0.], half_size=[.15, .15], marker=0))
        goals = [position("baton", [.15, 0.], .02), dict(type="handover", object="baton"),
                 dict(type="yaw", object="baton", value=angles[v], tolerance=.12)]
        plan.append(dict(object="baton", operation="handover", xy=[.15, 0.], bottom=.8,
                         yaw=angles[v], giver_grasp=[0., -.075, 0.], receiver_grasp=[0., .075, .004]))
    elif recipe == "bridge":
        for i in range(3):
            objects.append(obj(f"pillar{i}", [-.22, -.22+i*.22], colors[i], size=(.035, .035, .045)))
        objects.append(obj("beam", [-.04, 0.], "yellow", "bar", (.035, .12, .012)))
        objects.append(obj("load", [-.04, .24], "purple", size=(.025, .025, .025)))
        selected = [v, (v+1) % 3]
        for side, i in enumerate(selected):
            xy = [.15, -.07+side*.14]
            goals.append(position(f"pillar{i}", xy)); move(f"pillar{i}", xy)
        other = (v+2) % 3
        goals.append(position(f"pillar{other}", [-.22, -.22+other*.22]))
        move("beam", [.15, 0.], .89)
        move("load", [.15, 0.], .914)
        goals += [dict(type="bridge", object="beam", supports=[f"pillar{i}" for i in selected]),
                  dict(type="stack", object="load", target="beam")]
    elif recipe == "layers":
        xy = [.12, 0.]
        objects.append(handled_tray(obj, "lower", xy, .085, .11, .022))
        goals.append(position("lower", xy, .015))
        objects.append(handled_tray(obj, "upper", xy, .095, .12, .022, bottom=.844))
        goals.append(position("upper", xy, .015))
        for i in range(3):
            objects.append(obj(f"piece{i}", [.12, -.065+i*.065], colors[i], size=(.018, .018, .010+i*.003), bottom=.808))
            objects.append(obj(f"upper_piece{i}", [.12, -.065+i*.065], colors[i], size=(.018, .018, .014), bottom=.852))
            goals.append(dict(type="nest", object=f"upper_piece{i}", target="upper"))
        selected = 2-v
        move("upper", [-.16, 0.])
        move(f"piece{selected}", [-.16, -.24])
        goals.append(position(f"piece{selected}", [-.16, -.24]))
        for i in range(3):
            if i != selected: goals.append(dict(type="nest", object=f"piece{i}", target="lower"))
        move("lower", xy)
        move("upper", xy, .844)
        goals.append(dict(type="stack", object="upper", target="lower"))
    elif recipe == "change_cap":
        selected = 2-v
        parts = annulus(.032, .019, .020)+[dict(type="cylinder", size=[.032, .003], pos=[0, 0, .017])]
        for i in range(3):
            xy = [.14, -.22+i*.22]
            half = .025+i*.010
            objects.append(obj(f"post{i}", xy, "white", "post", (.05, .05, half), post_radius=.010, density=1600))
            objects.append(obj(f"cap{i}", xy, colors[i], "ring", (.032, .032, .02),
                               inner_radius=.019, components=parts, bottom=.8+2*half-.034))
            goals.append(position(f"post{i}", xy, .012))
            if i != selected: goals.append(dict(type="cap_on", object=f"cap{i}", target=f"post{i}"))
        objects.append(obj("new_cap", [-.18, 0.], "purple", "ring", (.032, .032, .02), inner_radius=.019, components=parts))
        bin_("recycle", [-.18, -.23], (.06, .06, .022))
        move(f"cap{selected}", [-.18, -.23], .808)
        goals.append(dict(type="nest", object=f"cap{selected}", target="recycle"))
        move("new_cap", [.14, -.22+selected*.22], .8+2*(.025+selected*.010)-.034, fine=True)
        goals.append(dict(type="cap_on", object="new_cap", target=f"post{selected}"))
    elif recipe == "top_up":
        desired = ([3, 4, 3], [4, 3, 3], [3, 3, 4])[v]
        positions = [[-.035, -.035], [-.035, .035], [.035, -.035], [.035, .035]]
        names = []
        for i in range(3):
            center = [.15, -.22+i*.22]
            bin_(f"bin{i}", center, restore=False)
            for j in range(i+1):
                name = f"initial{i}_{j}"; names.append(name)
                offset = positions[j]
                objects.append(obj(name, [center[0]+offset[0], center[1]+offset[1]], "yellow", size=(.020, .020, .020), bottom=.808))
        for j in range(4):
            name = f"spare{j}"; names.append(name)
            objects.append(obj(name, [-.23+(j//2)*.10, -.15+(j % 2)*.30], "yellow", size=(.020, .020, .020)))
        next_spare = 0
        for i, count in enumerate(desired):
            center = [.15, -.22+i*.22]
            for j in range(i+1, count):
                offset = positions[j]
                move(f"spare{next_spare}", [center[0]+offset[0], center[1]+offset[1]], .808, fine=True)
                next_spare += 1
            goals.append(dict(type="count_in", object=names[0], target=f"bin{i}", objects=names, count=count))
    elif recipe == "complete_lengths":
        initial = [.02, .03, .04]
        spare = [.02, .03, .04, .05, .06]
        spare_colours = colors[:5].copy(); rng.shuffle(spare_colours)
        for i, length in enumerate(initial):
            xy = [-.05+length, -.22+i*.22]
            objects.append(obj(f"ref{i}", xy, "white", "bar", (length, .018, .018)))
            goals.append(position(f"ref{i}", xy, .008))
        for i, length in enumerate(spare):
            objects.append(obj(f"spare{i}", [-.23, -.28+i*.14], spare_colours[i], "bar", (length, .018, .018)))
        chosen = ([4, 3, 2], [0, 1, 2], [4, 2, 0])[v]
        for row, i in enumerate(chosen):
            move(f"spare{i}", [-.05+2*initial[row]+spare[i], -.22+row*.22], fine=True)
        goals.append(dict(type="row_lengths", object="ref0", references=[f"ref{i}" for i in range(3)],
                          candidates=[f"spare{i}" for i in range(5)], relation=["equal", "increasing", "decreasing"][v]))
    elif recipe == "kit_delivery":
        center = [.10, 0.]
        objects.append(handled_tray(obj, "carrier", center, .075, .12, .022))
        for group, kind in enumerate(["box", "bar", "bottle"]):
            for rank in range(3):
                half = .016+rank*.004
                objects.append(obj(f"part{group}_{rank}", [-.28+group*.09, -.22+rank*.22], colors[(group+rank) % 3], kind,
                                   (half, half, half)))
        for group in range(3):
            name = f"part{group}_{v}"
            move(name, [center[0], -.075+group*.075], .808, fine=True)
            goals.append(dict(type="nest", object=name, target="carrier"))
            goals.append(dict(type="local_position", object=name, target="carrier", xy=[0., -.075+group*.075], tolerance=.02))
        move("carrier", [.18, 0.])
        goals.append(position("carrier", [.18, 0.], .02))
        for s in objects:
            if s["id"].startswith("part") and not s["id"].endswith(f"_{v}"):
                goals.append(position(s["id"], s["xy"]))
    else:
        raise NotImplementedError(recipe)
    return objects, goals, plan, zones, fixtures
