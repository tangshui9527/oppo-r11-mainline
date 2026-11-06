#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <sys/syscall.h>
#include <linux/reboot.h>

#define IMEM_BASE 0x146bf000
#define REBOOT_OFFSET 0x65c

#define REASON_NORMAL     0x77665501
#define REASON_BOOTLOADER 0x77665500
#define REASON_RECOVERY   0x77665502
#define REASON_EDL        0x776655ee

int main(int argc, char **argv) {
    uint32_t magic = REASON_BOOTLOADER;
    const char *target = "bootloader";

    if (argc > 1) {
        if (!strcmp(argv[1], "recovery")) {
            magic = REASON_RECOVERY;
            target = "recovery";
        } else if (!strcmp(argv[1], "edl")) {
            magic = REASON_EDL;
            target = "edl";
        } else if (!strcmp(argv[1], "normal")) {
            magic = REASON_NORMAL;
            target = "normal";
        } else if (!strcmp(argv[1], "bootloader") || !strcmp(argv[1], "fastboot")) {
            magic = REASON_BOOTLOADER;
            target = "bootloader";
        } else {
            fprintf(stderr, "Usage: %s [bootloader|fastboot|recovery|edl|normal]\n", argv[0]);
            return 1;
        }
    }

    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("open /dev/mem");
        return 1;
    }

    void *map = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, IMEM_BASE);
    if (map == MAP_FAILED) {
        perror("mmap IMEM");
        close(fd);
        return 1;
    }

    volatile uint32_t *reason = (volatile uint32_t *)((char *)map + REBOOT_OFFSET);
    printf("[*] Previous IMEM[0x65c] was: 0x%08x\n", *reason);
    *reason = magic;
    printf("[+] Wrote 0x%08x (%s) -> Verified: 0x%08x\n", magic, target, *reason);

    msync((void *)map, 0x1000, MS_SYNC);
    munmap(map, 0x1000);
    close(fd);

    printf("[*] Syncing filesystems and triggering hardware restart...\n");
    sync();
    syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2, LINUX_REBOOT_CMD_RESTART2, target);
    syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2, LINUX_REBOOT_CMD_RESTART);
    return 0;
}
