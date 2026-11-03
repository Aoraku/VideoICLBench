"""E28 v3: measured blade insertion before unsupported, hand-free lift.

No action names or author claims enter the witness. A tool/food collision alone
cannot distinguish scooping from hand-loading; relative edge advance while the
food is still table-supported is required before the blade may carry it.
"""
from copy import deepcopy
import numpy as np

REVISION = 'embodied50-execution-v3-20261102'


def enabled(spec):
    return spec.get('id') == 'E28' and spec.get('execution_design', {}).get('revision') == REVISION


class ScoopWitness:
    def __init__(self):
        self.pending = {}
        self.records = {}

    def observe(self, name, *, step, table_supported, held, hand_grasp,
                hand_contact, tool_contact, edge_under, relative_edge,
                food_bottom, supported_on_blade, blade_gap_m=None):
        """All scalars come from this physics tick's actual state/contact map."""
        if name in self.records:
            if hand_grasp or hand_contact:
                # A historical scoop cannot license a later hand-loaded carry.
                self.records.pop(name,None);self.pending.pop(name,None)
                return False
            return True
        if hand_grasp or (hand_contact and not table_supported) or not held:
            self.pending.pop(name, None)
            return False
        p = self.pending.get(name)
        if not table_supported and not tool_contact:
            # A measured 4 ms contact dropout at initial lift must not erase
            # completed table-supported insertion. Preserve only that history,
            # for at most two consecutive ticks, near the same blade edge and
            # table height. This tick can never establish a lift or transport.
            near_entry = (p and p['inserted'] and not hand_contact and edge_under
                and blade_gap_m is not None and abs(blade_gap_m) <= .001
                and -.001 <= food_bottom-p['table_bottom'] <= .003
                and abs(relative_edge-p.get('last_contact_edge', relative_edge)) <= .0015
                and int(step) == p.get('last_seen_step', -2)+1
                and p.get('contact_gap_ticks', 0) < 2)
            if near_entry:
                p['contact_gap_ticks'] = p.get('contact_gap_ticks', 0)+1
                p['last_seen_step'] = int(step)
            else:
                self.pending.pop(name, None)
            return False
        if table_supported and tool_contact and edge_under:
            if p is None:
                p = self.pending[name] = dict(entry_step=int(step),
                    edge_start=float(relative_edge), table_bottom=float(food_bottom),
                    insertion_m=0., inserted=False)
            p['insertion_m'] = max(p['insertion_m'], float(relative_edge)-p['edge_start'])
            p['inserted'] = p['insertion_m'] >= .004
        elif table_supported and not tool_contact:
            self.pending.pop(name, None)
            return False
        if p and tool_contact:
            p['last_contact_edge'] = float(relative_edge)
            p['last_seen_step'] = int(step)
            p['contact_gap_ticks'] = 0
        if p and p['inserted'] and not table_supported and not hand_contact and tool_contact and supported_on_blade and food_bottom-p['table_bottom'] >= .006:
            self.records[name] = dict(**p, lift_step=int(step),
                lift_m=float(food_bottom-p['table_bottom']), hand_free=True,
                source='native_edge_advance_table_contact_then_blade_supported_lift')
            return True
        return False

    def measured(self, evaluator, name, supported_on_blade):
        e = evaluator; tool = e.tool; tv = e.state[tool['actor']]
        center, half = e.bounds(name)
        normal = np.asarray(tool['support_normal_local'], float)
        normal /= np.linalg.norm(normal)
        forward = -np.asarray(tool['withdraw_local'], float)
        forward -= normal * float(forward @ normal)
        forward /= np.linalg.norm(forward)
        forward_world = tv['mat'] @ forward
        edge = np.asarray(tool['edge_segment'], float)
        world_edge = (tv['mat'] @ edge.T).T + tv['pos']
        midpoint = world_edge.mean(axis=0)
        bottom = float(center[2]-half[2])
        # The actual leading edge must intersect the food footprint at its
        # underside, not merely touch a vertical side or its top surface.
        d = world_edge[1,:2]-world_edge[0,:2]
        u = np.clip(float((center[:2]-world_edge[0,:2])@d)/max(float(d@d),1e-12),0.,1.)
        nearest = world_edge[0,:2]+u*d
        edge_under = bool(np.all(np.abs(nearest-center[:2])<=half[:2]+.002)
                          and bottom-.006 <= midpoint[2] <= bottom+.004)
        local = tv['mat'].T @ (center-tv['pos'])
        world_normal = tv['mat'] @ normal
        obj = e.objects[name]
        extent = (float(max(obj['size'])) if obj.get('kind') == 'sphere' else
                  float(np.abs(e.state[name]['mat'].T @ world_normal) @ np.asarray(obj['size'], float)))
        blade_gap = float(normal @ local)-extent-tool['support_plane_offset']
        return self.observe(name, step=e.steps,
            table_supported=e.force(name,'table')>0,
            held=e.held(tool['actor']), hand_grasp=any(e.state[name]['grasp']),
            hand_contact=e.hand_force(name)>0, tool_contact=e.force(name,tool['actor'])>0,
            edge_under=edge_under, relative_edge=float((midpoint-center)@forward_world),
            food_bottom=bottom, supported_on_blade=supported_on_blade,
            blade_gap_m=blade_gap if enabled(e.spec) else None)

    def export(self, label):
        return {label(n): deepcopy(v) for n,v in self.records.items()}
