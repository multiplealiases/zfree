# zfree

A zram swap-aware `free`-alike.

## Usage

```console
$ ./zfree
total   used    available  free   comptotal  compdata  compratio
23416M  15365M  10195M     8050M  632M       2059M     3.26
```

## Limitations

* Cannot handle multiple zram swap devices, only the first displayed
  by `/proc/swaps` (I believe this is a rare configuration)

* Only displays stats in MiB.

* Dies if no zram swap devices exist.

* Unaware of disk-based swap.

* Stats diverge from `procps-ng` `free` for reasons I don't understand.
