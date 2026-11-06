#!/mnt/home/nqch-deploy/test-qm-backend/.venv/bin/python -u
#SBATCH --partition=sinq20
#SBATCH --job-name=qm_fast_reset
#SBATCH --time=00:30:00
#SBATCH --chdir=/mnt/home/nqch-deploy/test-qm-backend
#SBATCH --output=/mnt/home/nqch-deploy/test-qm-backend/slurm_logs/slurm-fast-reset-%j.out
#SBATCH --error=/mnt/home/nqch-deploy/test-qm-backend/slurm_logs/slurm-fast-reset-%j.err
#SBATCH --export=ALL,QM_BACKEND_PLATFORMS=/mnt/scratch/qibolab_platforms_nqch

"""Two-round fast reset on q5, submitted directly with sbatch runner.py."""

import qibo
from qibo import Circuit, gates

qibo.set_backend(
    "qm-backend",
    platform="sinq20",
    physical_qubits=("q5",),
)

circuit = Circuit(1)
circuit.add(gates.H(0))

before_reset = circuit.add(gates.M(0, collapse=True, register_name="before_reset"))
circuit.add(gates.IfElse(before_reset.is_one(), then_do=gates.X(0)))

before_reset2 = circuit.add(gates.M(0, collapse=True, register_name="before_reset2"))
circuit.add(gates.IfElse(before_reset2.is_one(), then_do=gates.X(0)))

circuit.add(gates.M(0, register_name="after_reset"))

result = circuit(nshots=1000)

print(f"QM job ID: {result.qm_job_id}", flush=True)
print("\nFinal counts:", result.frequencies(), flush=True)
print("\nAll measurement registers:", result.register_frequencies(), flush=True)
