#!/usr/bin/env bash
# Probe/poke the EC memory-mapped brightness fields (ERAX @ 0xFE500400) via busybox devmem.
#   PCBV @ 0xFE500440 (16-bit), PCBS @ 0xFE500442 (8-bit), SPBL = bit7 of 0xFE50043F.
# Usage (as root):
#   sudo bash pwrled.sh read        # SAFE: print current values
#   sudo bash pwrled.sh pcbs <0-2>  # set PCBS (3-level)
#   sudo bash pwrled.sh pcbv <0-800> # set PCBV (16-bit) + SPBL latch
PCBV=0xFE500440
PCBS=0xFE500442
FLAG=0xFE50043F   # bit7=SPBL, bit6=BLCF
dm(){ busybox devmem "$@"; }
case "${1:-read}" in
  read)
    printf 'PCBV (0x440,16) = '; dm $PCBV 16
    printf 'PCBS (0x442, 8) = '; dm $PCBS 8
    printf 'FLAG (0x43F, 8) = '; dm $FLAG 8
    ;;
  pcbs)
    dm $PCBS 8 "$2"; echo "-> wrote PCBS=$2 (now reads $(dm $PCBS 8))"
    ;;
  pcbv)
    dm $PCBV 16 "$2"
    f=$(dm $FLAG 8); nf=$(( f | 0x80 )); dm $FLAG 8 $(printf '0x%x' $nf)
    echo "-> wrote PCBV=$2 + SPBL latch (PCBV now $(dm $PCBV 16))"
    ;;
  *) echo "usage: read | pcbs <0-2> | pcbv <0-800>" ;;
esac
