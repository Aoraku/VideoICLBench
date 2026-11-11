"""Bounded AST interpreter for one episode's GUI programs.

No Python eval/exec, imports, attributes, filesystem or network are exposed.
Callbacks are trusted bridges, not capabilities obtained by model-written code.
Blocking callback time consumes no AST operations. The caller owns wall time,
physical-action admission and atomic checkpoint storage.

Only JSON ``memory`` and submission receipts survive reconstruction. Functions
and other variables survive successive submissions in this runtime, but must be
redefined after reconstruction. A running/unknown persisted submission cannot be
resubmitted or silently resumed: the owner must reconcile it externally.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Callable, Mapping


class ProgramError(Exception):
    """A bounded-program or syntax error; earlier callbacks are not rolled back."""


class CallbackRejected(Exception):
    """Trusted bridge guarantees this callback was not accepted or executed."""


class CallbackPartial(Exception):
    """Trusted bridge knows work partly executed; observe anew before acting.

    This submission stops and must not be replayed. The bridge owns fresh-frame
    admission for future submissions; the runtime does not retry any callback.
    """


class CallbackUnknown(Exception):
    """Callback may have executed; external reconciliation is mandatory."""


class _Return(Exception):
    def __init__(self, value):
        self.value = value


@dataclass(frozen=True)
class _Function:
    node: ast.FunctionDef
    defaults: tuple


class EmbodiedProgramRuntime:
    """Synchronous interpreter; use one instance per episode and serialize calls.

    ``checkpoint(snapshot)`` must durably/atomically store the supplied detached
    JSON before returning. It is called before and after every callback and at
    submission boundaries. Alternatively ``checkpoint_delta(delta)`` receives
    only schema, episode_id, memory, submission_id, submission (current ledger
    row) and halted. These two persistence hooks are mutually exclusive. The
    delta hook must durably commit current row and memory/meta before returning;
    reconstruct the full ``snapshot`` from committed rows when reconnecting.
    An exception from either hook conservatively blocks further execution.
    ``snapshot`` is trusted host state, never model input.
    """

    SCHEMA = 'videoicl-gui-program-state-v1'
    _BUILTINS = frozenset({'print', 'len', 'range', 'abs', 'min', 'max', 'sum',
                           'round', 'int', 'float', 'str', 'bool', 'get'})
    _NODES = (ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.If, ast.For,
              ast.FunctionDef, ast.Return, ast.Break, ast.Continue, ast.Pass,
              ast.Constant, ast.Name, ast.List, ast.Tuple, ast.Dict,
              ast.Subscript, ast.Slice, ast.BinOp, ast.UnaryOp, ast.BoolOp,
              ast.Compare, ast.IfExp, ast.Call, ast.keyword, ast.arguments,
              ast.arg, ast.Load, ast.Store, ast.Add, ast.Sub, ast.Mult,
              ast.Div, ast.FloorDiv, ast.Mod, ast.USub, ast.UAdd, ast.Not,
              ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt,
              ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot)

    def __init__(self, episode_id: str, callbacks: Mapping[str, Callable], *,
                 checkpoint: Callable | None = None, snapshot: dict | None = None,
                 checkpoint_delta: Callable | None = None,
                 max_ops=10000, max_callbacks=8, max_source_bytes=16384,
                 max_memory_bytes=65536, max_stdout_bytes=4096,
                 max_value_bytes=65536, max_items=2048, max_depth=24,
                 max_submissions=4096):
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError('episode_id must be a nonempty string')
        self.episode_id = episode_id
        self.callbacks = dict(callbacks)
        for name, function in self.callbacks.items():
            if (not name.isidentifier() or name.startswith('_') or
                    name in self._BUILTINS or name == 'memory' or not callable(function)):
                raise ValueError('Invalid or reserved callback name')
        if checkpoint is not None and checkpoint_delta is not None:
            raise ValueError('checkpoint and checkpoint_delta are mutually exclusive')
        self.checkpoint = checkpoint
        self.checkpoint_delta = checkpoint_delta
        self.max_ops, self.max_callbacks = int(max_ops), int(max_callbacks)
        self.max_source_bytes = int(max_source_bytes)
        self.max_memory_bytes, self.max_stdout_bytes = int(max_memory_bytes), int(max_stdout_bytes)
        self.max_value_bytes, self.max_items = int(max_value_bytes), int(max_items)
        self.max_depth, self.max_submissions = int(max_depth), int(max_submissions)
        if min(self.max_ops, self.max_callbacks, self.max_source_bytes,
               self.max_memory_bytes, self.max_stdout_bytes, self.max_value_bytes,
               self.max_items, self.max_depth, self.max_submissions) < 1:
            raise ValueError('Limits must be positive')
        self.globals = {'memory': {}}
        self.ledger = {}
        self.halted = False
        self._busy = False
        if snapshot is not None:
            if snapshot.get('schema') != self.SCHEMA or snapshot.get('episode_id') != episode_id:
                raise ValueError('Snapshot episode/schema mismatch')
            memory = self._json(snapshot.get('memory', {}), self.max_memory_bytes)
            if not isinstance(memory, dict):
                raise ValueError('Snapshot memory must be a dict')
            self.globals['memory'] = memory
            self.ledger = copy.deepcopy(snapshot.get('submissions', {}))
            if not isinstance(self.ledger, dict) or len(self.ledger) > self.max_submissions:
                raise ValueError('Invalid submission ledger')
            self.halted = bool(snapshot.get('halted'))
            for row in self.ledger.values():
                if row.get('status') in {'running', 'unknown'}:
                    self.halted = True
                    row['status'] = 'unknown'
        self._ops = 0
        self._depth = 0
        self._stdout = ''
        self._stdout_truncated = False
        self._calls = []
        self._record = None
        self._submission_id = None

    def _json(self, value, limit=None):
        byte_limit = limit if limit is not None else self.max_value_bytes
        nodes, text_bytes = 0, 0
        def check(v, depth=0):
            nonlocal nodes, text_bytes
            nodes += 1
            if nodes > self.max_items * 4:
                raise ProgramError('Total value item limit exceeded')
            if type(v) is str:
                text_bytes += len(v.encode())
                if text_bytes > byte_limit:
                    raise ProgramError('JSON byte limit exceeded')
            if depth > self.max_depth:
                raise ProgramError('Value nesting limit exceeded')
            if v is None or type(v) in (bool, str):
                return
            if type(v) is int:
                if v.bit_length() > 256:
                    raise ProgramError('Integer size limit exceeded')
                return
            if type(v) is float:
                if not math.isfinite(v):
                    raise ProgramError('Non-finite numbers are forbidden')
                return
            if type(v) in (list, tuple, dict):
                if len(v) > self.max_items:
                    raise ProgramError('Container item limit exceeded')
                if isinstance(v, dict):
                    if any(type(k) is not str for k in v):
                        raise ProgramError('Dictionary keys must be strings')
                    for key in v:
                        check(key, depth + 1)
                    children = v.values()
                else:
                    children = v
                for child in children:
                    check(child, depth + 1)
                return
            raise ProgramError('Only JSON values may cross the program boundary')
        try:
            check(value)
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        except (RecursionError, ValueError, TypeError) as exc:
            raise ProgramError('Value is not bounded JSON') from exc
        if len(encoded.encode()) > (limit if limit is not None else self.max_value_bytes):
            raise ProgramError('JSON byte limit exceeded')
        return json.loads(encoded)

    def snapshot(self):
        return {'schema': self.SCHEMA, 'episode_id': self.episode_id,
                'memory': self._json(self.globals['memory'], self.max_memory_bytes),
                'submissions': copy.deepcopy(self.ledger), 'halted': self.halted}

    def _save(self):
        if self.checkpoint is None and self.checkpoint_delta is None:
            return
        try:
            if self.checkpoint_delta is not None:
                self.checkpoint_delta({
                    'schema': self.SCHEMA,
                    'episode_id': self.episode_id,
                    'memory': self._json(self.globals['memory'], self.max_memory_bytes),
                    'submission_id': self._submission_id,
                    'submission': copy.deepcopy(self._record),
                    'halted': self.halted,
                })
            else:
                self.checkpoint(self.snapshot())
        except BaseException as exc:
            self.halted = True
            if self._record is not None:
                self._record['status'] = 'unknown'
            raise CallbackUnknown('Checkpoint failed; do not replay this submission') from exc

    def _tick(self):
        self._ops += 1
        if self._ops > self.max_ops:
            raise ProgramError('Computation operation budget exhausted')

    def _validate(self, tree):
        nodes = list(ast.walk(tree))
        if len(nodes) > 4096:
            raise ProgramError('AST size limit exceeded')
        for node in nodes:
            if not isinstance(node, self._NODES):
                raise ProgramError(f'Unsupported syntax: {type(node).__name__}')
            if isinstance(node, (ast.Name, ast.arg)):
                name = node.id if isinstance(node, ast.Name) else node.arg
                if name.startswith('_'):
                    raise ProgramError('Private names are forbidden')
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or any(k.arg is None for k in node.keywords):
                    raise ProgramError('Only named calls without argument unpacking are allowed')
                keys = [k.arg for k in node.keywords]
                if len(keys) != len(set(keys)):
                    raise ProgramError('Duplicate keyword arguments')
            if isinstance(node, ast.FunctionDef):
                args = node.args
                if node.decorator_list or node.returns or args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs:
                    raise ProgramError('Decorators, annotations and variadic arguments are forbidden')
                if len({arg.arg for arg in args.args}) != len(args.args):
                    raise ProgramError('Duplicate function parameters')
                self._assignable(node.name)
                if node.name == 'memory':
                    raise ProgramError('memory is reserved')
                for arg in args.args:
                    self._assignable(arg.arg)
                    if arg.arg == 'memory':
                        raise ProgramError('memory is reserved')
                    if arg.annotation:
                        raise ProgramError('Annotations are forbidden')
            if isinstance(node, ast.For) and node.orelse:
                raise ProgramError('for/else is not supported')
            if isinstance(node, ast.Dict) and any(k is None for k in node.keys):
                raise ProgramError('Dictionary unpacking is forbidden')
        def contexts(statements, in_function=False, in_loop=False):
            for statement in statements:
                if isinstance(statement, ast.Return) and not in_function:
                    raise ProgramError('return requires a function')
                if isinstance(statement, (ast.Break, ast.Continue)) and not in_loop:
                    raise ProgramError('break/continue requires a loop in this function')
                if isinstance(statement, ast.FunctionDef):
                    contexts(statement.body, True, False)
                elif isinstance(statement, ast.For):
                    contexts(statement.body, in_function, True)
                elif isinstance(statement, ast.If):
                    contexts(statement.body, in_function, in_loop)
                    contexts(statement.orelse, in_function, in_loop)
        contexts(tree.body)

    def _assignable(self, name):
        if name.startswith('_') or name in self.callbacks or name in self._BUILTINS:
            raise ProgramError('Cannot overwrite a protected name')

    def execute(self, source: str, submission_id: str):
        if not isinstance(submission_id, str) or not submission_id or len(submission_id) > 200:
            raise ValueError('submission_id must be a nonempty bounded string')
        if not isinstance(source, str):
            raise ValueError('source must be text')
        digest = hashlib.sha256(source.encode()).hexdigest()
        previous = self.ledger.get(submission_id)
        if previous is not None:
            if previous.get('source_sha256') != digest:
                raise ProgramError('Submission identity already belongs to different code')
            if previous.get('status') in {'running', 'unknown'} or 'receipt' not in previous:
                raise CallbackUnknown('Submission outcome is unknown; do not replay it')
            return copy.deepcopy(previous['receipt'])
        if self._busy:
            raise ProgramError('A submission is already executing')
        if self.halted:
            raise CallbackUnknown('Runtime awaits external reconciliation')
        if len(self.ledger) >= self.max_submissions:
            raise ProgramError('Submission ledger is full')
        self._busy = True
        self._ops = self._depth = 0
        self._stdout, self._stdout_truncated, self._calls = '', False, []
        row = {'source_sha256': digest, 'status': 'running', 'callback_calls': self._calls}
        self.ledger[submission_id] = row
        self._record = row
        self._submission_id = submission_id
        value, error, status = None, None, 'completed'
        try:
            if len(source.encode()) > self.max_source_bytes:
                raise ProgramError('Source byte limit exceeded')
            tree = ast.parse(source, mode='exec')
            self._validate(tree)
            self._save()
            value = self._block(tree.body, self.globals)
            value = self._json(value)
            self._json(self.globals['memory'], self.max_memory_bytes)
        except CallbackUnknown as exc:
            self.halted, status, error = True, 'unknown', str(exc)
        except (Exception, _Return) as exc:
            status = ('partial' if isinstance(exc, CallbackPartial) else
                      'rejected' if isinstance(exc, CallbackRejected) else 'error')
            error = f'{type(exc).__name__}: {exc}'[:1024]
        # Every mutation into memory is validated before commit, so errors retain
        # the last valid memory and the physical actions that already happened.
        receipt = {'ok': status == 'completed', 'status': status,
                   'submission_id': submission_id, 'stdout': self._stdout,
                   'stdout_truncated': self._stdout_truncated, 'result': value if status == 'completed' else None,
                   'memory': self._json(self.globals['memory'], self.max_memory_bytes),
                   'callback_calls': copy.deepcopy(self._calls), 'operations': self._ops,
                   'error': error}
        row.update(status=status, receipt=receipt)
        try:
            self._save()
        except CallbackUnknown as exc:
            receipt.update(ok=False, status='unknown', error=str(exc))
            row.update(status='unknown', receipt=receipt)
        finally:
            self._record, self._submission_id, self._busy = None, None, False
        return copy.deepcopy(receipt)

    def _block(self, nodes, env):
        value = None
        for node in nodes:
            self._tick()
            if isinstance(node, ast.Expr):
                value = self._expr(node.value, env)
            elif isinstance(node, ast.Assign):
                result = self._expr(node.value, env)
                for target in node.targets:
                    self._set(target, result, env)
            elif isinstance(node, ast.AugAssign):
                result = self._binary(node.op, self._expr(node.target, env), self._expr(node.value, env))
                self._set(node.target, result, env)
            elif isinstance(node, ast.If):
                self._block(node.body if self._expr(node.test, env) else node.orelse, env)
            elif isinstance(node, ast.For):
                values = self._expr(node.iter, env)
                if not isinstance(values, (list, tuple, range, dict)) or len(values) > self.max_items:
                    raise ProgramError('for requires a bounded sequence')
                for item in list(values):
                    self._tick()
                    self._set(node.target, item, env)
                    try:
                        self._block(node.body, env)
                    except _Continue:
                        continue
                    except _Break:
                        break
            elif isinstance(node, ast.FunctionDef):
                env[node.name] = _Function(node, tuple(self._expr(v, env) for v in node.args.defaults))
            elif isinstance(node, ast.Return):
                raise _Return(self._expr(node.value, env) if node.value else None)
            elif isinstance(node, ast.Break):
                raise _Break()
            elif isinstance(node, ast.Continue):
                raise _Continue()
            elif not isinstance(node, ast.Pass):
                raise ProgramError('Unsupported statement')
        return value

    def _set(self, node, value, env):
        if isinstance(node, ast.Name):
            self._assignable(node.id)
            if node.id == 'memory':
                if env is not self.globals or not isinstance(value, dict):
                    raise ProgramError('memory must remain the global JSON dictionary')
                value = self._json(value, self.max_memory_bytes)
            elif not isinstance(value, (_Function, range)):
                self._json(value)
            env[node.id] = value
            return
        if isinstance(node, (ast.Tuple, ast.List)):
            if not isinstance(value, (list, tuple)) or len(value) != len(node.elts):
                raise ProgramError('Unpacking length mismatch')
            for target, item in zip(node.elts, value):
                self._set(target, item, env)
            return
        if isinstance(node, ast.Subscript):
            container, key = self._expr(node.value, env), self._expr(node.slice, env)
            if type(container) not in (list, dict):
                raise ProgramError('Only list/dict items may be assigned')
            before = copy.deepcopy(container)
            try:
                container[key] = copy.deepcopy(self._json(value))
                self._json(container)
                self._json(self.globals['memory'], self.max_memory_bytes)
            except Exception:
                if isinstance(container, dict):
                    container.clear(); container.update(before)
                else:
                    container[:] = before
                raise
            return
        raise ProgramError('Unsupported assignment target')

    def _expr(self, node, env):
        self._tick()
        self._depth += 1
        try:
            if self._depth > self.max_depth:
                raise ProgramError('Expression/call depth limit exceeded')
            return self._expression(node, env)
        finally:
            self._depth -= 1

    def _expression(self, node, env):
        if isinstance(node, ast.Constant):
            return self._json(node.value)
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            if node.id in self.globals:
                return self.globals[node.id]
            raise ProgramError(f'Unknown variable: {node.id}')
        if isinstance(node, (ast.List, ast.Tuple)):
            value = [self._expr(v, env) for v in node.elts]
            self._json(value)
            return value
        if isinstance(node, ast.Dict):
            value = {self._expr(k, env): self._expr(v, env) for k, v in zip(node.keys, node.values)}
            self._json(value)
            return value
        if isinstance(node, ast.Subscript):
            obj, key = self._expr(node.value, env), self._expr(node.slice, env)
            if not isinstance(obj, (dict, list, tuple, str, range)):
                raise ProgramError('Value is not subscriptable')
            return obj[key]
        if isinstance(node, ast.Slice):
            return slice(*(self._expr(v, env) if v is not None else None for v in (node.lower, node.upper, node.step)))
        if isinstance(node, ast.BinOp):
            return self._binary(node.op, self._expr(node.left, env), self._expr(node.right, env))
        if isinstance(node, ast.UnaryOp):
            value = self._expr(node.operand, env)
            if isinstance(node.op, ast.Not):
                return not value
            if type(value) not in (int, float):
                raise ProgramError('Unary arithmetic requires a number')
            return self._json(-value if isinstance(node.op, ast.USub) else +value)
        if isinstance(node, ast.BoolOp):
            result = self._expr(node.values[0], env)
            for item in node.values[1:]:
                if (isinstance(node.op, ast.And) and not result) or (isinstance(node.op, ast.Or) and result):
                    break
                result = self._expr(item, env)
            return result
        if isinstance(node, ast.Compare):
            left = self._expr(node.left, env)
            for op, term in zip(node.ops, node.comparators):
                right = self._expr(term, env)
                result = {ast.Eq: lambda: left == right, ast.NotEq: lambda: left != right,
                          ast.Lt: lambda: left < right, ast.LtE: lambda: left <= right,
                          ast.Gt: lambda: left > right, ast.GtE: lambda: left >= right,
                          ast.In: lambda: left in right, ast.NotIn: lambda: left not in right,
                          ast.Is: lambda: left is right, ast.IsNot: lambda: left is not right}[type(op)]()
                if not result:
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return self._expr(node.body if self._expr(node.test, env) else node.orelse, env)
        if isinstance(node, ast.Call):
            args = [self._expr(v, env) for v in node.args]
            kwargs = {k.arg: self._expr(k.value, env) for k in node.keywords}
            name = node.func.id
            if name in self.callbacks:
                return self._callback(name, args, kwargs)
            if name in self._BUILTINS:
                return self._builtin(name, args, kwargs)
            fn = env.get(name, self.globals.get(name))
            if not isinstance(fn, _Function):
                raise ProgramError('Only declared functions or whitelisted calls are allowed')
            names = [a.arg for a in fn.node.args.args]
            if len(args) > len(names) or set(kwargs) - set(names) or set(names[:len(args)]) & set(kwargs):
                raise ProgramError('Invalid function arguments')
            local = dict(zip(names[len(names) - len(fn.defaults):], copy.deepcopy(fn.defaults))) if fn.defaults else {}
            local.update(zip(names, args));local.update(kwargs)
            if set(local) != set(names):
                raise ProgramError('Missing function argument')
            try:
                self._block(fn.node.body, local)
            except _Return as result:
                return result.value
            return None
        raise ProgramError('Unsupported expression')

    def _binary(self, op, left, right):
        if isinstance(op, ast.Mult):
            seq, number = (left, right) if isinstance(left, (str, list, tuple)) else (right, left)
            if isinstance(seq, (str, list, tuple)):
                if type(number) is not int or len(seq) * max(0, number) > min(self.max_items, self.max_value_bytes):
                    raise ProgramError('Sequence multiplication limit exceeded')
        if not isinstance(op, (ast.Add, ast.Mult)) and (
                type(left) not in (int, float) or type(right) not in (int, float)):
            raise ProgramError('Arithmetic requires numbers; string formatting is unsupported')
        result = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right,
                  ast.Mult: lambda: left * right, ast.Div: lambda: left / right,
                  ast.FloorDiv: lambda: left // right, ast.Mod: lambda: left % right}[type(op)]()
        return self._json(result)

    def _builtin(self, name, args, kwargs):
        if name == 'print':
            if set(kwargs) - {'sep', 'end'}:
                raise ProgramError('Unsupported print option')
            sep, end = kwargs.get('sep', ' '), kwargs.get('end', '\n')
            if type(sep) is not str or type(end) is not str:
                raise ProgramError('print separator/end must be strings')
            self._json(args)
            # Append bounded pieces so a huge separator never creates a huge
            # joined temporary string before truncation.
            for index in range(len(args) * 2 + 1):
                if index == len(args) * 2:
                    piece = end
                elif index % 2:
                    piece = sep if index < len(args) * 2 - 1 else ''
                else:
                    piece = str(args[index // 2])
                remaining = self.max_stdout_bytes - len(self._stdout.encode())
                encoded = piece.encode()
                self._stdout += encoded[:max(0, remaining)].decode('utf-8', errors='ignore')
                self._stdout_truncated |= len(encoded) > remaining
            return None
        if kwargs:
            raise ProgramError('Builtin keyword arguments are unsupported')
        if name == 'range':
            if not 1 <= len(args) <= 3 or any(type(v) is not int for v in args):
                raise ProgramError('range requires one to three integers')
            values = range(*args)
            if len(values) > self.max_items:
                raise ProgramError('range limit exceeded')
            return values
        if name == 'get':
            if not 2 <= len(args) <= 3 or not isinstance(args[0], dict):
                raise ProgramError('get requires dictionary, key, optional default')
            return args[0].get(*args[1:])
        if name in {'min', 'max', 'sum'}:
            # Materialize only bounded range operands; all other values have
            # already passed AST value limits.
            args = [list(v) if isinstance(v, range) else v for v in args]
        functions = {'len': len, 'abs': abs, 'min': min, 'max': max, 'sum': sum,
                     'round': round, 'int': int, 'float': float, 'str': str, 'bool': bool}
        for value in args:
            if not isinstance(value, range):
                self._json(value)
        return self._json(functions[name](*args))

    def _callback(self, name, args, kwargs):
        if len(self._calls) >= self.max_callbacks:
            raise ProgramError('Callback budget exhausted')
        args, kwargs = self._json(args), self._json(kwargs)
        row = {'name': name, 'args': args, 'kwargs': kwargs, 'status': 'pending'}
        self._calls.append(row)
        self._save()  # Durable intent before potentially physical work.
        try:
            result = self.callbacks[name](*copy.deepcopy(args), **copy.deepcopy(kwargs))
            result = self._json(result)
        except (CallbackRejected, CallbackPartial) as exc:
            row.update(status='partial' if isinstance(exc, CallbackPartial) else 'rejected',
                       error=str(exc)[:1024])
            self._save()
            raise
        except BaseException as exc:
            row.update(status='unknown', error=f'{type(exc).__name__}: {exc}'[:1024])
            self.halted = True
            self._save()
            raise CallbackUnknown('Callback outcome unknown; do not replay this submission') from exc
        row.update(status='completed', result=copy.deepcopy(result))
        self._save()
        return result


class _Break(Exception):
    pass


class _Continue(Exception):
    pass
