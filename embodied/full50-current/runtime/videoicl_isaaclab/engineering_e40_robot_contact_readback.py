"""Read-only cross-robot/clip forces during one E40 checkpoint continuation."""
import json
import numpy as np


def install(author):
    scene = author.scene; controller = author.c
    if scene.spec['id'] != 'E40' or not author.control_report.get('engineering_reference_only'):
        raise ValueError('Explicit E40 engineering contact readback required')
    physics = next(iter(scene.contacts.values()))[0]._physics_sim_view
    right = [scene.root_path + '/right_robot/' + n for n in scene.robots['right'].body_names]
    views = {}
    for name in scene.robots['left'].body_names:
        source = scene.root_path + '/left_robot/' + name
        views['left/' + name] = (physics.create_rigid_contact_view(
            source, filter_patterns=right, max_contact_data_count=1024),
            ['right/' + n for n in scene.robots['right'].body_names])
    clip = scene.mechanisms['clip1']
    paths = clip.root_physx_view.link_paths[0]
    robots = [scene.root_path + '/' + side + '_robot/' + n
              for side in ('left', 'right') for n in scene.robots[side].body_names]
    labels = [side + '/' + n for side in ('left', 'right') for n in scene.robots[side].body_names]
    for name, source in zip(clip.body_names, paths):
        views['clip1/' + name] = (physics.create_rigid_contact_view(
            source, filter_patterns=robots, max_contact_data_count=1024), labels)
    for view, targets in views.values():
        if view.sensor_count != 1 or view.filter_count != len(targets):
            raise ValueError('Exact native rigid-body contact filters required')
    peak = {}; errors = {}; last = [controller.steps]; first_tick = [controller.physics_ticks]
    path = author.out / 'e40-native-cross-robot-forces.private.jsonl'

    def flush():
        with path.open('a') as stream:
            stream.write(json.dumps(dict(read_only=True, stage=author.stage,
                steps=controller.steps, ticks=[first_tick[0], controller.physics_ticks],
                native_pair_peak_force_n=peak, read_errors=errors,
                no_physics_state_schema_or_target_changes=True)) + '\n')
        peak.clear(); errors.clear(); first_tick[0] = controller.physics_ticks

    def record(c, render):
        if c.steps != last[0]:
            flush(); last[0] = c.steps
        # Observer errors never interrupt an already accepted physical action.
        for source, (view, targets) in views.items():
            try:
                value = view.get_contact_force_matrix(c.dt)
                raw = value.detach().cpu().numpy() if hasattr(value, 'detach') else value
                force = np.asarray(raw, float).reshape(-1, 3)
                if force.shape != (len(targets), 3) or not np.isfinite(force).all():
                    raise ValueError('Invalid native contact force matrix')
                for target, magnitude in zip(targets, np.linalg.norm(force, axis=1)):
                    if magnitude > 1e-5:
                        key = source + ' -> ' + target
                        peak[key] = max(peak.get(key, 0.), float(magnitude))
            except Exception as exc:
                errors[source] = type(exc).__name__ + ': ' + str(exc)
    controller.tick_hooks.append(record)
    return dict(flush=flush, read_only=True)
