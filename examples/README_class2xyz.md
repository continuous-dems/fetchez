# class2xyz (LITE) — LAS/LAZ class-filtered XYZ export

`class2xyz.py` is a lightweight **fetchez hook example** that extracts LAS/LAZ points by **classification** and writes an ASCII `.xyz` file in **X Y Z** order.

- **No CRS transforms** (keeps fetchez lightweight)
- Output filename includes class tag(s): `*_c29.xyz`, `*_c2-29-40.xyz`, etc.
- Precision defaults:
  - If the LAS/LAZ looks geographic (lon/lat bbox): **XY = 10 decimals**
  - **Z decimals inferred from LAS header Z scale** (often 2–3)

If you need reprojection/gridding/stream-chaining, use **Globato**:
`stream_data → stream_reproject → save_xyz/simple_stack`

---

## Install dependencies

### Conda (recommended)
```bash
mamba install -c conda-forge laspy lazrs
# or: conda install -c conda-forge laspy lazrs
```

### Pip
```bash
pip install laspy lazrs
```

> Note: `lazrs` is needed for **.laz**. If you only have `.las`, `laspy` alone is enough.

---

## Where to put the hook

### Option A: Run from `examples/` (quick test)
Copy/paste the commands in `examples/class2xyz_examples.sh`.

### Option B: Install as a local hook
Fetchez loads user hooks from:
```bash
~/.fetchez/hooks/
```

Create it if it doesn’t exist:
```bash
mkdir -p ~/.fetchez/hooks
```

Copy the hook:
```bash
cp examples/class2xyz.py ~/.fetchez/hooks/class2xyz.py
```

Confirm it’s visible:
```bash
fetchez --list-hooks | grep class2xyz
```

---

## Usage

### Ground points (class 2)
```bash
fetchez <module> ... --hook class2xyz:classes=2,out_dir=./ground_xyz
```

### Bathy points (example class 29)
```bash
fetchez dav --survey_id 8688 -R -71.76/-71.70/41.32/41.36 \
  --hook class2xyz:classes=29,out_dir=./bathy_xyz
```

### Multiple classes (important note)

Fetchez hook args are comma-delimited (`key=value,key=value,...`), so **don’t use commas inside** `classes=`.

You can use `+` (shell-safe, recommended for scripts):

```bash
fetchez <module> ... --hook class2xyz:classes=2+29+40,out_dir=./classes_xyz
```

You can also use `|`, but **quote or escape it** because `|` is a shell pipe operator:

```bash
fetchez <module> ... --hook "class2xyz:classes=2|29|40,out_dir=./classes_xyz"
# or:
fetchez <module> ... --hook class2xyz:classes=2\|29\|40,out_dir=./classes_xyz
```

### Overwrite outputs
```bash
fetchez <module> ... --hook class2xyz:classes=29,out_dir=./bathy_xyz,overwrite=true
```

---

## Notes / Troubleshooting

- If you see “produced 0 XYZ outputs”, check:
  - `laspy`/`lazrs` installed
  - your requested `classes=` actually exist in the tiles
  - output directory permissions
- This hook does **not** support `in_srs/out_srs`. Use Globato for CRS ops.
