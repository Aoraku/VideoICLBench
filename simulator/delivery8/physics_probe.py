"""Private deployment probe of actual end-effector displacement, not a task score."""
import argparse
import json
from pathlib import Path
import sys

from motion import move


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.runtime.resolve()))
    from simulator.tabletop50.catalog import task_spec
    from simulator.tabletop50.environment import TabletopDual
    env = TabletopDual(task_spec('F01', 'A', 7), seed=7, render=False)
    site = env.robots[0].eef_site_id['right']
    cases = []
    try:
        for distance in (.5, 7.5, 25., 50.):
            before = env.sim.data.site_xpos[site].copy()
            move(env, 'UP', step_mm=distance)
            after = env.sim.data.site_xpos[site].copy()
            actual = float(after[2]-before[2])*1000
            cases.append(dict(requested_mm=distance, measured_z_mm=actual,
                              absolute_error_mm=abs(actual-distance)))
            if abs(actual-distance) > 1.5:
                raise AssertionError('Unexpected free-space displacement')
        args.output.write_text(json.dumps(dict(kind='private-free-space-motion-probe', cases=cases), indent=2)+'\n')
        print(json.dumps(cases), flush=True)
    finally: env.close()


if __name__ == '__main__': main()
