#!/mnt/home/nqch-deploy/test-qm-backend/.venv/bin/python -u
#SBATCH --partition=sinq20
#SBATCH --job-name=qm_quantum_state_teleportation
#SBATCH --time=00:30:00
#SBATCH --chdir=/mnt/home/nqch-deploy/test-qm-backend
#SBATCH --output=/mnt/home/nqch-deploy/test-qm-backend/slurm_logs/slurm-quantum-state-teleportation-%j.out
#SBATCH --error=/mnt/home/nqch-deploy/test-qm-backend/slurm_logs/slurm-quantum-state-teleportation-%j.err
#SBATCH --export=ALL,QM_BACKEND_PLATFORMS=/mnt/scratch/qibolab_platforms_nqch

"""Teleport |-> from q19 to q10 via q15; the final H makes outcome 1 ideal."""

import qibo
from qibo import Circuit, gates

qibo.set_backend(
    "qm-backend",
    platform="sinq20",
    physical_qubits=('q19', 'q15', 'q10'),
)

circuit = Circuit(3)

# Prepare the input |-> and an entangled resource on qubits 1 and 2.
circuit.add(gates.X(0))
circuit.add(gates.H(0))
circuit.add(gates.H(2))
circuit.add(gates.H(1))
circuit.add(gates.CZ(1, 2))

# Bell measurement and its two feedback bits.
circuit.add(gates.CZ(0, 1))
circuit.add(gates.H(1))
circuit.add(gates.H(0))
feedback_x = circuit.add(gates.M(1, collapse=True, register_name="feedback_x"))
feedback_z = circuit.add(gates.M(0, collapse=True, register_name="feedback_z"))
circuit.add(gates.IfElse(feedback_x.is_one(), then_do=gates.X(2)))
circuit.add(gates.IfElse(feedback_z.is_one(), then_do=gates.Z(2)))

circuit.add(gates.H(2))
circuit.add(gates.M(2, register_name="result"))

result = circuit(nshots=1000)

print(f"QM job ID: {result.qm_job_id}", flush=True)
print("\nFinal counts:", result.frequencies(), flush=True)
print("\nAll measurement registers:", result.register_frequencies(), flush=True)
