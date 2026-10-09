"""Private recipe generation. Rule choice never changes the visible world."""
import copy
import hashlib
import json
import math
import random

from .families import BY_ID, REVISION

COLORS = {
    "red": [.85, .12, .1, 1], "green": [.12, .7, .22, 1],
    "blue": [.12, .3, .85, 1], "yellow": [.95, .72, .12, 1],
    "white": [.85, .85, .85, 1], "purple": [.65, .2, .75, 1],
}
IMPLEMENTED = tuple(k for k, f in BY_ID.items() if f["runtime_recipe"])


def obj(name, xy, color="red", kind="box", size=(.025, .025, .025), **extra):
    return dict(id=name, kind=kind, rgba=list(COLORS[color]), size=list(size), xy=list(xy), yaw=0., **extra)


def position(name, xy, tolerance=.025):
    return dict(type="position", object=name, xy=list(xy), tolerance=tolerance)


def task_spec(task_id, variant="A", seed=0):
    if task_id not in BY_ID or variant not in "ABC" or len(variant) != 1:
        raise ValueError("Unknown task or rule")
    family = BY_ID[task_id]
    if family["runtime_recipe"] is None:
        raise NotImplementedError(f"{task_id} has a design, but no accepted runtime recipe")
    rng = random.Random(seed)
    v = "ABC".index(variant)
    colors = ["red", "green", "blue"]
    starts = [[-.16, -.20], [-.16, 0.], [-.16, .20], [-.03, -.20]]
    rng.shuffle(starts)
    slots = [[.15, -.22], [.15, 0.], [.15, .22]]
    # Layout variation is independent of rule; marker identities move with pads.
    rng.shuffle(slots)
    objects, goals, plan, zones, fixtures = [], [], [], [], []

    def move(name, xy, bottom=.8, yaw=None):
        plan.append(dict(object=name, xy=list(xy), bottom=bottom, yaw=yaw))

    recipe = family["runtime_recipe"]
    if recipe == "stack3":
        objects = [obj(c, starts[i], c) for i, c in enumerate(colors)]
        order = colors[v:] + colors[:v]
        goals = [position(order[0], [.12, 0.])]
        for i, name in enumerate(order):
            if i:
                goals.append(dict(type="stack", object=name, target=order[i-1]))
            move(name, [.12, 0.], .8 + i*.05)
    elif recipe == "cup":
        objects = [obj("cup", starts[0], "yellow", "cup", (.034, .034, .042))]
        zones = [dict(id=f"pad{i}", xy=xy, half_size=[.055, .055], marker=i) for i, xy in enumerate(slots)]
        goals = [dict(type="place", object="cup", target=f"pad{v}")]
        move("cup", slots[v])
    elif recipe == "rank":
        sizes = sorted(rng.uniform(.017+i*.005, .019+i*.005) for i in range(4))
        color_order = ["red", "green", "blue", "yellow"]
        rng.shuffle(color_order)
        objects = [obj(f"size{i}", starts[i], color_order[i], size=[s]*3) for i, s in enumerate(sizes)]
        order = ([0, 1, 2, 3], [3, 2, 1, 0], [1, 3, 0, 2])[v]
        for j, i in enumerate(order):
            xy = [.15, -.225 + .15*j]
            goals.append(position(f"size{i}", xy)); move(f"size{i}", xy)
    elif recipe == "select":
        other_colors = ["red", "green"]; rng.shuffle(other_colors)
        objects = [obj("tall", starts[0], other_colors[0], size=[.021, .021, rng.uniform(.045, .055)]),
                   obj("wide", starts[1], other_colors[1], size=[rng.uniform(.034, .039), .026, .02]),
                   obj("blue", starts[2], "blue", size=[.025, .025, rng.uniform(.028, .035)]),
                   obj("stand", [.15, 0.], "white", size=[.06, .06, .02])]
        chosen = ["tall", "wide", "blue"][v]
        goals = [dict(type="stack", object=chosen, target="stand")]
        move(chosen, [.15, 0.], .84)
        for o in objects[:3]:
            if o["id"] != chosen:
                goals.append(position(o["id"], o["xy"]))
    elif recipe in ("classify", "group"):
        nboxes = 3 if recipe == "classify" else 2
        locations = slots if nboxes == 3 else [[.15, -.19], [.15, .19]]
        for i, xy in enumerate(locations):
            objects.append(obj(f"bin{i}", xy, "white", "bowl", (.075, .075, .025)))
        kinds = ["bottle", "box", "bar"] if nboxes == 3 else ["bottle", "box"]
        contents = []
        for shape, kind in enumerate(kinds):
            for c in range(2):
                name = f"part{shape}_{c}"
                xy = [-.23 + c*.11, -.21 + shape*.21] if nboxes == 3 else [-.23+c*.11, -.16+shape*.32]
                color = ["red", "blue"][c]
                size = (.017, .017, .024) if kind == "bottle" else ((.027, .014, .015) if kind == "bar" else (.018,)*3)
                objects.append(obj(name, xy, color, kind, size))
                dest = (shape + v) % 3 if nboxes == 3 else (c if v == 0 else shape if v == 1 else (shape+c) % 2)
                contents.append((name, dest))
                goals.append(dict(type="nest", object=name, target=f"bin{dest}"))
        for name, dest in contents:
            siblings = [n for n, d in contents if d == dest]
            offset = (siblings.index(name) - .5)*.065
            xy = [locations[dest][0], locations[dest][1] + offset]
            move(name, xy, .808)
    elif recipe == "orient":
        objects = [obj(c, starts[i], c, "arrow_bar", (.05, .018, .018)) for i, c in enumerate(["red", "blue"])]
        angles = ([0., 0.], [math.pi, math.pi], [0., math.pi])[v]
        for i, (name, angle) in enumerate(zip(["red", "blue"], angles)):
            xy = [.15, -.10 + i*.20]
            goals += [position(name, xy), dict(type="yaw", object=name, value=angle, tolerance=.18)]
            move(name, xy, yaw=angle)
    else:
        from .recipes import extended
        from .mechanical import RECIPES as mechanical_recipes, build
        from .workflows import RECIPES as workflow_recipes, build as workflow_build
        from .tool_tasks import RECIPES as tool_recipes, build as tool_build
        generator = build if task_id in mechanical_recipes else workflow_build if task_id in workflow_recipes else tool_build if task_id in tool_recipes else extended
        objects, goals, plan, zones, fixtures = generator(recipe, v, rng, obj, position)
    # Continuous jitter tests movement, not rule. It is recorded in both views.
    offset = [rng.uniform(-.006, .006), rng.uniform(-.006, .006)]
    for o in objects:
        o["xy"] = [a+b for a, b in zip(o["xy"], offset)]
    for z in zones:
        z["xy"] = [a+b for a, b in zip(z["xy"], offset)]
    for g in goals:
        if g["type"] == "through_apertures":
            for aperture in g["apertures"]:
                aperture[:2] = [a+b for a, b in zip(aperture[:2], offset)]
        if "xy" in g and g["type"] != "local_position":
            g["xy"] = [a+b for a, b in zip(g["xy"], offset)]
    for p in plan:
        p["xy"] = [a+b for a, b in zip(p["xy"], offset)]
        if "approach" in p:
            p["approach"][:2] = [a+b for a, b in zip(p["approach"][:2], offset)]
        for field in ("return_xy", "start_xy"):
            if field in p: p[field] = [a+b for a, b in zip(p[field], offset)]
    for fixture in fixtures:
        fixture["xy"] = [a+b for a, b in zip(fixture["xy"], offset)]
    return dict(id=task_id, title=family["title"], revision=REVISION, task_revision=1,
                variant=variant, seed=seed, objects=objects, zones=zones,
                fixtures=fixtures, goals=goals, author_plan=plan, action_budget=1600,
                public_instruction="按照示范完成这项桌面工作。")


def visible_world(spec):
    return copy.deepcopy({k: spec[k] for k in ("objects", "zones", "fixtures", "public_instruction")})


def world_sha256(spec):
    return hashlib.sha256(json.dumps(visible_world(spec), sort_keys=True).encode()).hexdigest()
