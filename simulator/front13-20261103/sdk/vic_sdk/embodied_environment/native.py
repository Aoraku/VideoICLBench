"""Adapter for the existing bounded Isaac Controller, with no expert policy."""
import base64
from copy import deepcopy
import io


class ControllerRuntime:
    def __init__(self, controller):
        self.controller = controller
        self.sealed = False
        self.result = None
        self.rgb_snapshot = {}

    def observe(self):
        from PIL import Image
        controller = self.controller
        scene, context = controller.scene, controller.sim
        for _ in range(3):
            scene.prepare_render()
            context.render()
            scene.update_render_cameras()
        images = {}
        calibration = {}
        depth = {}
        for name in ('head', 'left_wrist', 'right_wrist'):
            camera = scene.cameras[name]
            camera.update(0., force_recompute=True)
            rgb = camera.data.output['rgb'][0, :, :, :3].cpu().numpy()
            buffer = io.BytesIO()
            Image.fromarray(rgb).save(buffer, format='JPEG', quality=94)
            images[name] = base64.b64encode(buffer.getvalue()).decode()
            calibration[name] = scene.rgb_camera_calibration(name)
            if 'distance_to_image_plane' in camera.data.output:
                from .sensor_depth import encode_depth_packet
                packet = encode_depth_packet(camera.data.output['distance_to_image_plane'].cpu().numpy(),
                    rgb_bytes=buffer.getvalue(), observation_tick=controller.physics_ticks)
                if (packet['height'], packet['width']) != rgb.shape[:2]:
                    raise ValueError('RGB and sensor depth dimensions differ')
                depth[name] = packet
        self.rgb_snapshot = dict(images=deepcopy(images), camera_calibration=calibration,
                                 observation_tick=controller.physics_ticks, depth=depth)
        return images

    def rgb_measurement_snapshot(self):
        return {k:deepcopy(v) for k,v in self.rgb_snapshot.items() if k != "depth"}

    def sensor_depth_snapshot(self):
        return deepcopy(self.rgb_snapshot)

    def action(self, *, left, right, step_mm, rotation_deg):
        if self.sealed:
            raise RuntimeError('Native episode is sealed')
        return self.controller.action(left=left, right=right, step_mm=step_mm, rotation_deg=rotation_deg)

    def seal(self):
        self.sealed = True  # No further actions or physics ticks are admitted.

    def evaluate(self):
        if not self.sealed:
            raise RuntimeError('Seal the native episode before scoring')
        if self.result is None:
            self.result = deepcopy(self.controller.evaluator.result())
        return deepcopy(self.result)

    def public_feedback(self):
        """Measured robot proprioception, matching the RGB RoboProbe boundary.

        All coordinates refer to this room's declared task frame. This reads
        robot sensors and camera calibration only; it has no object pose or dense depth,
        contact labels or evaluator result in its output.
        """
        from .sensor_depth import depth_packet_metadata
        return dict(self.controller.public_feedback(),
                    depth_sensors={k:depth_packet_metadata(v) for k,v in self.rgb_snapshot.get("depth",{}).items()},
                    camera_calibration=deepcopy(self.rgb_snapshot.get('camera_calibration', {})),
                    observation_tick=self.rgb_snapshot.get('observation_tick'))
