#!/mnt/home/nqch-deploy/test-qm-backend/.venv/bin/python -u
#SBATCH --partition=sinq20
#SBATCH --job-name=qm_t_gate_teleportation
#SBATCH --time=00:30:00
#SBATCH --chdir=/mnt/home/nqch-deploy/test-qm-backend
#SBATCH --output=/mnt/home/nqch-deploy/test-qm-backend/slurm_logs/slurm-t-gate-teleportation-%j.out
#SBATCH --error=/mnt/home/nqch-deploy/test-qm-backend/slurm_logs/slurm-t-gate-teleportation-%j.err
#SBATCH --export=ALL,QM_BACKEND_PLATFORMS=/mnt/scratch/qibolab_platforms_nqch

"""T-gate teleportation on q15/q19, with a direct-T reference on q5."""

import qibo
from qibo import Circuit, gates

qibo.set_backend(
    "qm-backend",
    platform="sinq20",
    physical_qubits=('q15', 'q19', 'q5'),
)

circuit = Circuit(3)

# Input |+> and magic state T|+>.
circuit.add(gates.H(0))
circuit.add(gates.H(1))
circuit.add(gates.T(1))
circuit.add(gates.CNOT(0, 1))

feedback = circuit.add(gates.M(1, collapse=True, register_name="feedback"))
circuit.add(gates.IfElse(feedback.is_one(), then_do=gates.S(0)))

# Read the teleported phase in the X basis.
circuit.add(gates.H(0))
circuit.add(gates.M(0, register_name="teleported"))

# Independent direct-T reference, also measured in the X basis.
circuit.add(gates.H(2))
circuit.add(gates.T(2))
circuit.add(gates.H(2))
circuit.add(gates.M(2, register_name="local"))

result = circuit(nshots=10000)

print(f"QM job ID: {result.qm_job_id}", flush=True)
print("\nFinal counts:", result.frequencies(), flush=True)
print("\nAll measurement registers:", result.register_frequencies(), flush=True)
