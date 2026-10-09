"""Tool/contact tasks with real rigid contents and private process evidence."""
RECIPES = {"F40": "pour_solids"}


def build(recipe, v, rng, obj, position):
    if recipe != "pour_solids": raise NotImplementedError(recipe)
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
