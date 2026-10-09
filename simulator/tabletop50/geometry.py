"""Procedural rigid teaching props. All holes have real collision walls."""
import math
import xml.etree.ElementTree as ET

from robosuite.models.objects import BoxObject, CompositeObject, CylinderObject
from simulator.benchmark.environment import make_object
from .mechanical import annulus


def component_object(s, components):
    item = CompositeObject(name=s["id"], total_size=s["size"],
        geom_types=[p.get("type", "box") for p in components],
        geom_sizes=[p["size"] for p in components],
        geom_locations=[p["pos"] for p in components],
        geom_quats=[p.get("quat", [1, 0, 0, 0]) for p in components],
        geom_rgbas=[p.get("rgba", s["rgba"]) for p in components],
        locations_relative_to_center=True, density=s.get("density", 300),
        geom_frictions=[p.get("friction", s.get("friction", (1, .005, .0001))) for p in components])
    if "solref" in s:
        for geom in item.get_obj().iter("geom"):
            if geom.get("group") == "0": geom.set("solref", " ".join(map(str, s["solref"])))
    if "condim" in s:
        for geom in item.get_obj().iter("geom"):
            if geom.get("group") == "0": geom.set("condim", str(s["condim"]))
    for geom, part in zip((g for g in item.get_obj().iter("geom") if g.get("group") == "0"), components):
        if "priority" in part: geom.set("priority", str(part["priority"]))
    return item


def make_prop(s):
    kind = s["kind"]
    if kind == "hinged_panel":
        item = BoxObject(name=s["id"], size=s["size"], rgba=[.7, .7, .7, 1], density=2000)
        leaf = ET.SubElement(item.get_obj(), "body", name=item.naming_prefix+"leaf", pos="-.08 0 .027")
        ET.SubElement(leaf, "joint", name=item.naming_prefix+"hinge", type="hinge",
                      axis="0 -1 0", limited="true", range="0 1.6", damping=".02",
                      frictionloss=".025", armature=".0001",
                      solreffriction=".004 1", solimpfriction=".99 .99 .001")
        for name, size, pos in [("leaf_collision", ".08 .045 .006", ".08 0 0"),
                                ("handle_collision", ".020 .014 .018", ".145 0 .018")]:
            for group in [0, 1]:
                label = name if group == 0 else name.replace("collision", "visual")
                ET.SubElement(leaf, "geom", name=item.naming_prefix+label, type="box", size=size,
                              pos=pos, rgba=" ".join(map(str, s["rgba"])), density="80" if group == 0 else "0",
                              friction="1.5 .006 .0001", condim="4", group=str(group),
                              contype="1" if group == 0 else "0", conaffinity="1" if group == 0 else "0")
        # Composite metadata is cached before appending this articulated child.
        # Extend the raw names once; robosuite applies its usual object prefix.
        item._bodies.append("leaf"); item._joints.append("hinge")
        item._contact_geoms.extend(["leaf_collision", "handle_collision"])
        item._visual_geoms.extend(["leaf_visual", "handle_visual"])
        return item
    if "components" in s:
        return component_object(s, s["components"])
    if kind == "ring":
        return component_object(s, annulus(s["size"][0], s["inner_radius"], s["size"][2]))
    if kind == "post":
        x, y, z = s["size"]
        return component_object(s, [dict(type="cylinder", size=[x, .004], pos=[0, 0, -z+.004]),
                                   dict(type="cylinder", size=[s["post_radius"], z-.004], pos=[0, 0, .004])])
    if kind == "triangle":
        x, y, z = s["size"]
        item = BoxObject(name=s["id"], size=[x, y, z], rgba=s["rgba"], density=300)
        mesh_name = item.naming_prefix+"triangle_mesh"
        vertices = [[-x, -y, -z], [x, -y, -z], [0, y, -z],
                    [-x, -y, z], [x, -y, z], [0, y, z]]
        ET.SubElement(item.asset, "mesh", name=mesh_name,
                      vertex=" ".join(str(a) for point in vertices for a in point),
                      face="0 2 1 3 4 5 0 1 4 0 4 3 1 2 5 1 5 4 2 0 3 2 3 5")
        for geom in item.get_obj().iter("geom"):
            if geom.get("type") == "box":
                geom.set("type", "mesh"); geom.set("mesh", mesh_name); geom.attrib.pop("size", None)
                if geom.get("group") == "0":
                    geom.set("solref", ".004 1")
                    geom.set("solimp", ".99 .99 .001")
                    geom.set("friction", "1 .005 .0001")
        return item
    if "density" in s and kind in ("box", "bar", "arrow_bar"):
        item = BoxObject(name=s["id"], size=s["size"], rgba=s["rgba"], density=s["density"], friction=s.get("friction", [1, .005, .0001]))
        if "condim" in s:
            for geom in item.get_obj().iter("geom"):
                if geom.get("group") == "0": geom.set("condim", str(s["condim"]))
        return item
    return make_object(s)
