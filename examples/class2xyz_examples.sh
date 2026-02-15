#!/usr/bin/env bash
set -euo pipefail

# Example usage for the class2xyz (LITE) hook.
#
# Dependencies (conda-forge recommended):
#   mamba install -c conda-forge laspy lazrs
#
# If you want to use this as a local hook:
#   mkdir -p ~/.fetchez/hooks
#   cp examples/class2xyz.py ~/.fetchez/hooks/class2xyz.py
#   fetchez --list-hooks | grep class2xyz
#
# IMPORTANT:
# - fetchez hook args are comma-delimited (key=value,key=value,...), so do NOT use commas inside classes=.
# - in bash, the '|' character is a pipe operator, so prefer '+' in scripts:
#     classes=2+29+40   (shell-safe)

REGION="-71.76/-71.70/41.32/41.36"
SURVEY_ID="8688"

# 1) Topographic ground returns (class 2) -> XYZ
fetchez -R "${REGION}" dav --survey_id "${SURVEY_ID}" \
  --hook class2xyz:classes=2,out_dir=./ground_xyz

# 2) Bathymetric returns (example: class 29) -> XYZ
fetchez -R "${REGION}" dav --survey_id "${SURVEY_ID}" \
  --hook class2xyz:classes=29,out_dir=./bathy_xyz

# 3) Multiple classes -> XYZ (filename includes _c2-29-40)
fetchez -R "${REGION}" dav --survey_id "${SURVEY_ID}" \
  --hook class2xyz:classes=2+29+40,out_dir=./classes_xyz

# 4) Overwrite existing outputs
fetchez -R "${REGION}" dav --survey_id "${SURVEY_ID}" \
  --hook class2xyz:classes=29,out_dir=./bathy_xyz,overwrite=true
