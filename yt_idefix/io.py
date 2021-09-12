from abc import ABC, abstractmethod
from typing import BinaryIO

import numpy as np

from yt.utilities.io_handler import BaseIOHandler

from ._io import dmp_io


class IdefixIOHandler(BaseIOHandler, ABC):
    _particle_reader = False
    _dataset_type = "idefix"

    def __init__(self, ds):
        BaseIOHandler.__init__(self, ds)
        self.ds = ds
        self.dmpfile = ds.parameter_filename

    def _read_fluid_selection(self, chunks, selector, fields, size):
        data = {}
        offset = 0

        cls = self.__class__
        with open(self.dmpfile, mode="rb") as fh:
            for field in fields:
                ftype, fname = field
                data[ftype, fname] = np.empty(size, dtype="float64")
                for chunk in chunks:
                    for grid in chunk.objs:
                        foffset = grid._index._field_offsets[fname]
                        values = cls._read_single_field(fh, foffset)
                        offset += grid.select(selector, values, data[field], offset)
        return data

    @staticmethod
    @abstractmethod
    def _read_single_field(fh: BinaryIO, offset: int) -> np.ndarray:
        pass

    def _read_particle_coords(self, chunks, ptf):
        # This needs to *yield* a series of tuples of (ptype, (x, y, z)).
        # chunks is a list of chunks, and ptf is a dict where the keys are
        # ptypes and the values are lists of fields.
        raise NotImplementedError("Particles are not currently supported for Idefix")

    def _read_particle_fields(self, chunks, ptf, selector):
        # idefix doesn't have particles (yet)
        raise NotImplementedError("Particles are not currently supported for Idefix")

    def _read_chunk_data(self, chunk, fields):
        # This reads the data from a single chunk without doing any selection,
        # and is only used for caching data that might be used by multiple
        # different selectors later. For instance, this can speed up ghost zone
        # computation.
        raise NotImplementedError


class IdefixVtkIOHandler(IdefixIOHandler):
    ...


class IdefixDmpIOHandler(IdefixIOHandler):
    @staticmethod
    def _read_single_field(fh: BinaryIO, offset: int) -> np.ndarray:
        return dmp_io.read_single_field(fh, offset)
