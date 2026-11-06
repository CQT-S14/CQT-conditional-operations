# CQT-conditional-operations

Notebooks, NQCH runner scripts, and a public guide for Qibo's
measurement-dependent `IfElse` / `Switch` API. The API implementation lives in
**CQT-qibo**; the separately developed **qm-backend** package makes the established
QASM/Qiskit/QM hardware route selectable through ordinary Qibo execution.
This repository contains the demonstrations for both ways of using that route.

## Where to start

| Location | Purpose |
| --- | --- |
| [docs/index.md](docs/index.md) | API vocabulary and native NumPy simulation examples; source for the GitHub Pages guide. |
| [Notebook 0](notebooks/0_Executing_dynamic_circuits_in_python_OpenQASM3.ipynb) | Original Qiskit/OpenQASM 3 exploration. |
| [notebooks/direct_hardware_path/](notebooks/direct_hardware_path/) | Earlier demonstrations using the direct hardware route. Notebook 1 contains initial examples; notebook 2 preserves earlier circuit versions. |
| [Direct-path notebook 3](notebooks/direct_hardware_path/3_Hardware_Demo_Conditional_Operations.ipynb) | Four-demo reference: two-round reset, T-gate teleportation with a local reference, quantum state teleportation, and repetition exercising all four syndromes. Includes saved hardware results and plots. |
| [QM-backend_Conditional_Ops.ipynb](notebooks/qm-backend_path/QM-backend_Conditional_Ops.ipynb) | All four circuits through `qm-backend`: local circuit drawings, submission of the notebook's own code, result retrieval and plots. |
| [QM-backend_FastReset.ipynb](notebooks/qm-backend_path/QM-backend_FastReset.ipynb) | Fast-reset-only version of the backend notebook workflow. |
| [nqch_scripts/direct_hardware_path/](nqch_scripts/direct_hardware_path/) | Separate server-script sources for the direct route. Files `0`–`3` preserve earlier tests; files `4`–`7` accompany direct-path notebook 3. |
| [nqch_scripts/qm-backend_path/](nqch_scripts/qm-backend_path/) | Simple standalone backend runners: `fast_reset.py`, `t_gate_teleportation.py`, `quantum_state_teleportation.py`, and `repetition_code.py`. `runner.py` preserves the original fast-reset runner. |


## Two hardware paths

### Direct hardware path

```text
Notebook submits an existing server script
  → script constructs the Qibo circuit
  → OpenQASM 3 → Qiskit → physical placement and QM target-gate translation
  → Qiskit QM provider → OpenQASM 3 → qm-qasm → QUA → hardware
  → script prints measurements → notebook retrieves logs and plots
```

These notebooks execute a separately maintained script already on the server.
Changing a local circuit cell does not change that script. This is the route
with successful hardware demonstrations, including `Switch` in the repetition
experiment. The early constant-False QUA comparison problem was addressed by a
subsequent compiler update; it is not the current observed failure.

### QM backend path

```text
Notebook's own stored code, or a standalone runner
  → qibo.set_backend("qm-backend", platform="sinq20", physical_qubits=...)
  → circuit(nshots=...)
  → backend owns QASM export, Qiskit import, placement, target translation
    and offline QUA preflight
  → same downstream Qiskit QM provider → QM hardware execution
  → Qibo-compatible result, including intermediate measurement histories
```

The backend notebook builds the circuit locally for drawing and stores the same
construction code. Its submission cell sends backend setup, that construction
code, and execution/result extraction over SSH to Slurm. It does **not** depend
on an analogous `.py` script being installed on the server. Counts are returned
as a JSON line in the Slurm output and retrieved for plotting.

The standalone runners are an alternative: each selects the backend and defines the circuit, then it can be sbatched into a real slurm job directly.
Placement is supplied by the user. The prototype retains the established Qiskit
transpilation steps; it does not provide automatic placement or general routing.
`platform="sinq20"` names a QuAM/QM configuration, not a QiboLab platform or its
pulse-compilation route. See the sibling [qm-backend README](../qm-backend/README.md)
for configuration and result APIs.

## Environments

The local notebook environment is the sibling `.venv_conditional_operations`:

```text
forks-CQT-S14/
├── .venv_conditional_operations/
├── CQT-qibo/
├── qm-backend/
└── CQT-conditional-operations/
```

Use the CQT-qibo fork's **`eo-qm-backend`** branch to be bale to use the qm-backend path for executing on hardware.
(commit `e475bc635d605f77487f1f7438faa7097ad23a3a` or a compatible descendant).
It admits the backend's conditional circuits and lets it handle transpilation.
Public `qibo==0.3.7` alone does not contain that integration. Native conditional simulation remains available on NumPy and qibojit Numba CPU.

The backend notebook's Mac kernel needs the conditional-operation Qibo fork,
IPython, NumPy, pandas and matplotlib. The QM dependencies and hardware backend
run on the server, not in that local drawing kernel. The older direct-path
notebooks may also need Qiskit/Aer and drawing dependencies.

[`requirements.txt`](requirements.txt) is a partial notebook dependency list,
not a complete lockfile: it does not reproduce the editable Qibo fork or the
QM/QuAM environment and omits pandas. Do not treat installing that file alone
as a complete setup recipe. This file contains the required dependencies of the original first notebook built by Roman. 

The server environments are separate:

| Use | Environment |
| --- | --- |
| Established direct-script route | `/mnt/scratch/nqch-deploy/eo-switch-native-execution-venv` |
| New backend development/execution | `/mnt/home/nqch-deploy/test-qm-backend/.venv` |

The backend's [environment.md](../qm-backend/environment.md) records the original first-time package-recovery procedure and server setup (ie. how to install all hidden Paul dependencies). It also documents the
retained `cma` version conflict between Qibo and qibocal; the demonstrated
hardware route does not call CMA.
