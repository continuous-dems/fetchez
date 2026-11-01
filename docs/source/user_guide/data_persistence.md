# 🔱 Data Availability & Persistence

Fetchez is a data acquisition framework — we provide the tools to locate and download data from authoritative public repositories, but we do not host the data ourselves.

## What This Means for Users

**Source data can change without warning.** Government agencies reorganize websites, migrate APIs (e.g., WCS 1.0 to 2.0), or decommission servers without notice. A module that fetches perfectly today may encounter a 404 tomorrow.

**Datasets are frequently updated or removed.** Source datasets are actively maintained, reprocessed, or retired by their custodians. The "best available" data for a region can change overnight.

**Remote servers are outside our control.** Providers like NOAA NCEI, USGS, or Copernicus may experience downtime, throttling, or rate limits that we cannot predict or prevent.

## How Fetchez Handles Instability

We strive to keep our modules robust and our index fresh. Fetchez includes:

* **Retry logic** — Failed downloads attempt again automatically
* **Resumable transfers** — Interrupted downloads can continue from where they stopped
* **Caching** — Successfully retrieved files are cached locally to avoid unnecessary re-fetches
* **Validation hooks** — Checksum and schema validation catch corrupted or incomplete downloads

Despite these protections, you should design your workflows to tolerate occasional failures.

## Reporting Issues

If you encounter a broken fetch or a changed endpoint, please [open an issue](https://github.com/continuous-dems/fetchez/issues). This helps the whole community keep up with the changes.

Include:

* The module name you're using
* The error message you received
* The region or dataset you were trying to access
* Whether this worked previously (and when)

We monitor issues closely and prioritize fixes for critical data sources.
