import os, sys

# 1. Patch storage.c
with open('rmtfs/storage.c', 'r') as f:
    s = f.read()

oppo_str = """\t{ "/boot/modem_fsg_oem_1", "modem_fsg_oem_1", "oppostanvbk" },\n\t{ "/boot/modem_fsg_oem_2", "modem_fsg_oem_2", "oppodycnvbk" },\n"""
if '/boot/modem_fsg_oem_1' not in s:
    s = s.replace('\t/* OnePlus/Oppo OEM NV backup partitions */', oppo_str + '\t/* OnePlus/Oppo OEM NV backup partitions */')

with open('rmtfs/storage.c', 'w') as f:
    f.write(s)

# 2. Patch sharedmem.c: allow relative addresses
with open('rmtfs/sharedmem.c', 'r') as f:
    sm = f.read()

# in rmtfs_mem_ptr:
old_ptr = "static void *rmtfs_mem_ptr(struct rmtfs_mem *rmem, unsigned long phys_address, ssize_t len)\n{"
new_ptr = """static void *rmtfs_mem_ptr(struct rmtfs_mem *rmem, unsigned long phys_address, ssize_t len)
{
\tif (rmem && phys_address < rmem->size)
\t\tphys_address += rmem->address;"""

if 'if (rmem && phys_address < rmem->size)' not in sm:
    sm = sm.replace(old_ptr, new_ptr)

# in rmtfs_mem_write/read pread/pwrite:
old_off = "\toffset = phys_address - rmem->address;"
new_off = """\tif (phys_address < rmem->size)
\t\tphys_address += rmem->address;
\toffset = phys_address - rmem->address;"""

if 'if (phys_address < rmem->size)' not in sm:
    sm = sm.replace(old_off, new_off)

with open('rmtfs/sharedmem.c', 'w') as f:
    f.write(sm)

print("rmtfs patched successfully!")
