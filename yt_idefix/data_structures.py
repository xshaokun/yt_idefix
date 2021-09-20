from __future__ import annotations

import os
import re
import warnings
import weakref
from abc import ABC, abstractmethod
from typing import BinaryIO

import inifix
import numpy as np

from yt.data_objects.index_subobjects.grid_patch import AMRGridPatch
from yt.data_objects.static_output import Dataset
from yt.funcs import setdefaultattr
from yt.geometry.grid_geometry_handler import GridIndex

from ._io import dmp_io, vtk_io
from ._io.commons import IdefixFieldProperties, IdefixMetadata
from .fields import IdefixFieldInfo

_IDEFIX_VERSION_REGEXP = re.compile(r"v\d+\.\d+\.?\d*[-\w+]*")


class IdefixGrid(AMRGridPatch):
    _id_offset = 0

    def __init__(self, id, index, level, dims):
        super().__init__(id, filename=index.index_filename, index=index)
        self.Parent = None
        self.Children = []
        self.Level = level
        self.ActiveDimensions = dims

    def __repr__(self):
        return "IdefixGrid_%04i (%s)" % (self.id, self.ActiveDimensions)


class IdefixHierarchy(GridIndex, ABC):
    grid = IdefixGrid

    def __init__(self, ds, dataset_type="idefix"):
        self.dataset_type = dataset_type
        self.dataset = weakref.proxy(ds)
        # for now, the index file is the dataset!
        self.index_filename = self.dataset.parameter_filename
        self.directory = os.path.dirname(self.index_filename)
        # float type for the simulation edges and must be float64 now
        self.float_type = np.float64
        super().__init__(ds, dataset_type)

    def _detect_output_fields(self):
        self.field_list = [
            (self.dataset_type, f) for f in self.dataset._detected_field_list
        ]

    def _count_grids(self):
        self.num_grids = 1

    def _parse_index(self):
        self.grid_left_edge[0][:] = self.ds.domain_left_edge[:]
        self.grid_right_edge[0][:] = self.ds.domain_right_edge[:]
        self.grid_dimensions[0][:] = self.ds.domain_dimensions[:]
        self.grid_particle_count[0][0] = 0
        self.grid_levels[0][0] = 1
        self.max_level = 1

        cls = self.__class__
        with open(self.ds.parameter_filename, "rb") as fh:
            self._field_offsets = cls._get_field_offset_index(fh)

    def _populate_grid_objects(self):
        # the minimal form of this method is
        #
        # for g in self.grids:
        #     g._prepare_grid()
        #     g._setup_dx()
        #
        # This must also set:
        #   g.Children <= list of child grids
        #   g.Parent   <= parent grid
        # This is handled by the frontend because often the children must be identified.
        self.grids = np.empty(self.num_grids, dtype="object")
        for i in range(self.num_grids):
            g = self.grid(i, self, self.grid_levels.flat[i], self.grid_dimensions[i])
            g._prepare_grid()
            g._setup_dx()
            self.grids[i] = g

    @staticmethod
    @abstractmethod
    def _get_field_offset_index(fh: BinaryIO) -> dict[str, int]:
        pass


class IdefixVtkHierarchy(IdefixHierarchy):
    @staticmethod
    def _get_field_offset_index(fh: BinaryIO) -> dict[str, int]:
        return vtk_io.get_field_offset_index(fh)


class IdefixDmpHierarchy(IdefixHierarchy):
    @staticmethod
    def _get_field_offset_index(fh: BinaryIO) -> dict[str, int]:
        return dmp_io.get_field_offset_index(fh)


class IdefixDataset(Dataset, ABC):
    """A common abstraction for IdefixDmpDataset and IdefixVtkDataset."""

    def __init__(
        self,
        dmpfile,
        inifile=None,
        dataset_type="idefix",
        unit_system="cgs",
        units_override=None,
    ):
        self.fluid_types += ("idefix",)
        super().__init__(
            dmpfile,
            dataset_type,
            units_override=units_override,
            unit_system=unit_system,
        )
        self.inifile = inifile
        self._parse_inifile()

        self.storage_filename = None

        # idefix does not support grid refinement
        self.refine_by = 1

    def _parse_parameter_file(self):

        fprops, fdata = self._get_fields_metadata()
        self._detected_field_list = [k for k in fprops if re.match(r"^V[sc]-", k)]

        # parse the version hash
        self.parameters["idefix version"] = self._get_idefix_version()

        # parse the grid
        axes = ("x1", "x2", "x3")
        self.domain_dimensions = np.concatenate([fprops[k][-1] for k in axes])
        self.dimensionality = np.count_nonzero(self.domain_dimensions - 1)

        # note that domain edges parsing is already implemented in a mutli-block
        # supporting fashion even though we specifically error out in case there's more
        # than one block.
        self.domain_left_edge = np.array(
            [fdata[f"xl{idir}"][0] for idir in "123"], dtype="float64"
        )
        self.domain_right_edge = np.array(
            [fdata[f"xr{idir}"][-1] for idir in "123"], dtype="float64"
        )

        self.current_time = fdata["time"]

        self._periodicity = tuple(bool(p) for p in fdata["periodicity"])
        enum_geoms = {1: "cartesian", 2: "cylindrial", 3: "polar", 4: "spherical"}
        self.geometry = enum_geoms[fdata["geometry"]]

        # idefix is never cosmological
        self.cosmological_simulation = 0
        self.current_redshift = 0.0
        self.omega_lambda = 0.0
        self.omega_matter = 0.0
        self.hubble_constant = 0.0

    def _parse_inifile(self) -> None:
        if self.inifile is None:
            warnings.warn(
                "Cannot validate grid structure. "
                "Please pass the `inifile` keyword argument to `yt.load`"
            )
            return

        self.parameters.update(inifix.load(self.inifile))
        grid_ini = self.parameters["Grid"]

        msg_elems: list[str] = []
        for ax, vals in grid_ini.items():
            if vals[0] > 1:
                # more than one block is only relevant for mixing grid spacings,
                # but only "u" is supported
                msg_elems.append(f"found multiple blocks in direction {ax}; got {vals}")
            if any(_ != "u" for _ in vals[3::3]):
                msg_elems.append(f"found non-uniform block(s) in direction {ax}")
        if len(msg_elems) > 0:
            msg = (
                "yt + yt_idefix currently only supports a single block "
                "with uniform spacing in each direction. Got the following issue(s)\n"
                + "- "
                + "\n- ".join(msg_elems)
                + "\nThe grid will be treated as uniformly spaced in every direction. "
                "Only the domain edges are expected to be correctly parsed."
            )
            warnings.warn(msg)

    def _set_code_unit_attributes(self):
        # This is where quantities are created that represent the various
        # on-disk units.  These are the currently available quantities which
        # should be set, along with examples of how to set them to standard
        # values.
        #
        # self.length_unit = self.quan(1.0, "cm")
        # self.mass_unit = self.quan(1.0, "g")
        # self.time_unit = self.quan(1.0, "s")
        # self.time_unit = self.quan(1.0, "s")
        #
        # These can also be set:
        # self.velocity_unit = self.quan(1.0, "cm/s")
        # self.magnetic_unit = self.quan(1.0, "gauss")
        for key, unit in self.__class__.default_units.items():
            setdefaultattr(self, key, self.quan(1, unit))

    @abstractmethod
    def _get_fields_metadata(self) -> tuple[IdefixFieldProperties, IdefixMetadata]:
        pass

    @abstractmethod
    def _get_idefix_version(self) -> str:
        pass


class IdefixVtkDataset(IdefixDataset):
    _index_class = IdefixVtkHierarchy
    _field_info_class = IdefixFieldInfo

    @classmethod
    def _is_valid(cls, fn, *args, **kwargs) -> bool:
        try:
            header = vtk_io.read_header(fn)
        except Exception:
            return False
        else:
            return "Idefix" in header


class IdefixDmpDataset(IdefixDataset):
    _index_class = IdefixDmpHierarchy
    _field_info_class = IdefixFieldInfo

    @classmethod
    def _is_valid(cls, fn, *args, **kwargs):
        ok = bool(
            re.match(r"^(dump)\.\d{4}(\.dmp)$", os.path.basename(fn))
        )  # this is possibly too restrictive
        try:
            ok &= "idefix" in dmp_io.read_header(fn).lower()
        except Exception:
            ok = False
        return ok

    def _get_fields_metadata(self) -> tuple[IdefixFieldProperties, IdefixMetadata]:
        # read everything except large arrays
        return dmp_io.read_idefix_dmpfile(self.parameter_filename, skip_data=True)

    def _get_idefix_version(self) -> str:
        header = dmp_io.read_header(self.parameter_filename)

        match = re.search(_IDEFIX_VERSION_REGEXP, header)
        version: str
        if match is None:
            warnings.warn(
                f"Could not determine Idefix version from file header {header!r}"
            )
            version = "unknown"
        else:
            version = match.group()
        return version
