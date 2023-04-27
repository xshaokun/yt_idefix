
# yt_idefix
[![PyPI](https://img.shields.io/pypi/v/yt-idefix.svg?logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/yt_idefix/)
[![PyPI](https://img.shields.io/badge/requires-Python%20≥%203.8-blue?logo=python&logoColor=white)](https://pypi.org/project/yt_idefix/)
[![yt-project](https://img.shields.io/static/v1?label="works%20with"&message="yt"&color="blueviolet")](https://yt-project.org)

<!--- Tests and style --->
[![CI](https://github.com/neutrinoceros/yt_idefix/actions/workflows/ci.yml/badge.svg)](https://github.com/neutrinoceros/yt_idefix/actions/workflows/ci.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/neutrinoceros/yt_idefix/main.svg)](https://results.pre-commit.ci/latest/github/neutrinoceros/yt_idefix/main)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v1.json)](https://github.com/charliermarsh/ruff)

A maturing yt frontend for Idefix and Pluto, packaged as an extension for yt.

## Installation

```shell
python -m pip install yt_idefix
```

## Supported formats

| Code   | format | supported since | additional dependencies |
|--------|:------:|:---------------:|-------------------------|
| Idefix | `.dmp` | v0.1.0          |                         |
| Idefix | `.vtk` | v0.3.0          |                         |
| Pluto  | `.vtk` | v0.9.0          |                         |
| Pluto  |  XDMF  | v1.1.0          | `h5py`                  |

## Usage

After importing `yt` itself, make sure to activate the extension
```python
import yt
import yt_idefix
```

Now `yt.load` will be able to read Pluto/Idefix output files.

### Additional arguments to `yt.load`
The metadata are parsed from data file, definitions header file and inifile when loading dataset.

Definitions header file (`definitions.h` for Pluto, or `definitions.hpp` for Idefix) and inifile (`pluto.ini` and `idefix.ini` respectively) are discovered automatically if they match default names, are located along with data files, and unique. Otherwise, they can be specified explicitly as paths (either relative to data files or absolute paths) with parameters `definitions_header` and `inifile` respectively.

Geometry is parsed automatically whenever possible, but as a last resort, it can also be specified as a keyword argument (possible values are "cartesian", "spherical", "cylindrical" and "polar").

```python
# Examples
ds = yt.load("data.0010.vtk", definitions_header="../definitions.h", inifile="example.ini")
ds = yt.load("data.0010.vtk", geometry='spherical")
```

The data are loaded as physical quantities with units. The default unit system is `cgs` in yt. This frontend can convert data from code units into `cgs` properly, based on the unit definitions from metadata.

Users are able to choose the unit displayed in two ways, through `unit_system` ("code", "mks" and "cgs") and `units_override`(only valid for Pluto).

```python
# Examples on units
ds = yt.load("data.0010.vtk", unit_system='mks")

units_override = dict(length_unit=(100.0, "au"), mass_unit=yt.units.mass_sun)
ds = yt.load("data.0010.vtk", unit_override=unit_override) # Caution that other units will also be changed for consistency!!
```
With Pluto data, the rest of the system will be derived consistently with given units, within the following rules:
1. Temperature unit cannot be overridden (always set to Kelvin)
2. No more than three units can be overridden at once (overconstrained systems are never validated for simplicity)
3. When given less than three overrides, base units in Pluto (ordered: velocity_unit, density_unit, length_unit) are assumed
4. The following combinations are not allowed

```python
{"magnetic_unit", "velocity_unit", "density_unit"},
{"velocity_unit", "time_unit", "length_unit"},
{"density_unit", "length_unit", "mass_unit"},
```

yt is able to provide some derived fields from existed fields, e.g., `"cell_volume"`. Fields related to element species can be created according to primordial abundances of H and He, through `default_species_fields` (`"neutral"` and `"ionized"`) parameters.

```python
# Example
ds = yt.load("data.0010.vtk", default_species_fields="ionized")
```

## Experimental features

### Seamless plugin support
*new in yt 4.2 (unreleased) + yt_idefix 0.16*

`yt>=4.2` supports automatic
loading for external frontends, i.e., the extra import line (`import yt_idefix`)
will not be needed with this version.

This feature is marked as experimental until yt 4.2.0 is released.
In the mean time, this feature can be enabled by installing yt from source as, i.e.,
```shell
python -m pip install git+https://github.com/yt-project/yt.git
```

### Strecthed grids support
*new in yt 4.1 + yt_idefix 0.12*
- `yt_idefix>=0.12.0` natively supports `yt.SlicePlot` for streched grids
- `yt>=4.1.0` is required from `yt.ProjectionPlot`

Streched grids support is considered experimental as of yt 4.1
