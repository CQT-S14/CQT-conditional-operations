---
layout: default
title: Conditional operations in Qibo
---

# Conditional operations in Qibo

A conditional circuit measures a qubit **while the circuit is running**, uses
that result to choose an operation, and then continues. The choice is made
separately on every shot. This guide uses the `CQT-qibo` conditional-operations
API with the NumPy simulator.

Use the `develop` branch of the `CQT-qibo` fork, where this API is available.

```text
Prepare qubits → measure → evaluate the result → run one branch → continue
```

## The vocabulary

| Term | Meaning |
| --- | --- |
| Mid-circuit measurement | `gates.M(..., collapse=True)` measures now, so later operations can depend on its result. |
| Measurement result | The object returned by `circuit.add(gates.M(...))`. While building a circuit, it refers to an outcome that will be known during execution. |
| Condition | A question about that result, such as `result.is_one()` or `syndrome.equals("10")`. |
| Branch body | The gate or list of gates to apply when a condition or case matches. |
| `gates.IfElse` | Chooses a *then* body when a condition is true; otherwise chooses an optional *else* body. |
| `gates.Switch` | Chooses among named values of one measured bit or a multi-bit register. Its default body is explicit. |
| `gates.IfChain` | A convenience builder for `if`/`elif`/`else` chains. It creates nested `IfElse` operations, not a third control-flow operation. |

The measurement must come **before** the conditional operation in the circuit.
A measurement result is not a Python `bool`, so use Qibo conditions inside
`IfElse` or `Switch` rather than a Python `if` statement while constructing the
circuit.

## Example 1: `IfElse` for fast reset

This circuit puts one qubit in a superposition, measures it, and applies `X`
only if the measured bit was `1`. The final bit should therefore always be
`0` in an ideal simulation.

```python
from qibo import Circuit, gates, set_backend

set_backend("numpy")

circuit = Circuit(1)
circuit.add(gates.H(0))
before_reset = circuit.add(
    gates.M(0, collapse=True, register_name="before_reset")
)
circuit.add(
    gates.IfElse(
        condition=before_reset.is_one(),
        then_do=gates.X(0),
    )
)
circuit.add(gates.M(0, register_name="after_reset"))

print(circuit(nshots=1000).frequencies(binary=True))
# Counter({'0': 1000}) in an ideal simulation
```

`else_do` is omitted here: its default is an empty branch, so a measured `0`
leaves the qubit alone. You can supply `else_do=gates.Z(0)` or a list of gates
when the false branch should do something.

## Example 2: `Switch` for a two-bit result

Here both qubits are measured. The three nonzero outcomes each select the
appropriate `X` gates; `00` uses the empty default. Every branch returns the
final pair to `00` in an ideal simulation.

```python
from qibo import Circuit, gates, set_backend

set_backend("numpy")

circuit = Circuit(2)
circuit.add(gates.H(0))
circuit.add(gates.H(1))
bits = circuit.add(gates.M(0, 1, collapse=True, register_name="bits"))

circuit.add(
    gates.Switch(bits)
    .case("10", gates.X(0))
    .case("01", gates.X(1))
    .case("11", [gates.X(0), gates.X(1)])
    .default([])  # "00": leave both qubits alone
)
circuit.add(gates.M(0, 1, register_name="final"))

print(circuit(nshots=1000).frequencies(binary=True))
# Counter({'00': 1000}) in an ideal simulation
```

In a two-bit result from `gates.M(0, 1)`, the first character describes qubit
0 and the second describes qubit 1. Thus `"10"` means qubit 0 measured `1`
and qubit 1 measured `0`. A `Switch` can also use integer case values, but all
its cases must use the same value form. `.default([])` explicitly says to do
nothing for any unmatched value.

## Choosing a condition

For one measured bit, use `result.is_one()` or `result.is_zero()`. For a
multi-bit result, select one bit with `result.bit(0).is_one()` or compare the
whole result with `result.equals("10")`. The first measured bit is bit 0.
Conditions can also be combined:

```python
from qibo import Circuit, conditions, gates, set_backend

set_backend("numpy")
circuit = Circuit(3)
first = circuit.add(gates.M(0, collapse=True))
second = circuit.add(gates.M(1, collapse=True))
both_one = conditions.all_of(first.is_one(), second.is_one())
either_one = conditions.any_of(first.is_one(), second.is_one())
circuit.add(gates.IfElse(both_one, then_do=gates.X(2)))
circuit.add(gates.M(2, register_name="result"))
```

Use `IfElse` when the choice is a true/false question, `Switch` when one result
has several named values, and `IfChain` when several different conditions need
an `if`/`elif`/`else` sequence. Branches may contain a gate, a list of gates,
or a nested conditional operation. Keep measurements outside branch bodies.

For example, an `IfChain` can choose between two measured patterns:

```python
# Given the two-bit result named bits in Example 2:
choice = (
    gates.IfChain()
    .if_(bits.equals("10"), gates.X(0))
    .elif_(bits.equals("01"), gates.X(1))
    .else_([])
)
```

`.else_()` completes the builder and returns an operation that can be added to
a circuit.

The examples above run with Qibo's NumPy simulator. They are deliberately
small so you can change the preparation gates or correction branches and see
how the output counts respond.
