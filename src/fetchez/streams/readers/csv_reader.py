#!/usr/bin/env python

"""
fetchez.streams.readers.csv_reader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Basic CSV reader to create a generic 'list' stream.

:copyright: (c) 2016 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import csv

from fetchez.utils import int_or, str_or

from .base import BaseReader


class CSVReader(BaseReader):
    name = "csvreader"
    meta_dtype = "csv"
    meta_extensions = ["csv"]
    meta_desc = "Read and stream CSV data as list or dict."
    meta_category = "list-stream"

    def __init__(
        self,
        path,
        newline="",
        encoding="utf-8",
        as_dict=False,
        delimiter=",",
        quotechar=None,
        fields=None,
        skiplines=0,
        **kwargs,
    ):
        super().__init__(path, **kwargs)
        self.newline = newline
        self.encoding = encoding
        self.as_dict = as_dict
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.fields = fields or []
        self.skiplines = skiplines

    def _read_chunks(self):
        reader = csv.reader
        fields = [int_or(x) for x in self.fields]
        if not all(fields):
            fields = [str_or(x) for x in self.fields]
            reader = csv.DictReader

        with open(
            self.path, mode="r", newline=self.newline, encoding=self.encoding
        ) as file:
            for chunk in reader(file, delimiter=self.delimiter):
                if self.skiplines > 0:
                    self.skiplines -= 1
                    continue
                if fields:
                    chunk = [chunk[n] for n in fields]
                yield chunk

        # with open(self.path, 'r') as f:
        #     reader = csv.reader(f, delimiter=self.delimiter)
        #     while True:
        #         # Pull 10 rows at a time
        #         chunk = list(itertools.islice(reader, self.chunksize))
        #         if not chunk:
        #             break

        #         yield chunk
