# 📦 Installation

## From Conda (Recommended)

* Fetchez is available on `conda-forge`:

```bash
conda install -c conda-forge fetchez
```

## From Pip/PyPi

```bash
pip install fetchez
```

## From Source

Download and install git (If you have not already): [git installation](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

```bash
pip install git+https://github.com/continuous-dems/fetchez.git#egg=fetchez
```

Clone and install from source

```bash
git clone https://github.com/continuous-dems/fetchez.git
cd fetchez
pip install -e .
```

## 🛟 Module-Specific Dependencies

Fetchez is designed to be lightweight. The core installation only includes what is strictly necessary to run the engine.

However, some data modules require extra libraries to function (e.g., `boto3` for AWS data, `pyshp` for Shapefiles). You can install these "Extras" automatically using pip:

```bash
# Install support for AWS-based modules (BlueTopo, etc.)
pip install "fetchez[aws]"

# Install support for Vector processing (Shapefiles, etc.)
pip install "fetchez[vector]"

# Install ALL optional dependencies
pip install "fetchez[full]"
```

If you try to run a module without its required dependency, fetchez will exit with a helpful error message telling you exactly which extra group to install.
