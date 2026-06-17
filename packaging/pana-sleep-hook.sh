#!/usr/bin/env bash
# Installed to /usr/lib/systemd/system-sleep/pana
# Re-applies pana settings after resume (the firmware resets TDP across sleep).
case "$1/$2" in
    post/*)
        /usr/local/bin/pana --socket /run/pana/pana.sock reapply >/dev/null 2>&1 || true
        ;;
esac
