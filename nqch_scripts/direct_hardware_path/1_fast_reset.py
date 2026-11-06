"""Run the notebook's one-qubit fast reset on sinq20 through QASM 3 and QM.

Run only inside a user-submitted Slurm job. Logical qubit 0 is pinned to
the physical qubit named by ``PHYSICAL_QUBIT``.
The mid-circuit measurement is saved as ``before_reset``; a conditional X
returns the qubit to |0> when that measurement is one; ``after_reset`` checks
the result. An optional offline QUA preflight uses the QM backend's own
translator to preview whether the measurement-controlled reset survives into
the QUA program before hardware access. The backend compiles again when run()
submits the 1000-shot circuit.
"""

import json
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
PHYSICAL_QUBIT = "q15"
SHOTS = 1000
ENABLE_QUA_PREFLIGHT = True  # Set to False to skip the optional QUA check.
EXPECTED_REGISTERS = [("before_reset", 1), ("after_reset", 1)]


def build_fast_reset() -> Circuit:
    """Measure |+>, flip a measured one to zero, then measure again."""
    circuit = Circuit(1)
    circuit.add(gates.H(0))
    before_reset = circuit.add(
        gates.M(0, collapse=True, register_name="before_reset")
    )
    circuit.add(gates.IfElse(before_reset.is_one(), then_do=gates.X(0)))
    circuit.add(gates.M(0, register_name="after_reset"))
    return circuit


def qibo_to_openqasm3_to_qiskit(circuit: Circuit) -> QuantumCircuit:
    """Convert the fast-reset circuit through QASM 3 and verify its control flow."""
    qasm = circuit.to_qasm3(qiskit_compatible=True, reuse_registers=False)
    qiskit_circuit = qiskit.qasm3.loads(qasm)
    if len(qiskit_circuit.qubits) != 1:
        raise RuntimeError("Expected exactly one logical qubit")
    if [(reg.name, reg.size) for reg in qiskit_circuit.cregs] != EXPECTED_REGISTERS:
        raise RuntimeError("QASM import changed the reset measurement registers")
    if sum(isinstance(item.operation, IfElseOp) for item in qiskit_circuit.data) != 1:
        raise RuntimeError("QASM import did not preserve exactly one IfElse")
    if sum(item.operation.name == "measure" for item in qiskit_circuit.data) != 2:
        raise RuntimeError("Expected one feedback and one final measurement")
    return qiskit_circuit


def load_qm_backend():
    """Use the same sinq20 QuAM state, wiring, and macros from working Paul script."""
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


def transpilation(converted_circuit: QuantumCircuit, qm_backend) -> tuple[QuantumCircuit, int]:
    """Place the logical qubit and translate gates for the QM backend target."""
    # First pass: explicitly place logical qubit 0 on PHYSICAL_QUBIT.
    physical_index = qm_backend.qubit_dict[PHYSICAL_QUBIT]
    layout = Layout.from_intlist([physical_index], converted_circuit.qregs[0])
    placed = transpile(converted_circuit, initial_layout=layout, optimization_level=0)
    actual = placed.layout.initial_layout[converted_circuit.qubits[0]]
    if actual != physical_index:
        raise RuntimeError(f"Logical qubit 0 was placed at {actual}, not {physical_index}")

    # Second pass: translate H to QM target gates while retaining IfElse.
    native = transpile(placed, backend=qm_backend, optimization_level=0)
    if sum(isinstance(item.operation, IfElseOp) for item in native.data) != 1:
        raise RuntimeError("QM target translation did not preserve IfElse")
    if [(reg.name, reg.size) for reg in native.cregs] != EXPECTED_REGISTERS:
        raise RuntimeError("QM target translation changed the measurement registers")
    active_indices = {
        native.find_bit(qubit).index
        for item in native.data for qubit in item.qubits
    }
    if active_indices != {physical_index}:
        raise RuntimeError(
            f"QM target translation moved an operation off {PHYSICAL_QUBIT}"
        )
    return native, physical_index


def run_qua_preflight(qm_backend, native) -> None:
    """Check the generated QUA offline; run() compiles again for submission."""
    compilation = qm_backend.quantum_circuit_to_qua(native)
    qua_script = generate_qua_script(compilation.qua_program)
    if "with if_(" not in qua_script or "with if_(False)" in qua_script:
        raise RuntimeError("Unsafe or missing measurement-dependent QUA branch")
    if set(compilation.outputs.table) != {"before_reset", "after_reset"}:
        raise RuntimeError("Unexpected QUA measurement outputs")
    if qm_backend._qmm is not None or qm_backend._qm is not None:
        raise RuntimeError("The offline preflight unexpectedly opened a QM connection")

    print("QUA branch lines:", flush=True)
    for line in qua_script.splitlines():
        if "with if_(" in line or "with else_(" in line:
            print(f"  {line.strip()}", flush=True)


def report_results(counts, shots: int) -> None:
    """Label the measured reset outcomes and report the final-zero total."""
    # Qiskit displays classical registers in reverse declaration order:
    # after_reset first, before_reset second. The QM provider may omit spaces.
    print("Hardware counts:", flush=True)
    reset_to_zero = 0
    for key, count in sorted(counts.items()):
        bits = key.replace(" ", "")
        if len(bits) != 2 or any(bit not in "01" for bit in bits):
            raise RuntimeError(f"Unexpected after/before reset bit string: {key!r}")
        after_reset, before_reset = bits
        print(
            f"  before_reset={before_reset}  after_reset={after_reset}  shots={count}",
            flush=True,
        )
        if after_reset == "0":
            reset_to_zero += count
    print(f"Final zero outcomes: {reset_to_zero}/{shots}", flush=True)


def main() -> None:
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("Run this hardware script only inside a user-submitted Slurm job")

    # 1. Transform Qibo circuit to OpenQASM 3 to Qiskit.
    converted_circuit = qibo_to_openqasm3_to_qiskit(build_fast_reset())

    # 2. Load from Arthur's provider Qiskit-Backend
    qm_backend = load_qm_backend()

    # 3. Transpilation: 
    # 1) Place the logical qubit(s) into physical ones
    # 2) Translate the circuit to QM native gates.
    native, physical_index = transpilation(converted_circuit, qm_backend)
    print(f"Placement: logical 0 -> {PHYSICAL_QUBIT} ({physical_index})", flush=True)
    print(f"Shots: {SHOTS}", flush=True)

    # 4. Optional QUA compilation to check qm_backend.run() will compile correctly.
    if ENABLE_QUA_PREFLIGHT:
        run_qua_preflight(qm_backend, native)

    # 5. Job submission: this submits to QM only when the user submits the enclosing Slurm job.
    job = qm_backend.run(native, shots=SHOTS)
    print(f"QM job ID: {job.job_id()}", flush=True)

    result = job.result()
    if not result.success:
        raise RuntimeError("QM result reported failure")
    
    counts = result.get_counts()
    if sum(counts.values()) != SHOTS:
        raise RuntimeError(f"Expected {SHOTS} results, received {counts}")

    # 6. Print out results
    report_results(counts, SHOTS)

if __name__ == "__main__":
    main()
