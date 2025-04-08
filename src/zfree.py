#!/usr/bin/env python3
"""A zram-aware free-alike"""
# python3 because some very old distros do python-is-python2

from collections import OrderedDict
import operator
import argparse
import sys
import re
import math
from typing import List, Optional, Tuple

# one-number pride versioning:
# increment every time the author is proud of the release
__version__ = "9"


def check_open_read(f: str) -> Optional[str]:
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


def gather() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Gather all required files and read them into strings.
    (API files have ephemeral and ever-changing contents,
    so their contents should be *read* to a string as soon as possible)
    """
    meminfo = check_open_read("/proc/meminfo")
    swaps = check_open_read("/proc/swaps")
    psi_memory = check_open_read("/proc/pressure/memory")
    return meminfo, swaps, psi_memory


def gather_zram_mmstat(swaps: str) -> Optional[str]:
    """
    Try to find a zram swap device and return its mm_stat.
    """
    try:
        # Having more than 1 zram swap device is uncommon and unsupported.
        search = re.search(R".*zram.*", swaps, flags=re.MULTILINE)
        # if the search for zram swap turns up blank
        if search is None:
            return None
        cols = search.group(0).split()
        dev = cols[0].split("/")[2]
        path = f"/sys/class/block/{dev}/mm_stat"
        # use open() instead of check_open_read()
        # because the latter eats any potential OSError and returns None.
        return open(path, "r", encoding="utf-8").read().rstrip()
    except IndexError:
        sys.exit("Internal error: /proc/swaps not in expected format")
    except OSError:
        sys.exit(
            f"Internal error: tried to find zram swap mm_stat, but {path} doesn't exist"
        )


def parse_disk_swap(swaps: str) -> Optional[OrderedDict]:
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
            return None
        cols = swaprow.split()
        total = int(cols[2])
        used = int(cols[3])
        free = total - used
        return OrderedDict(
            [
                ("total", (total, "KiB")),
                ("used", (used, "KiB")),
                ("free", (free, "KiB")),
            ]
        )
    except IndexError:
        sys.exit("Internal error: /proc/swaps not in expected format")


def parse_zram_swap(mmstat: str) -> OrderedDict:
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
    return OrderedDict(
        # ratio is simply unitless.
        [("data", (data, "B")), ("total", (total, "B")), ("ratio", (ratio, ""))]
    )


def parse_meminfo(meminfo: str) -> OrderedDict:
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
    used = total - available
    # Python 3.6 does not guarantee ordering of dictionaries.
    # This is only guaranteed starting with Python 3.7+.
    # CPython 3.6's dictionaries are only ordered as an impl. detail.
    return OrderedDict(
        [
            ("total", (total, "KiB")),
            ("used", (used, "KiB")),
            ("avail", (available, "KiB")),
            ("cache", (bufcache, "KiB")),
            ("free", (free, "KiB")),
        ]
    )


def trim_equals(x: str) -> float:
    return float(x.split("=")[1])


def parse_psi(psi: str) -> OrderedDict:
    """
    Parse the output of /proc/pressure/* files.
    """
    some = map(trim_equals, psi.split("\n")[0].split()[1:4])
    full = map(trim_equals, psi.split("\n")[1].split()[1:4])
    psi_some_avg10, psi_some_avg60, psi_some_avg300 = list(some)[0:3]
    psi_full_avg10, psi_full_avg60, psi_full_avg300 = list(full)[0:3]
    return OrderedDict(
        [
            ("some", [psi_some_avg10, psi_some_avg60, psi_some_avg300]),
            ("full", [psi_full_avg10, psi_full_avg60, psi_full_avg300]),
        ]
    )


# the following is adapted from code under MIT by Síle Ekaterin Liszka
# this function is typically called "humanize()", but I refuse such notions.
def autorange(
    n: Tuple[float, str], want_decimal: bool
) -> Tuple[Optional[float], Optional[str]]:
    """
    Perform autoranging on data quantities.
    """
    mappingbinary = ["B", "KiB", "MiB", "GiB", "TiB"]
    mappingdecimal = ["B", "KB", "MB", "GB", "TiB"]
    # the length calculation only works in bytes, so just convert to bytes.
    shiftvalue = convert(n, "B")[0]
    # 'not' is not the same as 'is None'.
    if shiftvalue is None:
        return (None, None)
    try:
        length = math.floor(math.log(shiftvalue, 1000))
    # the digit length of exactly 0 is 1,
    # and I don't know what to tell you
    # if you feed negative numbers into this.
    except ValueError:
        length = 0
    length = min(length, 4)

    if want_decimal:
        return convert(n, mappingdecimal[length])
    else:
        return convert(n, mappingbinary[length])


def convert(
    n: Tuple[float, str], out_unit: str
) -> Tuple[Optional[float], Optional[str]]:
    """
    Convert between in_unit and out_unit.
    Expected input is a tuple of (value, unit).
    """
    prefixes = {
        "B": 1,
        "KB": 1000,
        "KiB": 2**10,
        "MB": 1000_000,
        "MiB": 2**20,
        "GB": 1000_000_000,
        "GiB": 2**30,
        "TB": 1000_000_000_000,
        "TiB": 2**40,
    }
    value = n[0]
    in_unit = n[1]

    # passthrough for unitless values
    if in_unit == "":
        return (value, "")

    # this is fine enough for me.
    if value is None:
        return None, None

    if in_unit in ("autodecimal", "autobinary"):
        sys.exit('Internal error: cannot infer input unit (misplaced "auto"?)')

    if out_unit == "autodecimal":
        return autorange(n, True)

    if out_unit == "autobinary":
        return autorange(n, False)

    return value * (prefixes[in_unit] / prefixes[out_unit]), out_unit


def convert_all(d: OrderedDict, out_unit: str) -> OrderedDict:
    """
    Runs convert() on every key-value pair
    of an OrderedDict whose entries are in the form

        "name": (value, in_unit)

    such that each entry becomes

        "name": (value, out_unit)

    with the value appropriately converted, retaining insertion order.
    """
    ret = OrderedDict()
    for k, v in d.items():
        ret[k] = convert(v, out_unit)
    return ret


def format_value_unit(vu: Tuple[float, str], dp=1) -> str:
    """
    Formats a (value, unit) tuple into
    a string suitable for display, to dp decimal points.
    """
    return f"{vu[0]:.{dp}f}{vu[1]}"


def format_value_unit_all(d: OrderedDict) -> OrderedDict:
    """
    Runs format_value_unit() on every value
    of an OrderedDict whose entries are in the form

        "name": (value, unit)

    such that each entry becomes

        "name": f"{value}{unit}"

    retaining insertion order.
    """
    ret = OrderedDict()
    for k, v in d.items():
        ret[k] = format_value_unit(v)
    return ret


def format_table(t: List[List[str]], width) -> str:
    """
    Formats a list of lists in the following format:

    [
        [header, value, value, value],
        [header, value, value, value],
        [header, value, value, value],
        (...)
    ]

    into the string

    header header header
     value  value  value
     value  value  value
     value  value  value

    with the appropriate left-padding.

    Truncates to the shortest column;
    please give perfectly rectangular tables as input.

    Ensure that all fields are strings or trivially convertible to a string.
    """
    ret = ""
    for row in zip(*t):
        ret += "\n"
        for field in row:
            ret += f"{field:>{width}}"
    # strip off the first newline for consistency.
    return ret.lstrip("\n")


def format_meminfo(
    meminfo: OrderedDict,
    swapinfo: Optional[OrderedDict],
    show_disk_swap: bool,
    width: int,
) -> str:
    ret = ""

    meminfo = format_value_unit_all(meminfo)
    if swapinfo and show_disk_swap:
        swapinfo = format_value_unit_all(swapinfo)

    ret += f"Memory{'/swap' if (swapinfo and show_disk_swap) else ''}\n"

    table = []
    if swapinfo and show_disk_swap:
        for h in meminfo.keys():
            table += [[h, meminfo.get(h, ""), swapinfo.get(h, "")]]
    else:
        for h in meminfo.keys():
            table += [[h, meminfo.get(h, "")]]
    ret += format_table(table, width)
    return ret


def format_zram(zram_swap: OrderedDict, meminfo: OrderedDict, width: int) -> str:
    ret = ""
    ret += "zram\n"

    memtotal = convert(meminfo["total"], "B")[0]
    ztotal = convert(zram_swap["total"], "B")[0]
    if (memtotal is None) or (ztotal is None):
        sys.exit("internal error: total RAM or zram is None?")
    totalpercent = (ztotal / memtotal) * 100.0

    zram_swap = OrderedDict(
        [
            ("data", format_value_unit(zram_swap["data"])),
            ("total", format_value_unit(zram_swap["total"])),
            ("ratio", format_value_unit(zram_swap["ratio"], dp=2)),
            ("comp%", format_value_unit((totalpercent, "%"), dp=2))
        ]
    )

    table = []
    for h in zram_swap.keys():
        table += [[h, zram_swap.get(h, "")]]

    ret += format_table(table, width)

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
        "--tera", help="show output in terabytes", action="store_true"
    )
    parser.add_argument(
        "--tebi", help="show output in tebibytes", action="store_true"
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
        "-S", help="do not display disk swap stats", action="store_true"
    )
    parser.add_argument(
        "-Z", help="do not display zram swap stats", action="store_true"
    )
    parser.add_argument("-P", help="do not display PSI", action="store_true")
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
        "TiB": args.tebi,
        "TB": args.tera,
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

    # overrides
    show_disk_swap = not args.S
    show_zram_swap = not args.Z
    show_psi = not args.P

    if show_zram_swap and swaps:
        mm_stat = gather_zram_mmstat(swaps)
    else:
        mm_stat = None

    if show_psi and psi_memory:
        psi = parse_psi(psi_memory)
    else:
        psi = None

    if show_disk_swap and swaps:
        disk_swap = parse_disk_swap(swaps)
    else:
        disk_swap = None
    if show_zram_swap and mm_stat:
        zram_swap = parse_zram_swap(mm_stat)
    else:
        zram_swap = None

    if meminfo:
        meminfo_stats = parse_meminfo(meminfo)
    else:
        sys.exit("internal error: how'd you get this far without a /proc/meminfo?")

    meminfo_stats = convert_all(meminfo_stats, unit)
    if disk_swap and show_disk_swap:
        disk_swap = convert_all(disk_swap, unit)
    if zram_swap and show_zram_swap:
        zram_swap = convert_all(zram_swap, unit)

    output: str = format_meminfo(meminfo_stats, disk_swap, show_disk_swap, args.width)

    if show_zram_swap and zram_swap:
        output += "\n"
        output += format_zram(zram_swap, meminfo_stats, args.width)

    if show_psi and psi:
        output += "\npsi some/full: "
        for row in psi.values():
            output += ", ".join(f"{v:.2f}" for v in row)
            output += " / "
    output = output.rstrip(" / ")
    print(output)


if __name__ == "__main__":
    main()
