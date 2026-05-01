# SPDX-License-Identifier: GPL-3.0-or-later
"""nextpnr-generic --run entry point for EP4CE6 (auto-generated).

Do not edit by hand; regenerate with ``python3 fuzz/chipdb_gen.py``.
"""
import gzip, json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DATA = json.loads(gzip.decompress(
    (_HERE / "chipdb_ep4ce6_data.json.gz").read_bytes()))

try:
    from nextpnrpy_generic import Loc  # type: ignore
except ImportError:
    Loc = globals().get("Loc")

_delays = {}
for cost in set(p[4] for p in _DATA["pips"]):
    _delays[cost] = ctx.getDelayFromNS(cost * 0.5)

for w in _DATA["wires"]:
    ctx.addWire(name=w[0], type=w[1], x=w[2], y=w[3])

for b in _DATA["bels"]:
    ctx.addBel(name=b["name"], type=b["type"],
               loc=Loc(b["x"], b["y"], b["z"]),
               gb=False, hidden=False)

for bp in _DATA["belpins"]:
    if bp["output"]:
        ctx.addBelOutput(bel=bp["bel"], name=bp["pin"], wire=bp["wire"])
    else:
        ctx.addBelInput(bel=bp["bel"], name=bp["pin"], wire=bp["wire"])

for p in _DATA["pips"]:
    ctx.addPip(name=p[0], type=p[1],
               srcWire=p[2], dstWire=p[3],
               delay=_delays[p[4]],
               loc=Loc(p[5], p[6], 0))

print("[chipdb_ep4ce6] loaded:",
      _DATA["stats"]["n_bels"], "bels,",
      _DATA["stats"]["n_wires"], "wires,",
      _DATA["stats"]["n_pips_total"], "pips")

# --run replaces the default flow, so we must drive pack/place/route
# ourselves.  sys.argv inside --run only has the binary path, so read
# the real command line from /proc/self/cmdline.  When invoked via
# --pre-pack instead, nextpnr runs its own pack/place/route flow and
# the hooks below would re-exec this script, double-adding wires and
# tripping the assertion in nextpnr-generic 0.10+.  Detect the
# invocation mode and skip the flow-driver block in --pre-pack mode.
def _run_hook(flag):
    """Execute a --flag script if the user passed one."""
    try:
        args = open("/proc/self/cmdline").read().split(chr(0))
    except OSError:
        return
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            path = args[i + 1]
            exec(compile(open(path).read(), path, "exec"), globals())
            return


def _invoked_as(flag):
    """True if /proc/self/cmdline contains `flag <this-file>`."""
    try:
        args = open("/proc/self/cmdline").read().split(chr(0))
    except OSError:
        return False
    me = str(Path(__file__).resolve())
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            try:
                if str(Path(args[i + 1]).resolve()) == me:
                    return True
            except (OSError, ValueError):
                pass
    return False


# Only drive the flow when invoked as --run (this script is the
# entry point).  In --pre-pack mode, nextpnr drives the default flow
# and the hooks below would cause recursion.
if _invoked_as("--run"):
    _run_hook("--pre-pack")
    ctx.pack()
    _run_hook("--pre-place")
    ctx.place()
    _run_hook("--pre-route")
    ctx.route()
    _run_hook("--post-route")
