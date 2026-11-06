# CQT-conditional-operations

Notebooks, NQCH hardware-script sources, and a public guide for Qibo's
measurement-dependent `IfElse` / `Switch` API. The implementation lives in the
sibling **CQT-qibo** repository; this repository contains demonstrations.

## Where to start

| Location | Purpose |
| --- | --- |
| [docs/index.md](docs/index.md) | API vocabulary and NumPy simulation examples; source for the GitHub Pages guide. |
| [Notebook 0](notebooks/0_Executing_dynamic_circuits_in_python_OpenQASM3.ipynb) | Original Qiskit/OpenQASM 3 exploration. |
| [Notebook 1](notebooks/1_Testing_examples_hardware_run.ipynb) | Initial Qibo examples and local simulation. |
| [Notebook 2](notebooks/2_Hardware_Demo_Conditional_Operations.ipynb) | Earlier hardware demos: single-round reset, T-gate teleportation, and injected-error repetition with a SWAP. |
| [Notebook 3](notebooks/3_Hardware_Demo_Conditional_Operations.ipynb) | Current four-demo reference: two-round reset, T-gate teleportation with a local reference, quantum teleportation, and repetition exercising all four syndromes. Includes saved runs and plots. |
| [nqch_scripts/](nqch_scripts/) | Hardware-script sources: files `0`–`3` preserve earlier tests; files `4`–`7` accompany notebook 3. |

Files named `EO_*` are ignored by this repository's `.gitignore` and are local
working copies. A date in a filename does not establish when saved outputs were
generated. The parent workspace's
[5 November handoff](../docs/Current_status/Current_status_05Nov.md) records the
timeline, branch state, saved results, and remaining limitations.

## Simulation and hardware execution

Local `circuit(nshots=...)` uses Qibo's native simulator, supported on NumPy and
qibojit Numba CPU. The conditional API is available on the fork's `develop` and
`eo-switch-native-execution` branches; the reviewed local refs both point to
`65779943a`.

The hardware demos use:

```text
Qibo → OpenQASM 3 → Qiskit → physical layout and QM target-gate translation
  → provider's Qiskit QM backend → OpenQASM 3 → qm-qasm → QUA → hardware
```

Newer project notes record a `qm-qasm` update enabling the register comparisons
used by `Switch`; the initial constant-`False` compiler failure is historical.
Saved hardware runs include repetition-code `Switch` execution.

**Hardware submission cells perform real SSH/Slurm submissions.** They execute
the prepared Python script already on the server, not the circuit in the local
simulation cell. Local edits do not automatically update that server script.
Submission is reserved for the user; do not execute those cells during onboarding.

## Environment

The notebook runs against a dedicated virtual environment, `.venv_conditional_operations`, located one level up (as a sibling of this folder):

```
forks-CQT-S14/
├── .venv_conditional_operations/   <- the venv
└── CQT-conditional-operations/     <- this folder
```

### Create/recreate the environment

From the `forks-CQT-S14` repo root:

```bash
cd "~/forks-CQT-S14"
python3 -m venv .venv_conditional_operations
.venv_conditional_operations/bin/pip install --upgrade pip
.venv_conditional_operations/bin/pip install -r CQT-conditional-operations/requirements.txt
```

[`requirements.txt`](requirements.txt) pins selected notebook packages, but is
**not a complete environment lockfile**. The commands above install that subset;
they do not reproduce the editable Qibo checkout, every notebook import, or the
QM/QuAM/provider stack. Current demo notebooks also import pandas, which is not
listed there, and insert the sibling CQT-qibo `src` directory into their import
path. Recreating a working environment requires checking those additional needs.
The existing freeze filter below records only its selected packages:

```bash
.venv_conditional_operations/bin/pip freeze | grep -iE '^(qiskit|matplotlib|pylatexenc|numpy|jupyter|ipykernel)' > CQT-conditional-operations/requirements.txt
```

Installed packages and why:
- `qiskit` — core circuit construction, `if_test` conditionals, OpenQASM 3 dump/load
- `qiskit-ibm-runtime` — `QiskitRuntimeService`, `MidCircuitMeasure`
- `qiskit-aer` — `AerSimulator`
- `matplotlib` + `pylatexenc` — required by `qc.draw(output='mpl')`
- `numpy` — random state generation in the teleportation example
- `jupyter` + `ipykernel` — running the notebook and registering it as a selectable kernel

### Running the notebook directly

```bash
source ../.venv_conditional_operations/bin/activate
jupyter notebook
```

Then open the relevant notebook under `notebooks/`; start with notebook 3 for
the current demos. Review submission cells before execution.

## Using the environment as a kernel in VS Code

Register the venv as a Jupyter kernel (only needs to be done once):

```bash
cd "/Users/elis/Desktop/Work/PROJECTS/Quantum/forks-CQT-S14"
.venv_conditional_operations/bin/python -m ipykernel install --user --name conditional-operations --display-name "venv_conditional_ops"
```

Then in VS Code:
1. Open the notebook.
2. Click the kernel picker in the top-right corner.
3. Choose **Select Another Kernel** → **Jupyter Kernel** → **venv_conditional_ops**.

Alternatively, you can skip the `ipykernel install` step and point VS Code directly at the venv's interpreter: **Select Another Kernel** → **Python Environments** → browse to `../.venv_conditional_operations/bin/python`.

## Notes

- The original Qiskit exploration's `QiskitRuntimeService()` calls are commented
  out. That observation does not apply to the later hardware notebooks, whose
  submission cells actively launch NQCH jobs when executed.
