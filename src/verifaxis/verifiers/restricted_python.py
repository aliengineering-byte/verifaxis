"""Pure-function tests using a bounded AST interpreter, never ``exec``/``eval``."""

from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from ..types import (
    Candidate,
    EvidencePacket,
    EvidenceStatus,
    IndependenceClassification,
    JSONValue,
)


@dataclass(frozen=True, slots=True)
class PythonTestCase:
    """One JSON-like pure-function test case."""

    args: tuple[JSONValue, ...] = ()
    kwargs: dict[str, JSONValue] = field(default_factory=dict)
    expected: JSONValue = None


class _ReturnSignal(Exception):
    def __init__(self, value: object) -> None:
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


_BINARY: dict[type[ast.operator], object] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_COMPARE: dict[type[ast.cmpop], object] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}
_SAFE_CALLS = {
    "abs",
    "all",
    "any",
    "enumerate",
    "len",
    "max",
    "min",
    "range",
    "sorted",
    "sum",
    "zip",
}
_CODE_FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

_MAX_INTEGER_BITS = 4_096
_MAX_STRING_LENGTH = 100_000
_MAX_CONTAINER_LENGTH = 10_000
_MAX_TOTAL_ITEMS = 20_000
_MAX_NESTING_DEPTH = 64
_MAX_ITERATIONS = 1_000
_MAX_EXPONENT = 100


def _json_value(
    value: object,
    *,
    _depth: int = 0,
    _remaining: list[int] | None = None,
) -> JSONValue:
    if _depth > _MAX_NESTING_DEPTH:
        raise ValueError("JSON-like value exceeds the nesting limit")
    if _remaining is None:
        _remaining = [_MAX_TOTAL_ITEMS]
    if value is None or isinstance(value, str | int | float | bool):
        if isinstance(value, int) and value.bit_length() > _MAX_INTEGER_BITS:
            raise ValueError("integer exceeds the interpreter size limit")
        if isinstance(value, str) and len(value) > _MAX_STRING_LENGTH:
            raise ValueError("string exceeds the interpreter size limit")
        if isinstance(value, float) and not math.isfinite(value):
            return repr(value)
        return value
    if isinstance(value, tuple | list):
        if len(value) > _MAX_CONTAINER_LENGTH:
            raise ValueError("container exceeds the interpreter size limit")
        _remaining[0] -= len(value)
        if _remaining[0] < 0:
            raise ValueError("value graph exceeds the interpreter item limit")
        return [_json_value(item, _depth=_depth + 1, _remaining=_remaining) for item in value]
    if isinstance(value, dict):
        if len(value) > _MAX_CONTAINER_LENGTH:
            raise ValueError("container exceeds the interpreter size limit")
        _remaining[0] -= len(value)
        if _remaining[0] < 0:
            raise ValueError("value graph exceeds the interpreter item limit")
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str | int | float | bool | None):
                raise TypeError("mapping keys must be JSON-like primitives")
            normalized_key = str(key)
            if len(normalized_key) > _MAX_STRING_LENGTH:
                raise ValueError("mapping key exceeds the interpreter size limit")
            result[normalized_key] = _json_value(item, _depth=_depth + 1, _remaining=_remaining)
        return result
    raise TypeError(f"unsupported non-JSON value: {type(value).__name__}")


class _Interpreter:
    def __init__(self, function: ast.FunctionDef, *, step_limit: int = 10_000) -> None:
        self.function = function
        self.step_limit = step_limit
        self.steps = 0

    def _tick(self) -> None:
        self.steps += 1
        if self.steps > self.step_limit:
            raise ValueError("interpreter step limit exceeded")

    @staticmethod
    def _bounded(
        value: object,
        *,
        _depth: int = 0,
        _remaining: list[int] | None = None,
    ) -> object:
        if _depth > _MAX_NESTING_DEPTH:
            raise ValueError("value exceeds the interpreter nesting limit")
        if _remaining is None:
            _remaining = [_MAX_TOTAL_ITEMS]
        if isinstance(value, int) and value.bit_length() > _MAX_INTEGER_BITS:
            raise ValueError("integer exceeds the interpreter size limit")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite float is not supported")
        if isinstance(value, str) and len(value) > _MAX_STRING_LENGTH:
            raise ValueError("string exceeds the interpreter size limit")
        if isinstance(value, list | tuple | dict):
            if len(value) > _MAX_CONTAINER_LENGTH:
                raise ValueError("container exceeds the interpreter size limit")
            _remaining[0] -= len(value)
            if _remaining[0] < 0:
                raise ValueError("value graph exceeds the interpreter item limit")
            children = (
                (child for item in value.items() for child in item)
                if isinstance(value, dict)
                else value
            )
            for child in children:
                _Interpreter._bounded(child, _depth=_depth + 1, _remaining=_remaining)
        elif not isinstance(value, range | slice | str | int | float | bool | None):
            raise ValueError(f"unsupported runtime value: {type(value).__name__}")
        return value

    def _apply_binary(self, operation_node: ast.operator, left: object, right: object) -> object:
        """Apply every binary operation through one preflight/postflight boundary."""

        self._bounded(left)
        self._bounded(right)
        if isinstance(operation_node, ast.Pow):
            if not isinstance(right, int | float):
                raise ValueError("exponent must be numeric")
            if abs(right) > _MAX_EXPONENT:
                raise ValueError("exponent exceeds safety limit")
            if (
                isinstance(left, int)
                and isinstance(right, int)
                and right >= 0
                and abs(left) > 1
                and left.bit_length() * right > _MAX_INTEGER_BITS
            ):
                raise ValueError("power result exceeds the integer size limit")
        if isinstance(operation_node, ast.Mult):
            sequence, multiplier = left, right
            if isinstance(right, str | list | tuple) and isinstance(left, int):
                sequence, multiplier = right, left
            if isinstance(sequence, str | list | tuple) and isinstance(multiplier, int):
                predicted = len(sequence) * max(multiplier, 0)
                limit = _MAX_STRING_LENGTH if isinstance(sequence, str) else _MAX_CONTAINER_LENGTH
                if predicted > limit:
                    raise ValueError("sequence multiplication exceeds the size limit")
            if isinstance(left, int) and isinstance(right, int) and left and right:
                minimum_bits = left.bit_length() + right.bit_length() - 1
                if minimum_bits > _MAX_INTEGER_BITS:
                    raise ValueError("integer multiplication exceeds the size limit")
        if (
            isinstance(operation_node, ast.Add)
            and isinstance(left, str | list | tuple)
            and isinstance(right, type(left))
        ):
            limit = _MAX_STRING_LENGTH if isinstance(left, str) else _MAX_CONTAINER_LENGTH
            if len(left) + len(right) > limit:
                raise ValueError("sequence addition exceeds the size limit")
        if isinstance(operation_node, ast.Mod) and isinstance(left, str):
            raise ValueError("string formatting is not supported")
        operation = _BINARY[type(operation_node)]
        return self._bounded(operation(left, right))  # type: ignore[operator]

    def call(self, args: tuple[JSONValue, ...], kwargs: Mapping[str, JSONValue]) -> object:
        self.steps = 0
        parameters = [argument.arg for argument in self.function.args.args]
        if self.function.args.vararg or self.function.args.kwarg or self.function.args.kwonlyargs:
            raise ValueError("variadic and keyword-only parameters are not supported")
        if len(args) + len(kwargs) != len(parameters):
            raise TypeError("test arguments do not match function parameters")
        environment: dict[str, object] = {
            key: self._bounded(value) for key, value in zip(parameters, args, strict=False)
        }
        for key, value in kwargs.items():
            if key not in parameters or key in environment:
                raise TypeError("test arguments do not match function parameters")
            environment[key] = self._bounded(value)
        if set(environment) != set(parameters):
            raise TypeError("test arguments do not match function parameters")
        try:
            self._statements(self.function.body, environment)
        except _ReturnSignal as signal:
            return signal.value
        return None

    def _statements(self, statements: Sequence[ast.stmt], environment: dict[str, object]) -> None:
        for statement in statements:
            self._statement(statement, environment)

    def _statement(self, node: ast.stmt, environment: dict[str, object]) -> None:
        self._tick()
        if isinstance(node, ast.Return):
            raise _ReturnSignal(
                None if node.value is None else self._expression(node.value, environment)
            )
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            self._assign(node.targets[0], self._expression(node.value, environment), environment)
            return
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            self._assign(node.target, self._expression(node.value, environment), environment)
            return
        if isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name) or type(node.op) not in _BINARY:
                raise ValueError("unsupported augmented assignment")
            current = self._name(node.target.id, environment)
            environment[node.target.id] = self._apply_binary(
                node.op, current, self._expression(node.value, environment)
            )
            return
        if isinstance(node, ast.If):
            branch = node.body if self._expression(node.test, environment) else node.orelse
            self._statements(branch, environment)
            return
        if isinstance(node, ast.For):
            values = self._expression(node.iter, environment)
            if not isinstance(values, range | list | tuple | str):
                raise ValueError("for-loop iterable is not bounded")
            if len(values) > _MAX_ITERATIONS:
                raise ValueError("for-loop exceeds 1,000 iterations")
            for value in values:
                self._assign(node.target, value, environment)
                try:
                    self._statements(node.body, environment)
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    break
            else:
                self._statements(node.orelse, environment)
            return
        if isinstance(node, ast.Break):
            raise _BreakSignal
        if isinstance(node, ast.Continue):
            raise _ContinueSignal
        if isinstance(node, ast.Pass):
            return
        raise ValueError(f"unsupported statement: {type(node).__name__}")

    def _assign(self, target: ast.expr, value: object, environment: dict[str, object]) -> None:
        if isinstance(target, ast.Name) and not target.id.startswith("__"):
            environment[target.id] = self._bounded(value)
            return
        if isinstance(target, ast.Tuple) and isinstance(value, tuple | list):
            if len(target.elts) != len(value):
                raise ValueError("unpacking lengths differ")
            for child, item in zip(target.elts, value, strict=True):
                self._assign(child, item, environment)
            return
        raise ValueError("only local-name assignment is supported")

    @staticmethod
    def _name(name: str, environment: Mapping[str, object]) -> object:
        if name.startswith("__") or name not in environment:
            raise ValueError(f"unknown name: {name}")
        return environment[name]

    def _expression(self, node: ast.expr, environment: dict[str, object]) -> object:
        self._tick()
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, str | int | float | bool | None):
                raise ValueError("unsupported constant")
            return self._bounded(node.value)
        if isinstance(node, ast.Name):
            return self._name(node.id, environment)
        if isinstance(node, ast.List):
            return self._bounded([self._expression(item, environment) for item in node.elts])
        if isinstance(node, ast.Tuple):
            return self._bounded(tuple(self._expression(item, environment) for item in node.elts))
        if isinstance(node, ast.Dict):
            keys = [self._expression(key, environment) for key in node.keys if key is not None]
            values = [self._expression(item, environment) for item in node.values]
            return self._bounded(dict(zip(keys, values, strict=True)))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            left = self._expression(node.left, environment)
            right = self._expression(node.right, environment)
            return self._apply_binary(node.op, left, right)
        if isinstance(node, ast.UnaryOp):
            value = self._expression(node.operand, environment)
            if isinstance(node.op, ast.Not):
                return not value
            if isinstance(node.op, ast.USub):
                return self._bounded(-value)  # type: ignore[operator]
            if isinstance(node.op, ast.UAdd):
                return self._bounded(+value)  # type: ignore[operator]
            raise ValueError("unsupported unary operator")
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._expression(item, environment) for item in node.values)
            if isinstance(node.op, ast.Or):
                return any(self._expression(item, environment) for item in node.values)
        if isinstance(node, ast.Compare):
            left = self._expression(node.left, environment)
            for operation_node, comparator in zip(node.ops, node.comparators, strict=True):
                operation = _COMPARE.get(type(operation_node))
                right = self._expression(comparator, environment)
                if operation is None or not operation(left, right):  # type: ignore[operator]
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            branch = node.body if self._expression(node.test, environment) else node.orelse
            return self._expression(branch, environment)
        if isinstance(node, ast.Subscript):
            container = self._expression(node.value, environment)
            index = self._expression(node.slice, environment)
            return self._bounded(container[index])  # type: ignore[index]
        if isinstance(node, ast.Slice):
            lower = None if node.lower is None else self._expression(node.lower, environment)
            upper = None if node.upper is None else self._expression(node.upper, environment)
            step = None if node.step is None else self._expression(node.step, environment)
            return slice(lower, upper, step)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in _SAFE_CALLS or node.keywords:
                raise ValueError("only whitelisted pure calls are supported")
            args = [self._expression(argument, environment) for argument in node.args]
            if node.func.id == "range":
                int_args: list[int] = []
                for item in args:
                    if not isinstance(item, int):
                        raise ValueError("range requires one to three integer arguments")
                    int_args.append(item)
                if not 1 <= len(int_args) <= 3:
                    raise ValueError("range requires one to three integer arguments")
                value = range(*int_args)
                if len(value) > _MAX_ITERATIONS:
                    raise ValueError("range exceeds 1,000 elements")
                return value
            functions: dict[str, Callable[..., object]] = {
                "abs": abs,
                "all": all,
                "any": any,
                "enumerate": lambda value: list(enumerate(value)),
                "len": len,
                "max": max,
                "min": min,
                "sorted": sorted,
                "sum": sum,
                "zip": lambda *values: list(zip(*values, strict=False)),
            }
            if node.func.id in {"enumerate", "sorted"}:
                if len(args) != 1 or not hasattr(args[0], "__len__"):
                    raise ValueError(f"{node.func.id} requires one bounded iterable")
                if len(args[0]) > _MAX_CONTAINER_LENGTH:
                    raise ValueError(f"{node.func.id} output exceeds the size limit")
            if node.func.id == "zip":
                for value in args:
                    if not hasattr(value, "__len__"):
                        raise ValueError("zip requires bounded iterables")
                if args and min(len(value) for value in args) > _MAX_CONTAINER_LENGTH:  # type: ignore[arg-type]
                    raise ValueError("zip output exceeds the size limit")
            return self._bounded(functions[node.func.id](*args))
        raise ValueError(f"unsupported expression: {type(node).__name__}")


def _source_from_candidate(content: str) -> str:
    if len(content) > 50_000:
        raise ValueError("candidate source exceeds 50,000 characters")
    match = _CODE_FENCE.search(content)
    return (match.group(1) if match else content).strip()


def _normalize_case(value: object) -> PythonTestCase:
    if isinstance(value, PythonTestCase):
        return value
    if isinstance(value, Mapping):
        args_value = value.get("args", ())
        kwargs_value = value.get("kwargs", {})
        if not isinstance(args_value, Sequence) or isinstance(args_value, str | bytes):
            raise TypeError("test case args must be a sequence")
        if not isinstance(kwargs_value, Mapping):
            raise TypeError("test case kwargs must be a mapping")
        return PythonTestCase(
            args=tuple(_json_value(item) for item in args_value),
            kwargs={str(key): _json_value(item) for key, item in kwargs_value.items()},
            expected=_json_value(value.get("expected")),
        )
    if isinstance(value, tuple) and len(value) == 2:
        inputs, expected = value
        if isinstance(inputs, tuple | list):
            args = tuple(_json_value(item) for item in inputs)
            kwargs: dict[str, JSONValue] = {}
        elif isinstance(inputs, Mapping):
            args = ()
            kwargs = {str(key): _json_value(item) for key, item in inputs.items()}
        else:
            args = (_json_value(inputs),)
            kwargs = {}
        return PythonTestCase(args=args, kwargs=kwargs, expected=_json_value(expected))
    raise TypeError("test cases must be PythonTestCase, mapping, or (inputs, expected)")


class RestrictedPythonVerifier:
    """Interpret one pure function and check it against supplied deterministic cases."""

    verifier_type = "restricted_python_ast"
    verifier_version = "1.0"

    def __init__(
        self,
        test_cases: Sequence[object],
        *,
        function_name: str | None = None,
        step_limit: int = 10_000,
    ) -> None:
        if step_limit < 1:
            raise ValueError("step_limit must be positive")
        self.test_cases = tuple(_normalize_case(case) for case in test_cases)
        self.function_name = function_name
        self.step_limit = step_limit

    def _packet(
        self,
        status: EvidenceStatus,
        claim: str,
        counterexample: JSONValue = None,
    ) -> EvidencePacket:
        return EvidencePacket.create(
            verifier_type=self.verifier_type,
            verifier_version=self.verifier_version,
            status=status,
            checked_claim=claim,
            counterexample=counterexample,
            provenance={"method": "bounded-ast-interpreter", "test_count": len(self.test_cases)},
            independence=IndependenceClassification.INDEPENDENT,
            reliability={
                "deterministic": True,
                "exec_used": False,
                "step_limit": self.step_limit,
            },
            raw_artifact_ref="inline://restricted-python-tests",
            llm_produced=False,
        )

    def verify(self, *, task: str, candidate: Candidate) -> EvidencePacket:
        del task
        if not self.test_cases:
            return self._packet(
                EvidenceStatus.UNKNOWN,
                "candidate passes provided pure-function cases",
                {"error": "no test cases were provided"},
            )
        try:
            source = _source_from_candidate(candidate.content)
            tree = ast.parse(source, mode="exec")
            if sum(1 for _ in ast.walk(tree)) > 256:
                raise ValueError("candidate AST exceeds 256 nodes")
            if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
                raise ValueError("candidate must contain exactly one function definition")
            function = tree.body[0]
            if function.decorator_list:
                raise ValueError("decorators are not allowed")
            if self.function_name is not None and function.name != self.function_name:
                raise ValueError(f"expected function named {self.function_name!r}")
            forbidden = (
                ast.Attribute,
                ast.Import,
                ast.ImportFrom,
                ast.Global,
                ast.Nonlocal,
                ast.Lambda,
                ast.ClassDef,
                ast.While,
                ast.Try,
                ast.With,
                ast.Raise,
                ast.Delete,
                ast.Yield,
                ast.Await,
            )
            bad = next((node for node in ast.walk(function) if isinstance(node, forbidden)), None)
            if bad is not None:
                raise ValueError(f"forbidden syntax: {type(bad).__name__}")
            interpreter = _Interpreter(function, step_limit=self.step_limit)
        except (SyntaxError, TypeError, ValueError) as error:
            return self._packet(
                EvidenceStatus.FAIL,
                "candidate is a safe interpretable pure function",
                {"error": type(error).__name__, "message": str(error)[:200]},
            )

        claim = f"function {function.name!r} passes {len(self.test_cases)} provided cases"
        for index, case in enumerate(self.test_cases):
            try:
                observed = interpreter.call(case.args, case.kwargs)
                observed_json = _json_value(observed)
            except Exception as error:
                return self._packet(
                    EvidenceStatus.FAIL,
                    claim,
                    {
                        "case_index": index,
                        "args": list(case.args),
                        "kwargs": dict(case.kwargs),
                        "expected": case.expected,
                        "observed": None,
                        "error": type(error).__name__,
                        "message": str(error)[:200],
                    },
                )
            if observed_json != case.expected:
                return self._packet(
                    EvidenceStatus.FAIL,
                    claim,
                    {
                        "case_index": index,
                        "args": list(case.args),
                        "kwargs": dict(case.kwargs),
                        "expected": case.expected,
                        "observed": observed_json,
                    },
                )
        return self._packet(EvidenceStatus.PASS, claim)
