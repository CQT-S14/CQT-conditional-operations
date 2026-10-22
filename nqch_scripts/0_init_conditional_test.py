"""Run one reviewed conditional Qibo circuit on sinq20 through QASM 3 and QM.

Run this script only as a user-submitted Slurm job. It uses SHOTS hardware shots.
Logical qubits 0 and 1 are pinned to sinq20 q15 and q19. The selected Qibo
circuit is exported to OpenQASM 3, imported by Qiskit, translated to the QM
backend target, compiled to QUA for a local preflight check, and then submitted
to the QM backend exactly once.

The two IfElse choices passed offline Aer and QUA checks in the _3 probe.
The Switch cases are omitted: the installed compiler rendered their register
comparisons as constant False conditions, which would give incorrect hardware
behavior. Hardware results are printed as Qiskit counts: "result feedback".
Noise may produce outcomes outside the ideal Aer sets.
"""

import json
import os
from pathlib import Path

import qiskit.qasm3
from qibo import Circuit, gates
from qibo_qm_provider import FluxTunableTransmonBackend, add_basic_macros
from qiskit import transpile
from qiskit.circuit.controlflow import IfElseOp
from qiskit.transpiler import Layout
from qm import generate_qua_script
from quam_config import Quam


SINQ20_ROOT = Path("/mnt/scratch/qibolab_platforms_nqch/sinq20")
SHOTS = 1024


def build_simple_if_else() -> Circuit:
    """Apply X to q19 when the measured q15 result is one."""
    circuit = Circuit(2)
    circuit.add(gates.H(0))
    feedback = circuit.add(gates.M(0, collapse=True, register_name="feedback"))
    circuit.add(gates.IfElse(feedback.is_one(), then_do=gates.X(1)))
    circuit.add(gates.M(0, 1, register_name="result"))
    return circuit


def build_if_else_with_else() -> Circuit:
    """Apply X for feedback one, or H for feedback zero."""
    circuit = Circuit(2)
    circuit.add(gates.H(0))
    feedback = circuit.add(gates.M(0, collapse=True, register_name="feedback"))
    circuit.add(gates.IfElse(feedback.is_one(), then_do=gates.X(1), else_do=gates.H(1)))
    circuit.add(gates.M(0, 1, register_name="result"))
    return circuit


def load_qm_backend():
    """Use the sinq20 setup and macros from the known working Paul script."""
    machine = Quam.load(filepath_or_dict=SINQ20_ROOT / "state.json")
    with (SINQ20_ROOT / "wiring.json").open() as handle:
        payload = json.load(handle)
    machine.wiring = payload["wiring"]
    machine.network = payload["network"]

    backend = FluxTunableTransmonBackend(machine)
    for pair in machine.qubit_pairs.values():
        pair.macros["cz"] = pair.macros["cz_flattop"]
    add_basic_macros(backend)
    return backend.qiskit_backend


def main() -> None:
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("This hardware script must be run inside a user-submitted Slurm job")

    # Keep exactly one entry active. Uncommenting another without commenting
    # the first makes the script stop before any hardware submission.
    selected_circuits = [
        ("simple IfElse", build_simple_if_else),
        # ("IfElse with explicit else branch", build_if_else_with_else),
    ]
    if len(selected_circuits) != 1:
        raise RuntimeError("Select exactly one circuit before running hardware")
    case_name, build_circuit = selected_circuits[0]

    qasm = build_circuit().to_qasm3(
        qiskit_compatible=True, reuse_registers=False
    )
    imported = qiskit.qasm3.loads(qasm)
    if sum(isinstance(item.operation, IfElseOp) for item in imported.data) != 1:
        raise RuntimeError("QASM import did not preserve exactly one IfElse")
    if sum(item.operation.name == "measure" for item in imported.data) != 3:
        raise RuntimeError("Expected one feedback and two final measurements")

    qm_backend = load_qm_backend()
    physical_names = ("q15", "q19")
    physical_indices = [qm_backend.qubit_dict[name] for name in physical_names]
    layout = Layout.from_intlist(physical_indices, imported.qregs[0])
    placed = transpile(imported, initial_layout=layout, optimization_level=0)
    for logical_index, physical_index in enumerate(physical_indices):
        actual = placed.layout.initial_layout[imported.qubits[logical_index]]
        if actual != physical_index:
            raise RuntimeError(
                f"Logical qubit {logical_index} was placed at {actual}, "
                f"not {physical_index}"
            )

    # H is not in the QM target. Qiskit translates it to target gates,
    # including an H inside the optional else branch, and keeps IfElse.
    native = transpile(placed, backend=qm_backend, optimization_level=0)
    if sum(isinstance(item.operation, IfElseOp) for item in native.data) != 1:
        raise RuntimeError("QM target translation did not preserve IfElse")
    active_indices = {
        native.find_bit(qubit).index
        for item in native.data for qubit in item.qubits
    }
    if not active_indices <= set(physical_indices):
        raise RuntimeError("QM target translation moved an operation off q15/q19")

    compilation = qm_backend.quantum_circuit_to_qua(native)
    qua_script = generate_qua_script(compilation.qua_program)
    if "with if_(" not in qua_script or "with if_(False)" in qua_script:
        raise RuntimeError("Unsafe or missing measurement-dependent QUA branch")
    if set(compilation.outputs.table) != {"feedback", "result"}:
        raise RuntimeError("Unexpected QUA measurement outputs")
    if qm_backend._qmm is not None or qm_backend._qm is not None:
        raise RuntimeError("The offline preflight unexpectedly opened a QM connection")

    print(f"Selected circuit: {case_name}", flush=True)
    print(
        f"Placement: logical 0 -> q15 ({physical_indices[0]}), "
        f"logical 1 -> q19 ({physical_indices[1]})",
        flush=True,
    )
    print(f"Shots: {SHOTS}", flush=True)
    print("QUA branch lines:", flush=True)
    for line in qua_script.splitlines():
        if "with if_(" in line or "with else_(" in line:
            print(f"  {line.strip()}", flush=True)

    # This call submits one circuit to the quantum machine. Only the user
    # submits the enclosing Slurm job.
    job = qm_backend.run(native, shots=SHOTS)
    print(f"QM job ID: {job.job_id()}", flush=True)
    result = job.result()
    if not result.success:
        raise RuntimeError("QM result reported failure")
    counts = result.get_counts()
    if sum(counts.values()) != SHOTS:
        raise RuntimeError(f"Expected {SHOTS} results, received {counts}")
    print("Hardware counts:", flush=True)
    for bits, count in sorted(counts.items()):
        if len(bits) != 3 or any(bit not in "01" for bit in bits):
            raise RuntimeError(f"Unexpected result/feedback bit string: {bits!r}")
        print(
            f"  result={bits[:2]}  feedback={bits[2]}  shots={count}",
            flush=True,
        )


if __name__ == "__main__":
    main()
