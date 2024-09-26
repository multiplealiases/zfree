# zfree

A zram swap-aware `free`-alike, or: mashing `free` and `zramctl` together.

## Usage

```console
$ ./zfree
total   used    available  free   comptotal  compdata  compratio
23416M  15365M  10195M     8050M  632M       2059M     3.26
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

* Only displays stats in MiB.

* Dies if no zram swap devices exist.

* Unaware of disk-based swap.

* Unaware of zswap (not to be confused with zram, which is supported).

* Stats diverge from `procps-ng` `free` for reasons I don't understand.
