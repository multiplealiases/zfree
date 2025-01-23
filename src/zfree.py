#!/usr/bin/env python3
"""A zram-aware free-alike"""
# python3 because some very old distros do python-is-python2

import operator
import argparse
import sys
import re
import math

# one-number pride versioning:
# increment every time the author is proud of the release
__version__ = "4"


def check_open_read(f: str) -> str:
    """
    Open and read a file into a string.
    Returns None if it encounters an OSError because
    the script may be able to continue without some of them.
    """
    try:
        ret = open(f, "r", encoding="utf-8").read().rstrip()
        return ret
    except OSError:
        return None


def gather() -> (str, str, str):
    """
    Gather all required files and read them into strings.
    (API files have ephemeral and ever-changing contents,
    so their contents should be *read* to a string as soon as possible)
    """
    meminfo = check_open_read("/proc/meminfo")
    swaps = check_open_read("/proc/swaps")
    psi_memory = check_open_read("/proc/pressure/memory")
    return meminfo, swaps, psi_memory


def gather_zram_mmstat(swaps) -> str:
    """
    Try to find a zram swap device and return its mm_stat.
    """
    try:
        # Having more than 1 zram swap device is uncommon and unsupported.
        cols = re.search(R".*zram.*", swaps, flags=re.MULTILINE).group(0).split()
        dev = cols[0].split("/")[2]
        path = f"/sys/class/block/{dev}/mm_stat"
        # use open() instead of check_open_read()
        # because the latter eats any potential OSError and returns None.
        return open(path, "r", encoding="utf-8").read().rstrip()
    # if the search for zram swap turns up blank
    except AttributeError:
        return None
    except IndexError:
        sys.exit("Internal error: /proc/swaps not in expected format")
    except OSError:
        sys.exit(
            f"Internal error: tried to find zram swap mm_stat, but {path} doesn't exist"
        )


def parse_disk_swap(swaps) -> (int, int, int):
    """
    Parse /proc/swaps for disk swap total and used.
    Units are in KiB.
    """
    try:
        swaprow = None
        # split by lines, then remove the column headings
        trimmed = swaps.split("\n")[1:]

        for row in trimmed:
            if not re.search(R".*zram.*", row):
                if swaprow is not None:
                    sys.exit("Error: having multiple disk swap devices is unsupported")
                swaprow = row

        if swaprow is None:
            return None, None, None
        cols = swaprow.split()
        total = int(cols[2])
        used = int(cols[3])
        free = total - used
        return total, used, free
    except IndexError:
        sys.exit("Internal error: /proc/swaps not in expected format")


def parse_zram_swap(mmstat) -> (int, int, float):
    """
    Parse the equivalents to zramctl COMPDATA and COMPTOTAL
    and calculates the compression ratio out of the zram swap mm_stat.
    data and total are in bytes.
    """
    m = mmstat.split()
    data = int(m[0])
    total = int(m[2])
    try:
        ratio = data / total
    except ZeroDivisionError:
        # handle zero division gracefully
        ratio = None
    return data, total, ratio


def parse_meminfo(meminfo) -> (int, int, int, int, int):
    """
    Parse meminfo for memory information.
    Values in KiB.
    """
    memdict = {}
    for s in meminfo.split("\n"):
        key, value = s.split(":")
        # strip the units
        memdict[key] = int(value.lstrip().split()[0])

    total = memdict["MemTotal"]
    try:
        available = memdict["MemAvailable"]
    except KeyError:
        sys.exit("MemAvailable in /proc/meminfo absent. How old is this kernel?")
    free = memdict["MemFree"]
    bufcache = memdict["Buffers"] + memdict["Cached"]
    used = total - free - bufcache
    return total, available, free, bufcache, used


def trim_equals(x):
    return float(x.split("=")[1])


def parse_psi(psi):
    """
    Parse the output of /proc/pressure/* files.
    """
    some = map(trim_equals, psi.split("\n")[0].split()[1:4])
    full = map(trim_equals, psi.split("\n")[1].split()[1:4])
    psi_some_avg10, psi_some_avg60, psi_some_avg300 = list(some)[0:3]
    psi_full_avg10, psi_full_avg60, psi_full_avg300 = list(full)[0:3]
    return (
        psi_some_avg10,
        psi_some_avg60,
        psi_some_avg300,
        psi_full_avg10,
        psi_full_avg60,
        psi_full_avg300,
    )


def check_existence(meminfo, swaps, psi_memory) -> (bool, bool, bool):
    """
    Checks if the files from gather() exist
    and produces boolean flags indicating what to display.
    """

    # Right now these flags mean "can't" rather than "don't".
    # User arguments may disable these later.
    show_disk_swap = True
    show_zram_swap = True
    show_psi = True

    # Testing for absences
    # * no /proc/meminfo
    # * no /proc/swaps
    # * no /proc/pressure/memory
    if meminfo is None:
        sys.exit("No /proc/meminfo. Cannot proceed. Is /proc mounted?")

    if swaps is None:
        # /proc/swaps is absent?
        # Continuing without swap stats,
        # but that seems odd to me.
        show_disk_swap = False
        show_zram_swap = False

    if psi_memory is None:
        show_psi = False

    return (show_disk_swap, show_zram_swap, show_psi)


# the following is adapted from code under MIT by Síle Ekaterin Liszka
# this function is typically called "humanize()", but I refuse such notions.
def autorange(value, in_unit, want_decimal) -> (float, str):
    """
    Perform autoranging on data quantities.
    """
    mappingbinary = ["B", "KiB", "MiB", "GiB"]
    mappingdecimal = ["B", "KB", "MB", "GB"]
    radix = 1000 if want_decimal else 1024
    length = math.ceil(math.log(value + 1, radix))
    length = min(length, 3)

    if want_decimal:
        return convert(value, in_unit, mappingdecimal[length])
    else:
        return convert(value, in_unit, mappingbinary[length])


def convert(value, in_unit, out_unit):
    """
    Convert between in_unit and out_unit.
    """
    prefixes = {
        "B": 1,
        "KB": 1000,
        "KiB": 2**10,
        "MB": 1000_000,
        "MiB": 2**20,
        "GB": 1000_000_000,
        "GiB": 2**30,
    }

    # this is fine enough for me.
    if value is None:
        return None, None

    if in_unit in ("autodecimal", "autobinary"):
        sys.exit('Internal error: cannot infer input unit (misplaced "auto"?)')

    if out_unit == "autodecimal":
        return autorange(value, in_unit, True)

    if out_unit == "autobinary":
        return autorange(value, in_unit, False)

    return value * (prefixes[in_unit] / prefixes[out_unit]), out_unit


def format_value_unit(vu):
    try:
        return f"{vu[0]:.1f}{vu[1]}"
    except (IndexError, TypeError):
        return None


def format_meminfo(
    total,
    available,
    free,
    bufcache,
    used,
    disk_swap_total,
    disk_swap_used,
    disk_swap_free,
    show_disk_swap,
    width,
) -> str:
    ret = ""

    fmt = f"{{0:>{width}}}"

    ret += f"Memory{'/swap' if show_disk_swap else ''}\n"

    meminfohead = ["total", "used", "avail", "cache", "free"]
    meminfo = [total, used, available, bufcache, free]
    meminfo = list(map(format_value_unit, meminfo))

    swapinfo = [disk_swap_total, disk_swap_used, disk_swap_free]
    swapinfo = list(map(format_value_unit, swapinfo))
    swapinfo = swapinfo[0:2] + ["", ""] + swapinfo[2:]

    for h in meminfohead:
        ret += fmt.format(h)
    ret += "\n"
    for m in meminfo:
        ret += fmt.format(m)
    if show_disk_swap:
        ret += "\n"
        for s in swapinfo:
            ret += fmt.format(s)
    return ret


def format_zram(total, data, ratio, width):
    fmt = f"{{0:>{width}}}"
    ret = ""
    ret += "zram\n"

    zhead = ["data", "total", "ratio"]
    zinfo = [format_value_unit(data), format_value_unit(total), f"{ratio:.2f}"]

    for h in zhead:
        ret += fmt.format(h)
    ret += "\n"
    for z in zinfo:
        ret += fmt.format(z)

    return ret


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-k", "--kibi", help="show output in kibibytes", action="store_true"
    )
    parser.add_argument(
        "-K", "--kilo", help="show output in kilobytes", action="store_true"
    )
    parser.add_argument(
        "-m", "--mebi", help="show output in mebibytes", action="store_true"
    )
    parser.add_argument(
        "-M", "--mega", help="show output in megabytes", action="store_true"
    )
    parser.add_argument(
        "-g", "--gibi", help="show output in gibibytes", action="store_true"
    )
    parser.add_argument(
        "-G", "--giga", help="show output in gigabytes", action="store_true"
    )
    parser.add_argument(
        "-h", help='do autoranging ("human-readable")', action="store_true"
    )
    parser.add_argument(
        "--si",
        "--decimal",
        help="(-h only) use powers of 1000 not 1024",
        action="store_true",
    )
    parser.add_argument(
        "-w", "--width", help="output width of each column", type=int, default=11
    )
    parser.add_argument("--help", help="this help", action="help")
    args = parser.parse_args()

    units = {
        "KiB": args.kibi,
        "KB": args.kilo,
        "MiB": args.mebi,
        "MB": args.mega,
        "GiB": args.gibi,
        "GB": args.giga,
        "auto": args.h,
    }
    unitsenabled = operator.countOf(units.values(), True)
    if unitsenabled > 1:
        sys.exit("error: cannot specify more than 1 unit")
    if unitsenabled == 0:
        unit = "MiB"
    else:
        # select the unit for which args.* is True
        unit = [k for k, v in units.items() if v][0]

    if args.si and unit != "auto":
        sys.exit("error: --si/--decimal only has effect in combination with -h.")
    if unit == "auto":
        if args.si:
            unit = "autodecimal"
        else:
            unit = "autobinary"

    if sys.platform != "linux":
        sys.exit("zfree can only run on Linux.")
    meminfo, swaps, psi_memory = gather()
    show_disk_swap, show_zram_swap, show_psi = check_existence(
        meminfo, swaps, psi_memory
    )

    if show_zram_swap is True:
        mm_stat = gather_zram_mmstat(swaps)
    else:
        mm_stat = None
    # /proc/swaps present, but no zram swap found
    if mm_stat is None:
        show_zram_swap = False

    if show_psi is True:
        (
            psi_some_avg10,
            psi_some_avg60,
            psi_some_avg300,
            psi_full_avg10,
            psi_full_avg60,
            psi_full_avg300,
        ) = parse_psi(psi_memory)

    # Declare ahead of time for devices without accessible /proc/swaps
    # (e.g. Android phones under Termux)
    disk_swap_total = (None, None)
    disk_swap_used = (None, None)
    disk_swap_free = (None, None)
    if show_disk_swap is True:
        disk_swap_total, disk_swap_used, disk_swap_free = parse_disk_swap(swaps)
        disk_swap_total = convert(disk_swap_total, "KiB", unit)
        disk_swap_used = convert(disk_swap_used, "KiB", unit)
        disk_swap_free = convert(disk_swap_free, "KiB", unit)
    # if parse_disk_swap turns up empty, don't bother showing info
    if disk_swap_total[0] is None:
        show_disk_swap = False

    if show_zram_swap is True:
        zram_swap_data, zram_swap_total, zram_swap_ratio = parse_zram_swap(mm_stat)
        zram_swap_data = convert(zram_swap_data, "B", unit)
        zram_swap_total = convert(zram_swap_total, "B", unit)

    total, available, free, bufcache, used = parse_meminfo(meminfo)

    total = convert(total, "KiB", unit)
    available = convert(available, "KiB", unit)
    free = convert(free, "KiB", unit)
    bufcache = convert(bufcache, "KiB", unit)
    used = convert(used, "KiB", unit)

    output = format_meminfo(
        total,
        available,
        free,
        bufcache,
        used,
        disk_swap_total,
        disk_swap_used,
        disk_swap_free,
        show_disk_swap,
        args.width,
    )

    if show_zram_swap is True:
        output += "\n"
        output += format_zram(
            zram_swap_total, zram_swap_data, zram_swap_ratio, args.width
        )

    if show_psi:
        output += f"\npsi some/full: {psi_some_avg10:.2f}, {psi_some_avg60:.2f}, {psi_some_avg300:.2f} / {psi_full_avg10:.2f}, {psi_full_avg60:.2f}, {psi_full_avg300:.2f}"

    print(output)


if __name__ == "__main__":
    main()
