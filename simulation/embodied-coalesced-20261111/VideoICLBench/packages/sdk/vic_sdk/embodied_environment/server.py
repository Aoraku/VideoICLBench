"""Authenticated local transport; Isaac operations stay on the main thread."""
from concurrent.futures import Future
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import queue
import threading
from urllib.parse import urlsplit

from .episode import PublicError


def serve(episode, *, port, agent_token, admin_token, frontend, ready=None, silhouette_provider=None):
    if not agent_token or not admin_token or hmac.compare_digest(agent_token, admin_token):
        raise ValueError('Distinct operation and administrator tokens are required')
    frontend = Path(frontend).resolve()
    # The former RGB estimators are retired. Keep the unused keyword for old
    # Python callers only; neither it nor legacy environment variables can
    # instantiate a worker or trigger a fallback.
    jobs = queue.Queue()
    stopped = threading.Event()
    # Admission is separate from the serialized environment owner. Otherwise a
    # terminal request received during a long action would silently wait in the
    # queue and stop the episode as soon as the action finished. Private owner
    # barriers deliberately keep their queue semantics for reconciliation.
    actor_admission = threading.Lock()
    actor_pending = False
    actor_operations = {'/api/observe', '/api/action', '/api/done', '/api/giveup',
                        '/api/finish', '/api/report-inferred-rule', '/api/measure-point',
                        '/api/depth-point', '/api/depth-map'}

    def dispatch(method, path, body, admin):
        if (method == 'POST' and path in {'/api/finish', '/api/done', '/api/giveup'}
                and episode.budget_policy == 'effective_time_graceful_v1'):
            # This is the native observation revision displayed by app.js,
            # not the MCP browser's separate screenshot token. Private drain
            # and seal intentionally use the owner barrier instead.
            if (episode.frame_id is None or not isinstance(body.get('frame_id'), str)
                    or body['frame_id'] != episode.frame_id):
                raise PublicError('stale_frame', 'Observe the current environment before deciding to stop.')
        if path.startswith('/api/private/'):
            if not admin:
                raise PublicError('forbidden', 'Administrator authorization is required.', 403)
            if method == 'GET' and path == '/api/private/state':
                return episode.private_state()
            if method == 'POST':
                from dataclasses import asdict
                expected = asdict(episode.identity)
                supplied = body.get('identity')
                if not isinstance(supplied, dict) or set(supplied) != set(expected) or any(
                    type(supplied[k]) is not type(v) or supplied[k] != v for k, v in expected.items()):
                    raise PublicError('identity_mismatch', 'The controller run identity does not match.', 409)
            if method == 'POST' and path == '/api/private/start':
                return episode.start(body.get('started_monotonic'))
            if method == 'POST' and path == '/api/private/recovery/begin':
                return episode.begin_recovery(body.get('recovery_id'))
            if method == 'POST' and path == '/api/private/recovery/end':
                return episode.end_recovery(body.get('recovery_id'))
            if method == 'POST' and path == '/api/private/evaluate':
                return episode.evaluate()
            if method == 'POST' and path == '/api/private/seal':
                return episode.finish(body.get('summary', 'Controller sealed the run.'),
                                      reason='controller_' + str(body.get('reason', 'seal'))[:100])
            if method == 'POST' and path == '/api/private/close':
                # Preserve legacy wall-time/single-environment close semantics.
                # Shared wait-policy rooms must retire before their owner exits.
                retirement = episode.abandon() if episode.budget_policy == 'effective_time_graceful_v1' else {}
                return dict(closed=True, **retirement)
        elif method == 'GET' and path == '/api/state':
            return episode.state()
        elif method == 'POST' and path == '/api/actor-activity':
            if body:
                raise PublicError('invalid_request', 'Activity metering accepts no action fields.', 400)
            episode.actor_activity()
            return dict(recorded=True)
        elif method == 'GET' and path == '/api/observe':
            episode.actor_activity()
            return episode.observe()
        elif method == 'POST' and path in {'/api/depth-point', '/api/depth-map'}:
            if episode.status != 'running':
                raise PublicError('episode_closed', 'The episode no longer accepts sensor queries.', 410)
            dense = path == '/api/depth-map'
            required = {'frame_id', 'camera'} if dense else {'frame_id', 'camera', 'row', 'col'}
            if set(body) != required:
                raise PublicError('invalid_request', 'Supply only the displayed frame, camera and query pixel.', 400)
            if episode.frame_id is None or body['frame_id'] != episode.frame_id:
                raise PublicError('stale_frame', 'Query depth from the currently displayed observation.', 409)
            if (body['camera'] not in ('head', 'left_wrist', 'right_wrist') or
                    (not dense and any(type(body[k]) not in (int, float) or not math.isfinite(body[k])
                                       for k in ('row', 'col')))):
                raise PublicError('invalid_request', 'A camera and finite native-image pixel are required.', 400)
            snapshot = getattr(episode.runtime, 'sensor_depth_snapshot', None)
            if not callable(snapshot):
                return dict(valid=False, reason='sensor_depth_unavailable', frame_id=episode.frame_id,
                            measurement_source='simulator_depth', physical_action=False)
            from .sensor_depth_public import public_sensor_query
            result = public_sensor_query(snapshot(), frame_id=episode.frame_id,
                camera=body['camera'], row=body.get('row'), col=body.get('col'), dense=dense)
            episode.actor_activity()
            return result
        elif method == 'POST' and path == '/api/measure-point':
            raise PublicError('rgb_depth_retired',
                'RGB depth estimation is retired. Query the displayed simulator depth via /api/depth-point.', 410)
        elif method == 'POST' and path == '/api/action':
            if set(body) == {'frame_id', 'batch_id', 'actions'}:
                episode.actor_activity()
                return episode.action_batch(**body)
            required = {'frame_id', 'left', 'right', 'step_mm', 'rotation_deg'}
            if set(body) != required:
                raise PublicError('invalid_action', 'Supply exactly the documented action fields.', 400)
            episode.actor_activity()
            return episode.action(**body)
        elif method == 'POST' and path == '/api/report-inferred-rule':
            return episode.report_inferred_rule(body.get('rule'), body.get('evidence_seconds', []))
        elif method == 'POST' and path == '/api/finish':
            return episode.finish(body.get('summary', ''))
        elif method == 'POST' and path == '/api/done':
            return episode.terminal('done', body.get('summary', ''))
        elif method == 'POST' and path == '/api/giveup':
            return episode.terminal('give_up', body.get('reason', ''))
        raise PublicError('not_found', 'Unknown environment endpoint.', 404)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Tokens, task rules and query strings never enter access logs.

        def reply(self, value, status=200, mime='application/json'):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if mime == 'application/json' else value
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def dispatch_request(self):
            nonlocal actor_pending
            path = urlsplit(self.path).path
            if self.command == 'GET' and path in ('/', '/index.html', '/app.js', '/style.css', '/styles.css'):
                filename = 'index.html' if path == '/' else path[1:]
                file = frontend / filename
                if file.is_file():
                    mime = 'application/javascript' if file.suffix == '.js' else 'text/css' if file.suffix == '.css' else 'text/html; charset=utf-8'
                    return self.reply(file.read_bytes(), mime=mime)
            auth = self.headers.get('Authorization', '')
            admin = hmac.compare_digest(auth, 'Bearer ' + admin_token)
            if not admin and not hmac.compare_digest(auth, 'Bearer ' + agent_token):
                raise PublicError('unauthorized', 'Environment authorization is required.', 401)
            if self.command == 'GET' and path == '/demo.mp4':
                if episode.demo is None:
                    raise PublicError('video_disabled', 'No demonstration video is assigned.', 404)
                return self.reply(Path(episode.demo['path']).read_bytes(), mime='video/mp4')
            body = {}
            if self.command == 'POST':
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 <= length <= 65536:
                        raise ValueError('size')
                    def nonfinite(value):
                        raise ValueError('nonfinite')
                    body = json.loads(self.rfile.read(length) or b'{}', parse_constant=nonfinite)
                    if not isinstance(body, dict):
                        raise ValueError('object')
                except (ValueError, UnicodeDecodeError) as exc:
                    raise PublicError('invalid_request', 'A bounded JSON object is required.', 400) from exc
            guarded = path in actor_operations
            future = Future()
            with actor_admission:
                pending = guarded and actor_pending
                if not pending:
                    if guarded:
                        actor_pending = True
                    jobs.put((self.command, path, body, admin, future, guarded))
            if pending:
                return self.reply(dict(error='operation_pending', status='operation_pending',
                    accepted=False, queued=False,
                    message='An accepted operation is still running. Wait for its result, then observe before deciding.'),
                    status=409)
            result = future.result()
            if self.command == 'POST' and path == '/api/private/close':
                try:
                    return self.reply(result)
                finally:
                    stopped.set()
            return self.reply(result)

        def safe_request(self):
            try:
                self.dispatch_request()
            except PublicError as exc:
                self.reply(dict(error=exc.code, message=exc.message), status=exc.status)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.reply(dict(error='environment_error', message='The environment request could not complete.'), status=503)

        do_GET = safe_request
        do_POST = safe_request

    http = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    http.daemon_threads = True
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    if ready:
        ready(http.server_address[1])
    try:
        while not stopped.is_set():
            try:
                method, path, body, admin, future, guarded = jobs.get(timeout=.2)
            except queue.Empty:
                # The main thread reaches this only between serialized jobs,
                # never while a physical action/RPC is awaiting its receipt.
                if getattr(episode, 'budget_policy', None) == 'effective_time_graceful_v1':
                    try:
                        episode.expire_budget_if_due()
                        if (episode.output.parent / 'drain-request.private.json').exists():
                            if episode.started is None:
                                # A controller may stop between launching room
                                # agents. Remove unstarted rooms from the native
                                # barrier without starting their budget or
                                # treating cancellation as an evaluated trial.
                                if episode.status == 'running':
                                    episode._seal('cancelled', 'controller_drain_before_model_start')
                            else:
                                episode.finish('Controller requested drain', reason='controller_drain')
                    except PublicError:
                        # Native sealing failures already mark the episode
                        # faulted. Its next state read exposes that status.
                        pass
                continue
            try:
                result = dispatch(method, path, body, admin)
            except Exception as exc:
                if guarded:
                    with actor_admission:
                        actor_pending = False
                future.set_exception(exc)
            else:
                if guarded:
                    with actor_admission:
                        actor_pending = False
                future.set_result(result)
                if method == 'POST' and path == '/api/private/close':
                    # The daemon handler must finish writing before the owner exits.
                    stopped.wait()
    finally:
        http.shutdown()
        http.server_close()
