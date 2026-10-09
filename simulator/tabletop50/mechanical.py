"""Large-clearance tabletop insertion recipes. No simulated attachment tricks."""
import math

RECIPES = {"F08": "shape_insert", "F11": "rings", "F12": "rack",
           "F13": "double_hole", "F14": "keyed"}


def annulus(outer, inner, half_height, count=24):
    thickness = (outer-inner)/2
    radius = (outer+inner)/2
    tangential = outer*math.tan(math.pi/count)
    return [dict(size=[thickness, tangential, half_height],
        pos=[radius*math.cos(a), radius*math.sin(a), 0.],
        quat=[math.cos(a/2), 0, 0, math.sin(a/2)])
        for a in [i*2*math.pi/count for i in range(count)]]


def polygon_walls(points, thickness, height):
    parts = []
    for a, b in zip(points, points[1:]+points[:1]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        normal = [dy/length, -dx/length]
        angle = math.atan2(dy, dx)
        parts.append(dict(size=[length/2+thickness, thickness, height],
            pos=[(a[0]+b[0])/2+normal[0]*thickness, (a[1]+b[1])/2+normal[1]*thickness, 0.],
            quat=[math.cos(angle/2), 0, 0, math.sin(angle/2)]))
    return parts


def build(recipe, v, rng, obj, position):
    objects, goals, plan, zones, fixtures = [], [], [], [], []
    colors = ["red", "green", "blue"]

    def move(name, xy, bottom=.8, yaw=None, fine=False):
        plan.append(dict(object=name, xy=list(xy), bottom=bottom, yaw=yaw, fine=fine))

    def fixture(xyz, half):
        fixtures.append(dict(type="box", xy=xyz[:2], z=xyz[2], size=half, rgba=[.4, .45, .5, 1]))

    if recipe == "shape_insert":
        kinds = ["bottle", "box", "triangle"]
        widths = [.023, .020, .032]
        for color_index, color in enumerate(colors):
            for shape, kind in enumerate(kinds):
                objects.append(obj(f"piece{color_index}_{shape}", [-.26+color_index*.11, -.22+shape*.22],
                                   color, kind, (widths[shape], widths[shape], .03)))
        for shape in range(3):
            xy = [.18, -.22+shape*.22]
            if shape == 0: components = annulus(.055, .025, .012)
            else:
                h = .022 if shape == 1 else .037
                points = [[-h, -h], [h, -h], [h, h], [-h, h]] if shape == 1 else [[-h, -h], [h, -h], [0, h]]
                components = polygon_walls(points, .008, .012)
            objects.append(obj(f"socket{shape}", xy, "white", "socket", (.06, .06, .012),
                               components=components, density=1800, hole_shape=shape))
            goals.append(position(f"socket{shape}", xy, .012))
            chosen = f"piece{v}_{shape}"
            goals.append(dict(type="insert", object=chosen, target=f"socket{shape}", tolerance=.004, relative_bottom=-.012))
            move(chosen, xy, fine=True)
        for c in range(3):
            if c != v:
                for shape in range(3):
                    name = f"piece{c}_{shape}"
                    s = next(s for s in objects if s["id"] == name)
                    goals.append(position(name, s["xy"]))
    elif recipe == "rings":
        for i, c in enumerate(colors):
            objects.append(obj(c, [-.18, -.22+i*.22], c, "ring", (.048, .048, .009), inner_radius=.030))
            xy = [.15, -.22+i*.22]
            objects.append(obj(f"post{i}", xy, "white", "post", (.055, .055, .035), post_radius=.010, density=1600))
            goals.append(position(f"post{i}", xy, .012))
        for i in range(3):
            name = colors[(i+v) % 3]
            xy = [.15, -.22+i*.22]
            goals.append(dict(type="threaded", object=name, target=f"post{i}"))
            move(name, xy, .808, fine=True)
    elif recipe == "rack":
        for i, c in enumerate(colors):
            # Thick plates start standing in broad supports; rotation is not
            # faked. Human card rack likewise holds the initial plates upright.
            objects.append(obj(c, [-.18, -.22+i*.22], c, "box", (.036, .012, .055)))
            fixture([-.18, -.22+i*.22-.018, .815], [.045, .006, .015])
            fixture([-.18, -.22+i*.22+.018, .815], [.045, .006, .015])
            y = -.22+i*.22
            fixture([.16, y-.020, .822], [.045, .006, .022])
            fixture([.16, y+.020, .822], [.045, .006, .022])
        for slot in range(3):
            chosen = colors[(slot+v) % 3]
            xy = [.16, -.22+slot*.22]
            goals += [position(chosen, xy, .006), dict(type="upright", object=chosen, axis=2),
                      dict(type="yaw", object=chosen, value=0., tolerance=.12)]
            move(chosen, xy, fine=True)
    elif recipe == "double_hole":
        for c, color in enumerate(colors):
            objects.append(obj(color, [-.13, -.22+c*.22], color, "bar", (.145, .014, .014)))
        for x in [.025, .21]:
            # Two real rectangular holes, aligned along X at z=.90.
            fixture([x, -.044, .9], [.010, .020, .07])
            fixture([x, .044, .9], [.010, .020, .07])
            fixture([x, 0., .858], [.010, .024, .018])
            fixture([x, 0., .942], [.010, .024, .018])
        chosen = colors[v]
        goals += [position(chosen, [.1175, 0.], .006), dict(type="shaft_height", object=chosen, z=.89),
                  dict(type="yaw", object=chosen, value=0., tolerance=.08)]
        # Horizontal threading, not dropping the shaft through solid frames.
        plan.append(dict(object=chosen, xy=[.1175, 0.], bottom=.876, yaw=0., fine=True,
                         approach=[-.145, 0., .89], insertion_axis=0))
        for c in colors:
            if c != chosen:
                s = next(s for s in objects if s["id"] == c)
                goals.append(position(c, s["xy"]))
    elif recipe == "keyed":
        components = [dict(size=[.020, .005, .03], pos=[0., -.015, 0.]),
                      dict(size=[.005, .020, .03], pos=[-.015, 0., 0.])]
        objects.append(obj("key", [-.18, 0.], "yellow", "key", (.02, .02, .03), components=components))
        h, notch = .026, -.004
        points = [[-h, -h], [h, -h], [h, notch], [notch, notch], [notch, h], [-h, h]]
        for i in range(3):
            angle = i*math.pi/2
            parts = polygon_walls(points, .008, .012)
            objects.append(obj(f"socket{i}", [.16, -.22+i*.22], "white", "socket", (.05, .05, .012), components=parts))
            objects[-1]["yaw"] = angle
            goals.append(position(f"socket{i}", objects[-1]["xy"], .012))
        goals += [dict(type="insert", object="key", target=f"socket{v}", tolerance=.005, relative_bottom=-.012),
                  dict(type="yaw", object="key", value=v*math.pi/2, tolerance=.1)]
        move("key", [.16, -.22+v*.22], yaw=v*math.pi/2, fine=True)
    else:
        raise NotImplementedError(recipe)
    return objects, goals, plan, zones, fixtures
