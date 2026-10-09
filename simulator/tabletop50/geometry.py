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
