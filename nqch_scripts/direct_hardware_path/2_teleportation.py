"""Run the notebook's T-gate teleportation circuit on sinq20 through QASM 3 and QM.

Run only inside a user-submitted Slurm job. Logical qubits 0 and 1 are pinned
respectively to the physical qubits named in ``PHYSICAL_QUBITS``. The first
measurement controls an S correction on qubit 0; the final X-basis measurement
of qubit 0 should give P(1) near sin^2(pi/8) on ideal hardware. An optional
offline QUA preflight checks that the measurement-dependent branch survives
translation before the backend opens a hardware session. The backend compiles
again when run() submits the 1000-shot circuit.
"""

import json
import math
import os
from pathlib import Path

import qiskit.qasm3
from qibo import Circuit, gates
from qibo_qm_provider import FluxTunableTransmonBackend, add_basic_macros
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.controlflow import IfElseOp
from qiskit.transpiler import Layout
from qm import generate_qua_script
from quam_config import Quam


SINQ20_ROOT = Path("/mnt/scratch/qibolab_platforms_nqch/sinq20")
PHYSICAL_QUBITS = ("q15", "q19")
SHOTS = 1000
ENABLE_QUA_PREFLIGHT = True  # Set to False to skip the optional QUA check.
EXPECTED_REGISTERS = [("feedback", 1), ("result", 1)]


def build_teleportation() -> Circuit:
    """Prepare a magic state, teleport T onto qubit 0, and measure in X."""
    circuit = Circuit(2)
    circuit.add(gates.H(0))
    circuit.add(gates.H(1))
    circuit.add(gates.T(1))
    circuit.add(gates.CNOT(0, 1))
    feedback = circuit.add(gates.M(1, collapse=True, register_name="feedback"))
    circuit.add(gates.IfElse(feedback.is_one(), then_do=gates.S(0)))
    circuit.add(gates.H(0))
    circuit.add(gates.M(0, register_name="result"))
    return circuit


def qibo_to_openqasm3_to_qiskit(circuit: Circuit) -> QuantumCircuit:
    """Convert through OpenQASM 3 and verify the teleportation control flow."""
    qasm = circuit.to_qasm3(qiskit_compatible=True, reuse_registers=False)
    qiskit_circuit = qiskit.qasm3.loads(qasm)
    if len(qiskit_circuit.qubits) != 2:
        raise RuntimeError("Expected exactly two logical qubits")
    if [(reg.name, reg.size) for reg in qiskit_circuit.cregs] != EXPECTED_REGISTERS:
        raise RuntimeError("QASM import changed the teleportation registers")
    if sum(isinstance(item.operation, IfElseOp) for item in qiskit_circuit.data) != 1:
        raise RuntimeError("QASM import did not preserve exactly one IfElse")
    if sum(item.operation.name == "measure" for item in qiskit_circuit.data) != 2:
        raise RuntimeError("Expected one feedback and one final measurement")
    if sum(item.operation.name == "cx" for item in qiskit_circuit.data) != 1:
        raise RuntimeError("QASM import changed the teleportation CNOT")
    return qiskit_circuit


def load_qm_backend():
    """Use the same sinq20 QuAM state, wiring, and macros as fast reset."""
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


def transpilation(converted_circuit: QuantumCircuit, qm_backend) -> tuple[QuantumCircuit, list[int]]:
    """Place both logical qubits and translate gates for the QM target."""
    physical_indices = [qm_backend.qubit_dict[name] for name in PHYSICAL_QUBITS]
    layout = Layout.from_intlist(physical_indices, converted_circuit.qregs[0])
    placed = transpile(converted_circuit, initial_layout=layout, optimization_level=0)
    for logical_index, physical_index in enumerate(physical_indices):
        actual = placed.layout.initial_layout[converted_circuit.qubits[logical_index]]
        if actual != physical_index:
            raise RuntimeError(
                f"Logical qubit {logical_index} was placed at {actual}, "
                f"not {physical_index}"
            )

    # Translate H, T, S, and CNOT to gates supported by the QM target.
    native = transpile(placed, backend=qm_backend, optimization_level=0)
    if sum(isinstance(item.operation, IfElseOp) for item in native.data) != 1:
        raise RuntimeError("QM target translation did not preserve IfElse")
    if [(reg.name, reg.size) for reg in native.cregs] != EXPECTED_REGISTERS:
        raise RuntimeError("QM target translation changed the measurement registers")
    active_indices = {
        native.find_bit(qubit).index
        for item in native.data for qubit in item.qubits
    }
    if active_indices != set(physical_indices):
        raise RuntimeError("QM target translation moved an operation off q15/q19")
    if native.count_ops().get("cz", 0) < 1:
        raise RuntimeError("QM target translation did not map CNOT to a CZ")
    return native, physical_indices


def run_qua_preflight(qm_backend, native: QuantumCircuit) -> None:
    """Check the generated QUA offline; run() compiles again for submission."""
    compilation = qm_backend.quantum_circuit_to_qua(native)
    qua_script = generate_qua_script(compilation.qua_program)
    if "with if_(" not in qua_script or "with if_(False)" in qua_script:
        raise RuntimeError("Unsafe or missing measurement-dependent QUA branch")
    if set(compilation.outputs.table) != {"feedback", "result"}:
        raise RuntimeError("Unexpected QUA measurement outputs")
    if qm_backend._qmm is not None or qm_backend._qm is not None:
        raise RuntimeError("The offline preflight unexpectedly opened a QM connection")

    print("QUA branch lines:", flush=True)
    for line in qua_script.splitlines():
        if "with if_(" in line or "with else_(" in line:
            print(f"  {line.strip()}", flush=True)


def report_results(counts, shots: int) -> None:
    """Label feedback/final outcomes and report the final-one frequency."""
    # Qiskit displays registers in reverse declaration order: result, feedback.
    # The QM provider may omit spaces between the two register values.
    print("Hardware counts:", flush=True)
    final_one_count = 0
    for key, count in sorted(counts.items()):
        bits = key.replace(" ", "")
        if len(bits) != 2 or any(bit not in "01" for bit in bits):
            raise RuntimeError(f"Unexpected result/feedback bit string: {key!r}")
        result_bit, feedback_bit = bits
        print(
            f"  feedback={feedback_bit}  result={result_bit}  shots={count}",
            flush=True,
        )
        if result_bit == "1":
            final_one_count += count
    print(f"Final one outcomes: {final_one_count}/{shots}", flush=True)
    print(
        f"P(1) = {final_one_count / shots:.3f}; "
        f"ideal sin^2(pi/8) = {math.sin(math.pi / 8) ** 2:.3f}",
        flush=True,
    )


def main() -> None:
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("Run this hardware script only inside a user-submitted Slurm job")

    # 1. Transform the Qibo circuit through OpenQASM 3 to Qiskit.
    converted_circuit = qibo_to_openqasm3_to_qiskit(build_teleportation())

    # 2. Load Arthur's provider Qiskit backend using the sinq20 configuration.
    qm_backend = load_qm_backend()

    # 3. Place both qubits and translate the circuit to QM target gates.
    native, physical_indices = transpilation(converted_circuit, qm_backend)
    print(
        f"Placement: logical 0 -> {PHYSICAL_QUBITS[0]} ({physical_indices[0]}), "
        f"logical 1 -> {PHYSICAL_QUBITS[1]} ({physical_indices[1]})",
        flush=True,
    )
    print(f"Shots: {SHOTS}", flush=True)

    # 4. Optionally check QUA compilation before opening a hardware session.
    if ENABLE_QUA_PREFLIGHT:
        run_qua_preflight(qm_backend, native)

    # 5. The user submits the Slurm job; this call submits to QM once inside it.
    job = qm_backend.run(native, shots=SHOTS)
    print(f"QM job ID: {job.job_id()}", flush=True)
    result = job.result()
    if not result.success:
        raise RuntimeError("QM result reported failure")
    counts = result.get_counts()
    if sum(counts.values()) != SHOTS:
        raise RuntimeError(f"Expected {SHOTS} results, received {counts}")

    # 6. Report measured results.
    report_results(counts, SHOTS)


if __name__ == "__main__":
    main()
