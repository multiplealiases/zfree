#!/usr/bin/env sh
set -o nounset
set -o errexit

# SPDX-License-Identifier: MIT

# Copyright (c) 2024 multiplealiases
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# “Software”), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
# NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
# THE USE OR OTHER DEALINGS IN THE SOFTWARE.

banner() {
    echo a zram-aware free-alike
}

usage() {
    printf 'Usage: zfree [options]\n'
}

kbytes_to_unit() {
    kbytes="$1"
    unit="$2"
    case "$unit" in
    '')
        # /proc/meminfo values are in KiB
        ret=$(( kbytes * 1024 ))
        ;;
    K)
        ret=$( echo "$kbytes" | awk '{printf "%.0f\n", ($1 * 1024) / (1000)}' )
        ;;
    Ki)
        # trivial case
        ret="$kbytes"
        ;;
    M)
        ret=$( echo "$kbytes" | awk '{printf "%.0f\n", ($1 * 1024) / (1000 * 1000)}' )
        ;;
    Mi)
        ret=$( echo "$kbytes" | awk '{printf "%.0f\n", $1 / 1024}' )
        ;;
    G)
        ret=$( echo "$kbytes" | awk '{printf "%.1f\n", ($1 * 1024) / (1000 * 1000 * 1000)}' )
        ;;
    Gi)
        ret=$( echo "$kbytes" | awk '{printf "%.1f\n", $1 / (1024 * 1024)}' )
        ;;
    # TODO: TB/TiB support
    # Does anyone have enough RAM that TB is the natural unit?
    *)
        die "Unsupported unit %s\n" "$unit"
      ;;
    esac
    printf '%s\n' "$ret"
}

help_text(){
    cat << EOF
$(banner)
$(usage)

Options
-h, --help          this help
-o, --output <list> comma-separated list of columns to use for output
-n, --no-unit       do not show unit in output
Unit options
-k, --kibi          show output in kibibytes
-K, --kilo          show output in kilobytes
-m, --mebi          show output in mebibytes [default]
-M, --mega          show output in megabytes
-g, --gibi          show output in gibibytes
-G, --giga          show output in gigabytes

Output columns
    total           Total installed memory [MemTotal]
    used            Used memory [MemTotal - MemAvailable - Buffers - Cached]
    available       Available memory for allocation [MemAvailable]
    bufcache        Buffers and cache [Buffers + Cached]
    free            Unused memory [MemFree]
    compdata        Uncompressed size of zram swap
    comptotal       Actual size of zram swap in physical memory
    compratio       Compression ratio of zram swap [compdata / comptotal]
EOF
}

die() {
	# shellcheck disable=SC2059
	printf "$@"
	exit 1
}

while [ "$#" -gt 0 ]
do
    case "$1" in
    --help)
        help_text
        exit 1
        ;;
    -k | --kibi)
        unit=Ki
        shift
        ;;
    -K | --kilo)
        unit=K
        shift
        ;;
    -m | --mebi)
        unit=Mi
        shift
        ;;
    -M | --mega)
        unit=M
        shift
        ;;
    -g | --gibi)
        unit=Gi
        shift
        ;;
    -G | --giga)
        unit=G
        shift
        ;;
    -n | --no-unit)
        nounit=y
        shift
        ;;
    -o | --output)
        columns="$2"
        shift 2
        ;;
    *)
        die "argument(s) not recognized: %s\nUse --help for help\n" "$*"
        ;;
    esac
done
defunit=Mi
unit="${unit-$defunit}"
nounit="${nounit:-n}"

cleanup_dir="$(mktemp -d)"
cleanup() {
    rm -rf "$cleanup_dir"
}
# shellcheck disable=SC2120
autocleaning_mktemp() {
    mktemp "$@" -p "$cleanup_dir"
}
trap 'cleanup' INT HUP TERM EXIT

meminfo=$(autocleaning_mktemp)
mm_stat=$(autocleaning_mktemp)
swaps=$(autocleaning_mktemp)
output=$(autocleaning_mktemp)

cat /proc/swaps | awk '{$1=$1}1;' > "$swaps"
cat /proc/meminfo > "$meminfo"

# TODO: figure out multiple zram swap devices
zswap_dev=$(grep zram "$swaps" | cut -f 1 -d ' ' | rev | cut -f 1 -d / | rev)

if [ "$zswap_dev" != "" ]
then
    awk '{$1=$1};1' /sys/class/block/"$zswap_dev"/mm_stat > "$mm_stat"
    defcols="total,used,available,bufcache,free,compdata,comptotal,compratio"
else
    # write dummy values to mm_stat
    # and omit the zram-specific columns
    # if no zram swap is present
    echo "0 0 0 0 0 0" > "$mm_stat"
    defcols="total,used,available,bufcache,free"
fi
columns="${columns:-$defcols}"

# kiB
memtotal=$(( $(grep MemTotal "$meminfo" | tr -cd '0-9') ))
memavailable=$(( $(grep MemAvailable "$meminfo" | tr -cd '0-9' ) ))
memfree=$(( $(grep MemFree "$meminfo" | tr -cd '0-9' ) ))
membuf=$(( $( grep Buffers "$meminfo" | tr -cd '0-9' ) ))
memcache=$(( $( grep '^Cached' "$meminfo" | tr -cd '0-9' ) ))
membufcache=$(( memcache + membuf ))
memused=$(( memtotal - memfree - membufcache ))

swaptotal=$(grep -v '\(Filename\|zram\)' "$swaps" | cut -f 3 -d ' ')
swapfree=$(grep -v '\(Filename\|zram\)' "$swaps" | cut -f 4 -d ' ')
swapused=$((swaptotal - swapfree))
if [ "$swaptotal" = "" ]
then
     haveswap=0
else
     haveswap=1
fi
# bytes
ztotal=$(cut -f 3 -d ' ' "$mm_stat")
zdata=$(cut -f 1 -d ' ' "$mm_stat")

# dimensionless
# add 1 to ztotal to prevent division by 0
zratio=$( echo "$zdata" "$((ztotal + 1))" | awk '{printf "%.2f\n", $1/$2}' )

# convert to MiB (1024, not 1000)
memtotal=$( kbytes_to_unit "$memtotal" "$unit" )
memavailable=$( kbytes_to_unit "$memavailable" "$unit" )
memfree=$( kbytes_to_unit "$memfree" "$unit" )
memused=$( kbytes_to_unit "$memused" "$unit" )
membufcache=$( kbytes_to_unit "$membufcache" "$unit" )
ztotal=$( kbytes_to_unit "$((ztotal / 1024))" "$unit" )
zdata=$( kbytes_to_unit "$((zdata / 1024))" "$unit" )
swaptotal=$( kbytes_to_unit "$swaptotal" "$unit" )
swapfree=$( kbytes_to_unit "$swapfree" "$unit" )
swapused=$( kbytes_to_unit "$swapused" "$unit" )

# and glue the units on

if [ "$nounit" = "y" ]
then
    unit=""
fi

memtotal="$memtotal""$unit"
memavailable="$memavailable""$unit"
memfree="$memfree""$unit"
memused="$memused""$unit"
membufcache="$membufcache""$unit"
ztotal="$ztotal""$unit"
zdata="$zdata""$unit"
swaptotal="$swaptotal""$unit"
swapfree="$swapfree""$unit"
swapused="$swapused""$unit"

values=""
swapvalues=""
# match the behavior of zramctl's --output option
IFS=","

for col in $columns;
do
    case "$col" in
    total)
        values="$values$memtotal "
        ;;
    used)
        values="$values$memused "
        ;;
    available)
        values="$values$memavailable "
        ;;
    bufcache)
        values="$values$membufcache "
        ;;
    free)
        values="$values$memfree "
        ;;
    compdata)
        values="$values$zdata "
        ;;
    comptotal)
        values="$values$ztotal "
        ;;
    compratio)
        values="$values$zratio "
        ;;
    *)
        die "unknown column type %s\n" "$col"
        ;;
    esac
done

for col in $columns;
do
    case "$col" in
    total)
        swapvalues="$swapvalues$swaptotal "
        ;;
    used)
        swapvalues="$swapvalues$swapused "
        ;;
    free)
        swapvalues="$swapvalues$swapfree "
        ;;
    available | bufcache | compdata | comptotal | compratio)
        swapvalues="${swapvalues}N "
        ;;
    *)
        die "unknown column type %s\n" "$col"
        ;;
    esac
done

IFS=' ,'
# this is primitive, but it's all I have.
set -f
printf '      ' >> "$output"
printf '%11s' $columns >> "$output"
echo >> "$output"
printf 'Mem:  ' >> "$output"
printf '%11s' $values >> "$output"
if [ "$haveswap" = 1 ]
then
    echo >> "$output"
    printf 'Swap: ' >> "$output"
    printf '%11s' $swapvalues | tr 'N' ' ' >> "$output"
fi
echo >> "$output"

cat "$output"
