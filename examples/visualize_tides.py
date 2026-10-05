#!/usr/bin/env python

"""
visualize_tides.py
~~~~~~~~~~~~~~~~~~

Recipe: Fetch and Plot NOAA Tide Data.
"""

import argparse
import logging
import sys
from pathlib import Path

# Dependencies
try:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import pandas as pd
except ImportError:
    sys.stderr.write("ERROR: Requires 'pandas' and 'matplotlib'. Install via pip.\n")
    sys.exit(1)

import fetchez as fz

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("tide_viz")


def fetch_tides(station, start, end, out_dir):
    """Wraps fetchez to get the data."""
    results = fz.get(
        "tides",
        station=station,
        start_date=start,
        end_date=end,
        datum="MLLW",
        product="water_level",
        outdir=out_dir,
    )

    if not results:
        logger.warning("Fetchez found no data (check dates/station ID).")
        return None

    return results[0]  # Returns the downloaded file path


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

    cache_dir = Path.cwd() / "tide_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    csv_file = fetch_tides(args.station, args.start, args.end, str(cache_dir))

    if csv_file:
        plot_tides(csv_file, args.station, args.output)


if __name__ == "__main__":
    main()
