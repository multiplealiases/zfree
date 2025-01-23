# zfree

A zram swap-aware `free`-alike, or: mashing `free` and `zramctl` together. Now in Python!

## Usage

```console
$ zfree -h
Memory/swap
      total       used      avail      cache       free
    22.9GiB     7.0GiB    14.5GiB     3.8GiB    12.1GiB
  1024.0MiB       0.0B                        1024.0MiB
zram
       data      total      ratio
     0.0MiB     0.0MiB        0.2
psi some/full: 0.00, 0.00, 0.00 / 0.00, 0.00, 0.00
```

## Dependencies

A list of dependencies and why they're here:

* Linux kernel 3.14+: the script peeks at Linux-specific files and
  requires the `MemAvailable` field to be present in `/proc/meminfo`.

* Python 3.6+: f-strings.

## Install

* Copy `./src/zfree.py` to somewhere in PATH under the name `zfree`.

* Use pipx, `pipx install .` (haven't published to PyPI yet)

* Distro packages don't yet exist,
  but I plan on publishing to Gentoo's GURU at least.

## Compatibility

Currently untested, but the script
is meant to work on the following platforms:

* All Linux distributions (glibc, musl, future libcs)
  shipping Python 3.6+ and kernel 3.14+.

RHEL 7 and older are unsupported because those ship kernels older than 3.14.

## Limitations

* Only handles a maximum of 1 zram swap device and 1 disk swap device.

* Unaware of zswap (not to be confused with zram, which is supported).

* Stats diverge from `procps-ng` `free` for reasons I don't understand.
