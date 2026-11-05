#!/usr/bin/env python3
import struct, sys, os

SPARSE_HEADER_MAGIC = 0xED26FF3A
CHUNK_TYPE_RAW = 0xCAC1
CHUNK_TYPE_DONT_CARE = 0xCAC3
BLK_SIZE = 4096

def convert_to_sparse(in_path, out_path):
    file_size = os.path.getsize(in_path)
    assert file_size % BLK_SIZE == 0, "Input size must be 4096-aligned"
    total_blks = file_size // BLK_SIZE

    zero_block = b"\x00" * BLK_SIZE

    chunks = [] # list of (type, num_blks, data_or_none)

    with open(in_path, "rb") as f:
        blk_idx = 0
        cur_type = None
        cur_count = 0
        cur_raw_data = []

        while blk_idx < total_blks:
            block = f.read(BLK_SIZE)
            if not block:
                break
            is_zero = (block == zero_block)
            this_type = CHUNK_TYPE_DONT_CARE if is_zero else CHUNK_TYPE_RAW

            if cur_type is None:
                cur_type = this_type
                cur_count = 1
                if cur_type == CHUNK_TYPE_RAW:
                    cur_raw_data.append(block)
            elif cur_type == this_type and cur_count < 65535:
                cur_count += 1
                if cur_type == CHUNK_TYPE_RAW:
                    cur_raw_data.append(block)
            else:
                chunks.append((cur_type, cur_count, b"".join(cur_raw_data) if cur_type == CHUNK_TYPE_RAW else None))
                cur_type = this_type
                cur_count = 1
                cur_raw_data = [block] if cur_type == CHUNK_TYPE_RAW else []

            blk_idx += 1

        if cur_type is not None:
            chunks.append((cur_type, cur_count, b"".join(cur_raw_data) if cur_type == CHUNK_TYPE_RAW else None))

    # Write sparse file
    with open(out_path, "wb") as out:
        # File header
        header = struct.pack(
            "<IHHHHIIII",
            SPARSE_HEADER_MAGIC,
            1, # major
            0, # minor
            28, # file_hdr_sz
            12, # chunk_hdr_sz
            BLK_SIZE,
            total_blks,
            len(chunks),
            0 # checksum
        )
        out.write(header)

        for c_type, c_blks, data in chunks:
            if c_type == CHUNK_TYPE_RAW:
                total_sz = 12 + len(data)
                out.write(struct.pack("<HHII", c_type, 0, c_blks, total_sz))
                out.write(data)
            else: # DONT_CARE
                total_sz = 12
                out.write(struct.pack("<HHII", c_type, 0, c_blks, total_sz))

    in_mb = file_size / (1024*1024)
    out_mb = os.path.getsize(out_path) / (1024*1024)
    print(f"Sparse conversion complete: {in_mb:.1f} MB -> {out_mb:.1f} MB ({len(chunks)} chunks)")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.raw> <output.simg>")
        sys.exit(1)
    convert_to_sparse(sys.argv[1], sys.argv[2])
