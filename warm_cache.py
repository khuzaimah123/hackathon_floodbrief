"""
Pre-load the cache before judging: runs a full live lookup for each address in
config.DEMO_ADDRESSES (through the same load_site the app uses), builds the brief,
and prints a status table.

    python3 warm_cache.py
"""
import os
import time

os.environ.pop("SAMPLE", None)  # always do real lookups here

import app  # noqa: E402
import brief  # noqa: E402
import config  # noqa: E402


def main():
    rows, notes = [], []
    for address in config.DEMO_ADDRESSES:
        t = time.time()
        try:
            site = app.load_site(address)
            b = brief.build_brief(site)
        except Exception as e:  # report every failure, keep going
            rows.append([address, "FAIL", f"{time.time() - t:.1f}s", "", "", "", "", ""])
            notes.append(f"{address}: {type(e).__name__}: {e}")
            continue
        if site.get("from_cache"):
            status = f"CACHED {site['from_cache']}"
        elif app.is_cacheable(site):
            status = "LIVE, saved"
        else:
            status = "LIVE, NOT saved"
        t_ = b["today"]
        curve = (site.get("gauge") or {}).get("curve")
        rows.append([
            address, status, f"{time.time() - t:.1f}s",
            t_["zone"] or "-",
            f"{t_['bfe_ft']:g}" if t_["bfe_ft"] is not None else "-",
            f"{t_['ground_ft']:g}" if t_["ground_ft"] is not None else "-",
            f"{len(curve)} pts" if curve else "-",
            str(len(b["warnings"])),
        ])
        notes += [f"{address}: {w}" for w in b["warnings"]]

    head = ["Address", "Result", "Time", "Zone", "BFE ft", "Ground ft", "Curve", "Warn"]
    widths = [max(len(str(r[i])) for r in rows + [head]) for i in range(len(head))]
    line = lambda r: "  ".join(str(c).ljust(w) for c, w in zip(r, widths))  # noqa: E731
    print(line(head))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(line(r))
    if notes:
        print("\nWarnings / errors:")
        for n in notes:
            print("  - " + n)
    saved = [a for a in config.DEMO_ADDRESSES if os.path.exists(app.cache_path(a))]
    print(f"\nCache files present for {len(saved)}/{len(config.DEMO_ADDRESSES)} demo addresses.")


if __name__ == "__main__":
    main()
