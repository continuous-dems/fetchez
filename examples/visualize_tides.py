#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
visualize_tides.py
~~~~~~~~~~~~~~~~~~

Recipe: Fetch and Plot NOAA Tide Data.
"""

import os
import sys
import argparse
import logging

# Dependencies
try:
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
except ImportError:
    sys.stderr.write("ERROR: Requires 'pandas' and 'matplotlib'. Install via pip.\n")
    sys.exit(1)

from fetchez import core, registry

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("tide_viz")


def fetch_tides(station, start, end, out_dir):
    """Wraps fetchez to get the data."""

    TidesModule = registry.FetchezRegistry.load_module("tides")
    if not TidesModule:
        logger.error("Error: 'tides' module not found in fetchez registry.")
        sys.exit(1)

    fetcher = TidesModule(
        station=station,
        start_date=start,
        end_date=end,
        datum="MLLW",
        product="water_level",
        outdir=out_dir,
    )

    fetcher.run()

    if not fetcher.results:
        logger.warning("Fetchez found no data (check dates/station ID).")
        return None

    core.run_fetchez([fetcher], threads=1)

    return fetcher.results[0]["dst_fn"]


def plot_tides(csv_path, station_id, out_img):
    """Plot the CSV."""
    try:
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.strip()

        if "Date Time" not in df.columns or "Water Level" not in df.columns:
            logger.error(f"Unexpected CSV format. Columns: {df.columns}")
            return

        df["dt"] = pd.to_datetime(df["Date Time"])

        # Plot
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(
            df["dt"],
            df["Water Level"],
            color="#005da4",
            linewidth=2,
            label="Water Level",
        )

        ax.set_title(
            f"NOAA CO-OPS: Station {station_id}\nWater Level (MLLW)", fontsize=12
        )
        ax.set_ylabel("Meters")
        ax.grid(True, linestyle=":", alpha=0.6)

        # Format X-Axis Dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))

        plt.tight_layout()
        plt.savefig(out_img)
        logger.info(f"✅ Plot saved to {out_img}")

    except Exception as e:
        logger.error(f"Plotting error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Fetch and Plot Tides")
    parser.add_argument("--station", required=True, help="Station ID (e.g. 8518750)")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    parser.add_argument("-o", "--output", default="tides.png")

    args = parser.parse_args()

    cache_dir = os.path.join(os.getcwd(), "tide_cache")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    csv_file = fetch_tides(args.station, args.start, args.end, cache_dir)

    if csv_file:
        plot_tides(csv_file, args.station, args.output)


if __name__ == "__main__":
    main()
