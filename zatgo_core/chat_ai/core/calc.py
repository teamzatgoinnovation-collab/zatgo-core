"""Safe arithmetic evaluator: the model delegates maths here instead of guessing."""

from __future__ import annotations

import ast
import math
import operator
import re

MAX_LEN = 500
MAX_ABS_EXP = 1000
# Integer results stay below ~4200 digits: beyond that json.dumps() refuses to serialise them, and
# stacked powers like ((10**1000)**1000)**1000 would otherwise burn CPU and memory before failing.
MAX_INT_BITS = 14000
_THOUSANDS = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?![\d,])")
_BIN = {
	ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
	ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
	"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max, "floor": math.floor,
	"ceil": math.ceil, "log": math.log, "log10": math.log10, "exp": math.exp, "sin": math.sin,
	"cos": math.cos, "tan": math.tan, "sum": lambda *a: sum(a),
}
_CONSTS = {"pi": math.pi, "e": math.e}


class CalcError(ValueError):
	pass


def _eval(node):
	if isinstance(node, ast.Expression):
		return _eval(node.body)
	if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
		return node.value
	if isinstance(node, ast.Name) and node.id in _CONSTS:
		return _CONSTS[node.id]
	if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
		return _UN[type(node.op)](_eval(node.operand))
	if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
		a, b = _eval(node.left), _eval(node.right)
		if isinstance(node.op, ast.Pow):
			if abs(b) > MAX_ABS_EXP:
				raise CalcError("Exponent too large")
			if isinstance(a, int) and isinstance(b, int) and abs(a).bit_length() * abs(b) > MAX_INT_BITS:
				raise CalcError("Result too large")
		result = _BIN[type(node.op)](a, b)
		if isinstance(result, int) and result.bit_length() > MAX_INT_BITS:
			raise CalcError("Result too large")
		return result
	if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
		return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
	raise CalcError("Unsupported expression")


def calculate(expression: str) -> dict:
	# "1,234.5 * 2" is a number with a thousands separator; commas that separate function
	# arguments ("max(3, 9)", "round(x, 2)") must survive.
	expr = _THOUSANDS.sub(lambda m: m.group().replace(",", ""), (expression or "").strip().replace("^", "**"))
	if not expr or len(expr) > MAX_LEN:
		raise CalcError("Provide an arithmetic expression (max 500 characters)")
	try:
		value = _eval(ast.parse(expr, mode="eval"))
	except CalcError:
		raise
	except ZeroDivisionError as exc:
		raise CalcError("Division by zero") from exc
	except (SyntaxError, ValueError, TypeError, OverflowError, RecursionError, MemoryError) as exc:
		raise CalcError("Could not evaluate the expression") from exc
	if isinstance(value, float):
		if not math.isfinite(value):
			raise CalcError("Result is not a finite number")
		value = float(f"{value:.12g}")
	return {"expression": expression, "value": value}
