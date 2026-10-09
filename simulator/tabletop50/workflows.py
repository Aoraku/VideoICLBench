"""Multi-object dependencies using ordinary rigid household teaching props."""
from .mechanical import annulus

RECIPES = {"F09": "bridge", "F22": "layers", "F25": "change_cap",
           "F27": "top_up", "F33": "complete_lengths", "F35": "kit_delivery"}


def build(recipe, v, rng, obj, position):
    objects, goals, plan, zones, fixtures = [], [], [], [], []
    colors = ["red", "green", "blue", "yellow", "purple", "white"]

    def move(name, xy, bottom=.8, yaw=None, fine=False):
        plan.append(dict(object=name, xy=list(xy), bottom=bottom, yaw=yaw, fine=fine))

    def bin_(name, xy, size=(.09, .10, .025), bottom=None):
        kwargs = {} if bottom is None else dict(bottom=bottom)
        objects.append(obj(name, xy, "white", "tray", size, **kwargs))
        goals.append(position(name, xy, .015))

    if recipe == "bridge":
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
        bin_("lower", xy, (.085, .11, .022))
        bin_("upper", xy, (.085, .11, .022), bottom=.844)
        for i in range(3):
            objects.append(obj(f"piece{i}", [.12, -.065+i*.065], colors[i], size=(.018, .018, .012+i*.003), bottom=.808))
            objects.append(obj(f"upper_piece{i}", [.12, -.065+i*.065], colors[i], size=(.018, .018, .014), bottom=.852))
            goals.append(dict(type="nest", object=f"upper_piece{i}", target="upper"))
        selected = 2-v
        move("upper", [-.16, 0.])
        move(f"piece{selected}", [-.16, -.24])
        goals.append(position(f"piece{selected}", [-.16, -.24]))
        for i in range(3):
            if i != selected: goals.append(dict(type="nest", object=f"piece{i}", target="lower"))
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
            bin_(f"bin{i}", center)
            for j in range(i+1):
                name = f"initial{i}_{j}"; names.append(name)
                offset = positions[j]
                objects.append(obj(name, [center[0]+offset[0], center[1]+offset[1]], "yellow", size=(.014, .014, .014), bottom=.808))
        for j in range(4):
            name = f"spare{j}"; names.append(name)
            objects.append(obj(name, [-.23+(j//2)*.10, -.15+(j % 2)*.30], "yellow", size=(.014, .014, .014)))
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
        for i, length in enumerate(initial):
            xy = [-.05+length, -.22+i*.22]
            objects.append(obj(f"ref{i}", xy, "white", "bar", (length, .018, .018)))
            goals.append(position(f"ref{i}", xy, .008))
        for i, length in enumerate(spare):
            objects.append(obj(f"spare{i}", [-.23, -.28+i*.14], colors[i], "bar", (length, .018, .018)))
        chosen = ([4, 3, 2], [0, 1, 2], [4, 2, 0])[v]
        for row, i in enumerate(chosen):
            move(f"spare{i}", [-.05+2*initial[row]+spare[i], -.22+row*.22], fine=True)
        goals.append(dict(type="row_lengths", object="ref0", references=[f"ref{i}" for i in range(3)],
                          candidates=[f"spare{i}" for i in range(5)], relation=["equal", "increasing", "decreasing"][v]))
    elif recipe == "kit_delivery":
        center = [.10, 0.]
        objects.append(obj("carrier", center, "white", "tray", (.075, .12, .022)))
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
