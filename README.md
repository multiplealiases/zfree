# zfree

A zram swap-aware `free`-alike.

## Usage

```console
$ ./zfree
total   used    available  free   comptotal  compdata  compratio
23416M  15365M  10195M     8050M  632M       2059M     3.26
```

## Dependencies

A list of dependencies and why they're here:

* Linux kernel: non-negotiable, this script peeks at Linux-specific files.

* Bash: not sure. Should be able to remove what few Bashisms there are.

* GNU coreutils: argument parsing (`getopt`) and `-0`/`--null` flags.
  Good chance these can be replaced with more portable constructs.

* util-linux: formatting the output into a `free`-like table (`column`).
  Maybe this could be replaced with `printf`, but offets would need
  to be manually updated each time the output gets changed.

## Limitations

* Cannot handle multiple zram swap devices, only the first displayed
  by `/proc/swaps` (I believe this is a rare configuration?)

* Only displays stats in MiB.

* Dies if no zram swap devices exist.

* Unaware of disk-based swap.

* Stats diverge from `procps-ng` `free` for reasons I don't understand.
