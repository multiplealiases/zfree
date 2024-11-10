# zfree

A zram swap-aware `free`-alike, or: mashing `free` and `zramctl` together.

## Usage

```console
$ ./zfree
            total       used  available   bufcache       free   compdata  comptotal  compratio
Mem:        7548M      5553M      2429M      1826M       168M      1595M       156M      10.17
```

## Dependencies

A list of dependencies and why they're here:

* Linux kernel: non-negotiable, this script peeks at Linux-specific files.

* POSIX shell and standard associated utilities: this is a shell script.

The previous dependencies on Bash, GNU coreutils, and util-linux have
been removed for portabiity.

# Compatibility

Apart from the Linux kernel, `zfree` attempts to only rely on
portable constructs, and should work on the base installations
of the following:

* GNU/Linux distributions (Debian, Ubuntu, many others)

* Linux distributions using BusyBox (Alpine Linux and friends)

* Linux distributions using FreeBSD tools (Chimera Linux)

Incompatibility with any of these platforms is a bug;
please file a GitHub Issue.

## Limitations

* Cannot handle multiple zram swap devices, only the first displayed
  by `/proc/swaps` (I believe this is a rare configuration?)

* ~~Only displays stats in MiB.~~
  Now supports units, but `-h`/`--human-readable` isn't yet implemented.

* ~~Dies if no zram swap devices exist.~~

* Unaware of disk-based swap.

* Unaware of zswap (not to be confused with zram, which is supported).

* Stats diverge from `procps-ng` `free` for reasons I don't understand.
