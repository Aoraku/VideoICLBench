"""Extended rigid-prop recipes, with explicit goals rather than generic fallbacks."""
import math


RECIPES = {"F10": "mosaic", "F16": "vacancy", "F17": "extract_stack",
           "F18": "swap_contents", "F19": "correct", "F20": "relocate",
           "F23": "uncover", "F24": "under_bar", "F26": "kits",
           "F28": "reference", "F29": "relative", "F30": "pair_arrows",
           "F31": "packing", "F32": "end_align", "F34": "height_pair",
           "F50": "replace_base"}


def extended(recipe, v, rng, obj, position):
    objects, goals, plan, zones, fixtures = [], [], [], [], []
    colors = ["red", "green", "blue", "yellow", "purple", "white"]

    def move(name, xy, bottom=.8, yaw=None):
        plan.append(dict(object=name, xy=list(xy), bottom=bottom, yaw=yaw))

    def at(name, xy, bottom=.8, yaw=None):
        goals.append(position(name, xy))
        if yaw is not None:
            goals.append(dict(type="yaw", object=name, value=yaw, tolerance=.18))
        move(name, xy, bottom, yaw)

    def bin_(name, xy, size=(.075, .075, .025), restore=True):
        objects.append(obj(name, xy, "white", "bowl", size))
        if restore: goals.append(position(name, xy, .012))

    def inside(name, target, xy):
        goals.append(dict(type="nest", object=name, target=target))
        move(name, xy, .808)

    def static_box(xy, half, z, rgba=(.4, .4, .4, 1)):
        fixtures.append(dict(type="box", xy=list(xy), size=list(half), z=z, rgba=list(rgba)))

    if recipe in ("mosaic", "correct", "relocate", "reference"):
        count = 3 if recipe == "reference" else 4 if recipe != "correct" else 6
        order = list(range(count)); rng.shuffle(order)
        if count == 3:
            dest = [[.14, -.18+i*.18] for i in range(3)]
            source = [[-.19, -.18+i*.18] for i in range(3)]
            permutation = (order, order[::-1], order[1:]+order[:1])[v]
        else:
            dest = [[.11 + (i//2)*.11, -.08+(i % 2)*.16] for i in range(count)]
            source = [[-.22+(i//3)*.12, -.22+(i % 3)*.22] for i in range(count)]
            permutation = (order, [order[2], order[0], order[3], order[1]],
                           [order[1], order[0], order[3], order[2]])[v] if count == 4 else order
        if recipe == "mosaic":
            # Congruent square grids are necessary for an actual quarter-turn
            # or mirror, rather than merely permuting a ragged reference row.
            source = [[-.23+(i//2)*.13, -.065+(i % 2)*.13] for i in range(4)]
            dest = [[.10+(i//2)*.13, -.065+(i % 2)*.13] for i in range(4)]
            for cx in [-.165, .165]:
                for x in [cx-.130, cx+.130]:
                    static_box([x, 0.], [.002, .132, .002], .802)
                for y in [-.130, .130]:
                    static_box([cx, y], [.130, .002, .002], .802)
                static_box([cx-.124, -.124], [.006, .006, .003], .803, (.12, .3, .85, 1))
                static_box([cx, 0.], [.002, .130, .002], .802)
                static_box([cx, 0.], [.130, .002, .002], .802)
            for prefix, cells in [("reference", source), ("target", dest)]:
                zones.extend(dict(id=f"{prefix}{i}", xy=xy, half_size=[.061, .061], marker=None)
                             for i, xy in enumerate(cells))
        if recipe in ("mosaic", "reference"):
            if recipe == "reference":
                zones.extend(dict(id=f"target{i}", xy=xy, half_size=[.045, .045], marker=None)
                             for i, xy in enumerate(dest))
            for i, index in enumerate(order):
                objects.append(obj(f"ref{i}", source[i], colors[index], size=(.025, .025, .025 if recipe == "mosaic" else .01)))
                goals.append(dict(type="place", object=f"ref{i}", target=f"reference{i}")
                             if recipe == "mosaic" else position(f"ref{i}", source[i], .012))
            movable_starts = [[0. if recipe == "mosaic" else -.04, -.22+i*.145] for i in range(count)]
        elif recipe == "relocate":
            # An asymmetric layout, with the same members in three rotations.
            source = [[-.22, -.16], [-.22, -.04], [-.10, -.16], [-.10, .08]]
            center = [.14, .04]
            relative = [[-.06, -.06], [-.06, .06], [.06, -.06], [.06, .18]]
            angle = v*math.pi/2
            dest = [[center[0]+x*math.cos(angle)-y*math.sin(angle),
                     center[1]+x*math.sin(angle)+y*math.cos(angle)] for x,y in relative]
            permutation = list(range(count)); movable_starts = source
            zones.append(dict(id="target_board", xy=center, half_size=[.22, .22], marker=None))
        else:
            # Six occupied pads, with exactly three locations changed per rule.
            dest = [[.04+(i//3)*.18, -.22+(i % 3)*.22] for i in range(6)]
            zones.extend(dict(id=f"work_cell{i}", xy=xy, half_size=[.04, .04], marker=None)
                         for i, xy in enumerate(dest))
            movable_starts = dest
            permutation = list(range(6))
            selected = ([0, 1, 2], [3, 4, 5], [0, 2, 4])[v]
            for a, b in zip(selected, selected[1:]+selected[:1]): permutation[a] = b
            # Three visible 2x3 diagrams use the same row/column topology as
            # the working grid; keep them in front of all movable pieces.
            for r, selected in enumerate(([0, 1, 2], [3, 4, 5], [0, 2, 4])):
                card_y = -.25+r*.25
                zones.append(dict(id=f"reference_card{r}", xy=[-.26, card_y],
                                  half_size=[.065, .095], marker=None))
                zones.append(dict(id=f"reference_label{r}", xy=[-.355, card_y],
                                  half_size=[.024, .024], marker=r))
                p = list(range(6))
                for a, b in zip(selected, selected[1:]+selected[:1]): p[a] = b
                for i in range(6):
                    static_box([-.29+(i//3)*.06, card_y-.06+(i % 3)*.06],
                               [.018, .018, .002], .803, colors_rgba(colors[p[i]]))
        for i in range(count):
            objects.append(obj(f"piece{i}", movable_starts[i], colors[i],
                               size=(.025, .025, .025 if recipe == "mosaic" else .012)))
        if recipe == "correct":
            changed = [i for i in range(count) if permutation[i] != i]
            # Clear occupied targets using distinct staging locations.
            for j, i in enumerate(changed): move(f"piece{i}", [-.02, -.22+j*.22])
        for slot, index in enumerate(permutation):
            if recipe == "mosaic":
                goals.append(dict(type="place", object=f"piece{index}", target=f"target{slot}"))
                move(f"piece{index}", dest[slot])
            else: at(f"piece{index}", dest[slot])
    elif recipe == "vacancy":
        spots = [[.10, -.24+i*.16] for i in range(4)]
        for i in range(5):
            static_box([.10, -.32+i*.16], [.06, .006, .018], .818)
        static_box([.165, 0.], [.006, .326, .018], .818)
        initial = list(range(3)); rng.shuffle(initial)
        for slot, i in enumerate(initial): objects.append(obj(f"piece{i}", spots[slot], colors[i]))
        mapping = (initial[1:]+initial[:1], initial[-1:]+initial[:-1], initial[::-1])[v]
        locations = {piece: slot for slot, piece in enumerate(initial)}
        for slot, piece in enumerate(mapping):
            if locations[piece] == slot: continue
            blocker = next((p for p, loc in locations.items() if loc == slot), None)
            if blocker is not None:
                empty = next(j for j in range(4) if j not in locations.values())
                move(f"piece{blocker}", spots[empty]); locations[blocker] = empty
            move(f"piece{piece}", spots[slot]); locations[piece] = slot
        goals = [position(f"piece{p}", spots[i]) for i, p in enumerate(mapping)]
    elif recipe == "extract_stack":
        rng.shuffle(colors)
        for i in range(5):
            objects.append(obj(f"layer{i}", [-.12, 0.], colors[i], bottom=.8+i*.05))
        selected = v+1
        for i in range(4, selected, -1): move(f"layer{i}", [.00, -.22+(i-selected-1)*.16])
        at(f"layer{selected}", [.20, -.22])
        remaining = [i for i in range(5) if i != selected]
        for level, i in enumerate(remaining):
            if i > selected: move(f"layer{i}", [-.12, 0.], .8+level*.05)
            if level == 0: goals.append(position(f"layer{i}", [-.12, 0.]))
            else: goals.append(dict(type="stack", object=f"layer{i}", target=f"layer{remaining[level-1]}"))
    elif recipe == "swap_contents":
        locs = [[-.12, -.20], [-.12, .20]]
        for i in range(2):
            bin_(f"bin{i}", locs[i], restore=False)
            for shape in range(2):
                name = f"piece{i}_{shape}"
                objects.append(obj(name, [locs[i][0], locs[i][1] + (shape-.5)*.065], colors[i],
                                   "bottle" if shape == 0 else "box", (.018, .018, .025), bottom=.808))
        zones.extend(dict(id=f"staging{i}", xy=[.14, -.23+i*.15],
                          half_size=[.045, .045], marker=None) for i in range(4))
        for i in range(2):
            for shape in range(2):
                name = f"piece{i}_{shape}"
                dest = 1-i if v == 0 or shape == v-1 else i
                goals.append(dict(type="nest", object=name, target=f"bin{dest}"))
                if dest != i: move(name, [.14, -.23+(i*2+shape)*.15])
        for i in range(2):
            for shape in range(2):
                dest = 1-i if v == 0 or shape == v-1 else i
                if dest != i: move(f"piece{i}_{shape}", [locs[dest][0], locs[dest][1]+(shape-.5)*.065], .808)
    elif recipe in ("uncover", "under_bar"):
        if recipe == "uncover":
            locs = [[.12, -.22], [.12, 0.], [.12, .22]]
            for i, xy in enumerate(locs):
                bin_(f"bin{i}", xy, (.065, .065, .025))
                zones.append(dict(id=f"box_label{i}", xy=[xy[0]-.11, xy[1]],
                                  half_size=[.025, .025], marker=i))
                objects.append(obj(f"piece{i}", xy, colors[i], size=(.018, .018, .018), bottom=.808))
                objects.append(obj(f"lid{i}", xy, "yellow", "lid", (.07, .07, .025), bottom=.85))
                goals.append(dict(type="cover", object=f"lid{i}", target=f"bin{i}"))
                if i != v: goals.append(dict(type="nest", object=f"piece{i}", target=f"bin{i}"))
            move(f"lid{v}", [-.18, 0.])
            at(f"piece{v}", [-.18, -.22])
            move(f"lid{v}", locs[v], .85)
        else:
            locs = [[.12, -.15+i*.15] for i in range(3)]
            for i, xy in enumerate(locs):
                objects.append(obj(f"piece{i}", xy, colors[i], size=(.035, .045, .012)))
                if i != v: goals.append(position(f"piece{i}", xy))
            objects.append(obj("cover_bar", [.12, 0.], "yellow", "bar", (.02, .23, .018), bottom=.824))
            zones.append(dict(id="bar_return", xy=[.12, 0.], half_size=[.027, .24], marker=None))
            move("cover_bar", [-.13, .05])
            at(f"piece{v}", [-.13, -.22])
            move("cover_bar", [.12, 0.])
            goals.append(position("cover_bar", [.12, 0.]))
    elif recipe == "kits":
        for group in range(3):
            palette = colors[:3].copy(); rng.shuffle(palette)
            for rank in range(3):
                name = f"part{group}_{rank}"
                xy = [-.28+group*.14, -.22+rank*.22]
                kind = ["box", "bar", "bottle"][group]
                size = .016+rank*.004
                dimensions = [(size, size, size), (size*2.4, size*.65, size*.85),
                              (size*.85, size*.85, size*1.7)][group]
                objects.append(obj(name, xy, palette[rank], kind, dimensions))
        zones.extend(dict(id=f"kit{rank}", xy=[.19, -.22+rank*.22],
                          half_size=[.15, .09], marker=None) for rank in range(3))
        for rank in range(3):
            for group in range(3):
                selected = rank if group == 0 else (rank+v) % 3 if group == 1 else (rank-v) % 3
                name = f"part{group}_{selected}"
                move(name, [.08+group*.11, -.22+rank*.22])
                goals.append(dict(type="on_mat", object=name, target=f"kit{rank}"))
    elif recipe == "relative":
        center = [.12, 0.]
        objects.append(obj("center", center, "yellow", "arrow_bar", (.035, .02, .015)))
        goals.append(position("center", center, .012))
        locs = [[.26, 0.], [.12, -.17], [.12, .17]]
        for i, kind in enumerate(["bottle", "box", "bar"]):
            objects.append(obj(f"piece{i}", [-.18, -.20+i*.20], colors[i], kind))
            at(f"piece{i}", locs[(i+v) % 3])
    elif recipe == "pair_arrows":
        for group in range(3):
            for member in range(2):
                name = f"bar{group}_{member}"
                xy = [-.22+member*.12, -.22+group*.22]
                objects.append(obj(name, xy, colors[group], "arrow_bar", (.04, .015, .015)))
                angle = (0 if member == 0 else math.pi) if v == 0 else (math.pi if member == 0 else 0) if v == 1 else 0
                at(name, [.05+member*.15, -.22+group*.22], yaw=angle)
    elif recipe == "packing":
        bin_("bin0", [.12, 0.], (.10, .10, .026), restore=False)
        objects.append(obj("lid", [-.20, .22], "yellow", "lid", (.105, .105, .025)))
        for i in range(4):
            objects.append(obj(f"piece{i}", [-.22+(i//2)*.12, -.22+(i % 2)*.13], colors[i],
                               "bar" if i < 2 else "box", (.072, .018, .018) if i < 2 else (.025, .025, .018)))
        # All three arrangements fit with physical margin, same packing count.
        placements = ([[-.065, 0.], [-.025, 0.], [.045, -.04], [.045, .04]],
                      [[.025, 0.], [.065, 0.], [-.045, -.04], [-.045, .04]],
                      [[-.065, 0.], [.065, 0.], [0., -.04], [0., .04]])[v]
        for i, (dy, dx) in enumerate(placements):
            xy = [.12+dx, dy]
            inside(f"piece{i}", "bin0", xy)
            if i < 2:
                side = (-1 if v == 0 else 1) if v != 2 else (-1 if i == 0 else 1)
                goals.append(dict(type="container_half", object=f"piece{i}", target="bin0", side=side))
        move("lid", [.12, 0.], .852)
        goals.append(dict(type="cover", object="lid", target="bin0"))
        for p in plan: p["operation"] = "pack"
    elif recipe == "end_align":
        for group in range(3):
            for member, length in enumerate([.035, .06]):
                name = f"bar{group}_{member}"
                objects.append(obj(name, [-.22+member*.12, -.22+group*.22], colors[group], "bar", (length, .014, .014)))
                x = .12 + ((length-.06) if v == 0 else (.06-length) if v == 1 else 0.)
                at(name, [x, -.25+group*.22+member*.055], yaw=0.)
    elif recipe == "height_pair":
        ranks = list(range(3)); rng.shuffle(ranks)
        locs = [[.14, -.22+i*.22] for i in range(3)]
        for i in range(3):
            objects.append(obj(f"base{i}", locs[i], "white", size=(.055, .055, .015+i*.015)))
            goals.append(position(f"base{i}", locs[i], .012))
            objects.append(obj(f"part{i}", [-.18, -.22+ranks[i]*.22], colors[i], size=(.022, .022, .02+i*.012)))
        mapping = ([0, 1, 2], [2, 1, 0], [2, 0, 1])[v]
        for base, part in enumerate(mapping):
            move(f"part{part}", locs[base], .8+2*(.015+base*.015))
            goals.append(dict(type="stack", object=f"part{part}", target=f"base{base}"))
    elif recipe == "replace_base":
        for i in range(3):
            half = .015+i*.01
            objects.append(obj(f"base{i}", [-.18, -.22+i*.22], colors[i], "handled_block", size=(.095, .06, half),
                components=[dict(size=[.06, .06, half], pos=[0, 0, 0]),
                            dict(size=[.018, .018, min(half, .01)], pos=[-.075, 0, 0])],
                grasp_local=[-.075, 0, 0]))
        objects.append(obj("old_base", [.12, 0.], "white", "handled_block", size=(.10, .09, .02),
            components=[dict(size=[.065, .09, .02], pos=[0, 0, 0]),
                        dict(size=[.018, .018, .01], pos=[-.08, 0, 0])], grasp_local=[-.08, 0, 0]))
        for i in range(2):
            objects.append(obj(f"upper{i}", [.12, -.045+i*.09], colors[i], size=(.025, .025, .025), bottom=.84))
            move(f"upper{i}", [.10, -.24+i*.48])
        move("old_base", [-.03, 0.])
        chosen = 2-v
        at(f"base{chosen}", [.12, 0.])
        for i in range(2):
            move(f"upper{i}", [.12, -.033+i*.066], .8+2*(.015+chosen*.01))
            goals += [dict(type="stack", object=f"upper{i}", target=f"base{chosen}"),
                      position(f"upper{i}", [.12, -.033+i*.066])]
        goals.append(position("old_base", [-.03, 0.]))
        for i in range(3):
            if i != chosen: goals.append(position(f"base{i}", [-.18, -.22+i*.22]))
    else:
        raise NotImplementedError(recipe)
    return objects, goals, plan, zones, fixtures


def colors_rgba(color):
    from .catalog import COLORS
    return COLORS[color]
