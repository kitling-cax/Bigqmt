"""Normalize PE metadata that makes otherwise identical tray builds differ.

The legacy .NET Framework compiler writes the current time into the COFF
timestamp field.  Clearing that non-functional field makes the generated
tray binaries reproducible when source, compiler and icon inputs are the
same.  No code or resource bytes are changed.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path


FIXED_MVID = b"KITLING-BIGQMT01"


def _rva_to_offset(data: bytearray, pe_offset: int, rva: int) -> int:
    section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    section_table = pe_offset + 24 + optional_size
    for index in range(section_count):
        offset = section_table + index * 40
        virtual_size, virtual_address = struct.unpack_from("<II", data, offset + 8)
        raw_size, raw_pointer = struct.unpack_from("<II", data, offset + 16)
        span = max(virtual_size, raw_size)
        if virtual_address <= rva < virtual_address + span:
            return raw_pointer + (rva - virtual_address)
    raise ValueError(f"RVA is not mapped to a PE section: 0x{rva:x}")


def _normalise_mvid(data: bytearray, pe_offset: int) -> None:
    optional = pe_offset + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    data_directory = optional + (96 if magic == 0x10B else 112)
    cli_rva = struct.unpack_from("<I", data, data_directory + 14 * 8)[0]
    if not cli_rva:
        raise ValueError(".NET CLI directory is missing")
    cli_offset = _rva_to_offset(data, pe_offset, cli_rva)
    metadata_rva = struct.unpack_from("<I", data, cli_offset + 8)[0]
    metadata = _rva_to_offset(data, pe_offset, metadata_rva)
    if data[metadata:metadata + 4] != b"BSJB":
        raise ValueError(".NET metadata signature is missing")
    version_length = struct.unpack_from("<I", data, metadata + 12)[0]
    streams = struct.unpack_from("<H", data, metadata + 16 + version_length + 2)[0]
    cursor = metadata + 16 + version_length + 4
    guid_stream_offset = None
    tables_stream_offset = None
    for _ in range(streams):
        stream_offset, stream_size = struct.unpack_from("<II", data, cursor)
        cursor += 8
        name_start = cursor
        while data[cursor] != 0:
            cursor += 1
        name = bytes(data[name_start:cursor]).decode("ascii")
        cursor += 1
        while (cursor - metadata) % 4:
            cursor += 1
        if name == "#GUID":
            guid_stream_offset = metadata + stream_offset
        elif name in {"#~", "#-"}:
            tables_stream_offset = metadata + stream_offset
    if guid_stream_offset is None or tables_stream_offset is None:
        raise ValueError(".NET metadata tables or GUID stream is missing")
    heap_sizes = data[tables_stream_offset + 6]
    valid_mask = struct.unpack_from("<Q", data, tables_stream_offset + 8)[0]
    row_cursor = tables_stream_offset + 24
    row_counts = {}
    for table in range(64):
        if valid_mask & (1 << table):
            row_counts[table] = struct.unpack_from("<I", data, row_cursor)[0]
            row_cursor += 4
    if not row_counts.get(0):
        raise ValueError(".NET Module table is empty")
    string_index_size = 4 if heap_sizes & 0x01 else 2
    guid_index_size = 4 if heap_sizes & 0x02 else 2
    mvid_index_offset = row_cursor + 2 + string_index_size
    mvid_index = int.from_bytes(data[mvid_index_offset:mvid_index_offset + guid_index_size], "little")
    if mvid_index <= 0:
        raise ValueError(".NET Module MVID index is empty")
    guid_offset = guid_stream_offset + (mvid_index - 1) * 16
    data[guid_offset:guid_offset + 16] = FIXED_MVID


def normalize(path: Path) -> None:
    data = bytearray(path.read_bytes())
    if data[:2] != b"MZ" or len(data) < 0x40:
        raise ValueError(f"not a PE file: {path}")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 12 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"invalid PE signature: {path}")
    timestamp_offset = pe_offset + 8
    struct.pack_into("<I", data, timestamp_offset, 0)
    _normalise_mvid(data, pe_offset)
    path.write_bytes(data)


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit("usage: normalize_native_pe.py FILE [...]")
    for name in argv:
        normalize(Path(name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
