#!/mnt/home/nqch-deploy/test-qm-backend/.venv/bin/python -u
#SBATCH --partition=sinq20
#SBATCH --job-name=qm_repetition_code
#SBATCH --time=00:30:00
#SBATCH --chdir=/mnt/home/nqch-deploy/test-qm-backend
#SBATCH --output=/mnt/home/nqch-deploy/test-qm-backend/slurm_logs/slurm-repetition-code-%j.out
#SBATCH --error=/mnt/home/nqch-deploy/test-qm-backend/slurm_logs/slurm-repetition-code-%j.err
#SBATCH --export=ALL,QM_BACKEND_PLATFORMS=/mnt/scratch/qibolab_platforms_nqch

"""Parity measurement and Switch correction on the q4-q5-q10-q15-q19 line."""

import qibo
from qibo import Circuit, gates

qibo.set_backend(
    "qm-backend",
    platform="sinq20",
    physical_qubits=('q4', 'q5', 'q10', 'q15', 'q19'),
)

data0, anc0, data1, anc1, data2 = range(5)
circuit = Circuit(5, wire_names=["q4", "q5", "q10", "q15", "q19"])

# Prepare all data qubits in |+> to exercise all four syndromes.
circuit.add(gates.H(data0))
circuit.add(gates.H(data1))
circuit.add(gates.H(data2))
circuit.add(gates.H(anc0))
circuit.add(gates.H(anc1))

# Each ancilla measures the parity of its two data neighbours.
circuit.add(gates.CZ(anc0, data1))
circuit.add(gates.CZ(anc1, data2))
circuit.add(gates.CZ(anc0, data0))
circuit.add(gates.CZ(anc1, data1))
circuit.add(gates.H(anc0))
circuit.add(gates.H(anc1))

syndrome = circuit.add(gates.M(anc0, anc1, collapse=True, register_name="syndrome"))
circuit.add(
    gates.Switch(syndrome)
    .case("10", gates.X(data0))
    .case("11", gates.X(data1))
    .case("01", gates.X(data2))
    .default([])
)
circuit.add(gates.M(data0, data1, data2, register_name="result"))

result = circuit(nshots=1000)

print(f"QM job ID: {result.qm_job_id}", flush=True)
print("\nFinal counts:", result.frequencies(), flush=True)
print("\nAll measurement registers:", result.register_frequencies(), flush=True)
