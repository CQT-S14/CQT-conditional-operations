"""Run the notebook's five-qubit repetition code on sinq20 through QM.

Three data qubits (q4, q10, q19) encode one logical qubit. The first ancilla
(q5) checks q4/q10 and the second ancilla (q15) checks q10/q19. The five
qubits form the line q4-q5-q10-q15-q19, so all CZ gates use the q4-q5,
q5-q10, q10-q15, and q15-q19 connections and no SWAP is needed.

All three data qubits start in |+>, so the parity measurement gives each of
the four syndromes with equal probability. The Switch correction then leaves
the data in 000 or 111, which are the only ideal final outcomes.

Qibo exports the syndrome Switch as OpenQASM 3 register comparisons. The
offline QUA preflight checks that these comparisons remain dynamic before a
QM session opens. A user must submit this script as a Slurm job.
"""

import json
import os
import re
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
SHOTS = 1000
ENABLE_QUA_PREFLIGHT = True

# Physical qubits for circuit wires 0, 1, 2, 3, 4:
# data 0, ancilla 0, data 1, ancilla 1, data 2.
PHYSICAL_QUBITS = ("q4", "q5", "q10", "q15", "q19")
REQUIRED_CZ_EDGES = ((0, 1), (1, 2), (2, 3), (3, 4))
EXPECTED_CZ_COUNT = 4  # Four parity CZs, one per line edge.
EXPECTED_REGISTERS = [("syndrome", 2), ("result", 3)]
EXPECTED_SYNDROME_CASES = (1, 3, 2)  # QASM integers for 10, 11, 01.


def build_repetition() -> Circuit:
    """Inject one X error, measure parity, correct it, and measure the data."""
    data0, anc0, data1, anc1, data2 = range(5)
    circuit = Circuit(5, wire_names=list(PHYSICAL_QUBITS))

    # Put every data qubit in |+> so all four syndromes occur.
    circuit.add(gates.H(data0))
    circuit.add(gates.H(data1))
    circuit.add(gates.H(data2))

    circuit.add(gates.H(anc0))
    circuit.add(gates.H(anc1))

    # Parity checks: q5 on q4/q10 and q15 on q10/q19.
    circuit.add(gates.CZ(anc0, data1))
    circuit.add(gates.CZ(anc1, data2))
    circuit.add(gates.CZ(anc0, data0))
    circuit.add(gates.CZ(anc1, data1))
    circuit.add(gates.H(anc0))
    circuit.add(gates.H(anc1))

    syndrome = circuit.add(
        gates.M(anc0, anc1, collapse=True, register_name="syndrome")
    )
    circuit.add(
        gates.Switch(syndrome)
        .case("10", gates.X(data0))
        .case("11", gates.X(data1))
        .case("01", gates.X(data2))
        .default([])
    )
    circuit.add(gates.M(data0, data1, data2, register_name="result"))
    return circuit


def syndrome_conditions(circuit: QuantumCircuit) -> list[tuple]:
    """Find nested Qiskit if/else comparisons produced from the Switch."""
    conditions = []
    for item in circuit.data:
        operation = item.operation
        if isinstance(operation, IfElseOp):
            conditions.append(operation.condition)
            for block in operation.blocks:
                conditions.extend(syndrome_conditions(block))
    return conditions


def verify_syndrome_switch(circuit: QuantumCircuit, stage: str) -> None:
    conditions = syndrome_conditions(circuit)
    if tuple(value for _, value in conditions) != EXPECTED_SYNDROME_CASES:
        raise RuntimeError(f"{stage} changed the three syndrome cases: {conditions}")
    if any(register.name != "syndrome" or register.size != 2 for register, _ in conditions):
        raise RuntimeError(f"{stage} changed the syndrome condition register")


def qibo_to_openqasm3_to_qiskit(circuit: Circuit) -> QuantumCircuit:
    qasm = circuit.to_qasm3(qiskit_compatible=True, reuse_registers=False)
    qiskit_circuit = qiskit.qasm3.loads(qasm)
    if len(qiskit_circuit.qubits) != 5:
        raise RuntimeError("Expected five circuit wires")
    if [(reg.name, reg.size) for reg in qiskit_circuit.cregs] != EXPECTED_REGISTERS:
        raise RuntimeError("QASM import changed the measurement registers")
    if sum(item.operation.name == "measure" for item in qiskit_circuit.data) != 5:
        raise RuntimeError("Expected two syndrome and three final measurements")
    cz_edges = [
        frozenset(qiskit_circuit.find_bit(qubit).index for qubit in item.qubits)
        for item in qiskit_circuit.data if item.operation.name == "cz"
    ]
    expected_edges = {frozenset(pair) for pair in REQUIRED_CZ_EDGES}
    if len(cz_edges) != EXPECTED_CZ_COUNT or set(cz_edges) != expected_edges:
        raise RuntimeError(
            f"QASM import changed the {EXPECTED_CZ_COUNT} CZ gates or their allowed edges"
        )
    verify_syndrome_switch(qiskit_circuit, "QASM import")
    return qiskit_circuit


def load_qm_backend():
    """Use the known sinq20 QuAM state, wiring, and provider macros."""
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


def physical_indices_and_connectivity(qm_backend) -> list[int]:
    """Check the five labels and all four physical CZ connections."""
    unknown = [name for name in PHYSICAL_QUBITS if name not in qm_backend.qubit_dict]
    if unknown:
        raise RuntimeError(f"Physical qubits absent from sinq20: {unknown}")
    indices = [qm_backend.qubit_dict[name] for name in PHYSICAL_QUBITS]
    if len(set(indices)) != 5:
        raise RuntimeError("Physical qubit labels must resolve to distinct qubits")
    for left, right in REQUIRED_CZ_EDGES:
        pair = (indices[left], indices[right])
        if not (
            qm_backend.target.instruction_supported(operation_name="cz", qargs=pair)
            or qm_backend.target.instruction_supported(operation_name="cz", qargs=pair[::-1])
        ):
            raise RuntimeError(
                f"No CZ connection for {PHYSICAL_QUBITS[left]}-"
                f"{PHYSICAL_QUBITS[right]} in the QM target"
            )
    return indices


def transpilation(
    converted_circuit: QuantumCircuit, qm_backend, physical_indices: list[int]
) -> QuantumCircuit:
    """Place the five wires and translate H gates to the QM target."""
    layout = Layout.from_intlist(physical_indices, converted_circuit.qregs[0])
    placed = transpile(converted_circuit, initial_layout=layout, optimization_level=0)
    for logical, physical in enumerate(physical_indices):
        actual = placed.layout.initial_layout[converted_circuit.qubits[logical]]
        if actual != physical:
            raise RuntimeError(f"Circuit wire {logical} was placed at {actual}, not {physical}")

    native = transpile(placed, backend=qm_backend, optimization_level=0)
    verify_syndrome_switch(native, "QM target translation")
    if [(reg.name, reg.size) for reg in native.cregs] != EXPECTED_REGISTERS:
        raise RuntimeError("QM target translation changed the measurement registers")
    active_indices = {
        native.find_bit(qubit).index for item in native.data for qubit in item.qubits
    }
    if active_indices != set(physical_indices):
        raise RuntimeError("QM target translation moved an operation off the selected qubits")
    native_cz_edges = [
        frozenset(native.find_bit(qubit).index for qubit in item.qubits)
        for item in native.data if item.operation.name == "cz"
    ]
    expected_edges = {
        frozenset((physical_indices[left], physical_indices[right]))
        for left, right in REQUIRED_CZ_EDGES
    }
    if len(native_cz_edges) != EXPECTED_CZ_COUNT or set(native_cz_edges) != expected_edges:
        raise RuntimeError("QM target translation changed the CZ count or physical edges")
    return native


def run_qua_preflight(qm_backend, native: QuantumCircuit) -> None:
    """Reject constant-False syndrome cases before connecting to hardware."""
    compilation = qm_backend.quantum_circuit_to_qua(native)
    qua_script = generate_qua_script(compilation.qua_program)
    if re.search(r"with\s+(?:if_|elif_|case_)\(\s*False\s*\)", qua_script):
        raise RuntimeError("QUA compiler reduced a syndrome branch to constant False")
    condition_lines = [
        line.strip() for line in qua_script.splitlines()
        if re.search(r"with\s+(?:if_|elif_|case_)\(", line)
    ]
    if len(condition_lines) < 3:
        raise RuntimeError(f"Expected three dynamic QUA syndrome branches: {condition_lines}")
    if set(compilation.outputs.table) != {"syndrome", "result"}:
        raise RuntimeError("Unexpected QUA measurement outputs")
    if qm_backend._qmm is not None or qm_backend._qm is not None:
        raise RuntimeError("The offline preflight unexpectedly opened a QM connection")

    print("QUA control-flow lines:", flush=True)
    for line in condition_lines:
        print(f"  {line}", flush=True)


def report_results(counts, shots: int) -> None:
    """Print syndrome q5/q15 and final data q4/q10/q19 for the notebook."""
    # Qiskit displays the last declared register first, and reverses the bit
    # order within each register: result[2:0] syndrome[1:0].
    print("Hardware counts:", flush=True)
    final_zero_count = 0
    final_codeword_count = 0
    for key, count in sorted(counts.items()):
        bits = key.replace(" ", "")
        if len(bits) != 5 or any(bit not in "01" for bit in bits):
            raise RuntimeError(f"Unexpected result/syndrome bit string: {key!r}")
        data_result = bits[:3][::-1]  # Physical q4, q10, q19.
        syndrome = bits[3:][::-1]    # Physical q5, q15; Switch case order.
        print(
            f"  syndrome={syndrome}  data_result={data_result}  shots={count}",
            flush=True,
        )
        if data_result == "000":
            final_zero_count += count
        if data_result in ("000", "111"):
            final_codeword_count += count
    print(f"Final 000 outcomes: {final_zero_count}/{shots}", flush=True)
    print(f"Final 000 or 111 outcomes: {final_codeword_count}/{shots}", flush=True)


def main() -> None:
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("Run this hardware script only inside a user-submitted Slurm job")

    converted_circuit = qibo_to_openqasm3_to_qiskit(build_repetition())
    qm_backend = load_qm_backend()
    physical_indices = physical_indices_and_connectivity(qm_backend)
    native = transpilation(converted_circuit, qm_backend, physical_indices)
    print("Placement (circuit wire -> physical qubit):", flush=True)
    for wire, (name, index) in enumerate(zip(PHYSICAL_QUBITS, physical_indices)):
        print(f"  {wire} -> {name} ({index})", flush=True)
    print(f"Shots: {SHOTS}", flush=True)

    if ENABLE_QUA_PREFLIGHT:
        run_qua_preflight(qm_backend, native)

    # Only the user submits the Slurm job. This call runs inside that job.
    job = qm_backend.run(native, shots=SHOTS)
    print(f"QM job ID: {job.job_id()}", flush=True)
    result = job.result()
    if not result.success:
        raise RuntimeError("QM result reported failure")
    counts = result.get_counts()
    if sum(counts.values()) != SHOTS:
        raise RuntimeError(f"Expected {SHOTS} results, received {counts}")
    report_results(counts, SHOTS)


if __name__ == "__main__":
    main()
