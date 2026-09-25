# CQT-conditional-operations

This folder contains `Executing dynamic circuits in python OpenQASM3.ipynb`, a Qiskit notebook demonstrating dynamic circuits (mid-circuit measurement, classically-conditioned gates via `if_test`) and dumping them to OpenQASM 3, including a 3-bit repetition code example.

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

Dependencies are pinned in [`requirements.txt`](requirements.txt) in this folder. To recreate the environment on another machine, just run the two commands above with that file present. If you add/upgrade a package in the venv and want to capture the change, regenerate it with:

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

Then open `Executing dynamic circuits in python OpenQASM3.ipynb`.

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

- `QiskitRuntimeService()` calls in the first cell are commented out — the notebook runs entirely locally/offline as-is. Uncommenting them to target a real IBM backend requires IBM Quantum account credentials configured separately.
