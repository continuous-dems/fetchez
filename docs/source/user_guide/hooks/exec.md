# External command processing with `exec`

Fetchez's **`exec`** hook runs an external program for each completed file entry. It is useful for leveraging GDAL, GMT, PDAL, CDO, other command-line programs, or your own scripts in YAML workflows, without creating a specialized Python hook for every operation.

`exec` defaults to the **`file`** stage, where it runs after a file has been fetched and before Fetchez initializes stream processing. Set `stage: collection` to operate on the completed entries after the normal stream stage. It does not process individual raster or point-stream chunks.

## Two ways to use `exec`

### Run a command without changing the entry

```yaml
- name: exec
  stage: file
  args:
    cmd: [gdalinfo, "{file}"]
```

Without an `output` declaration, the program runs but the current entry's `dst_fn` and artifacts are not changed. This preserves the original behavior for validation, diagnostics, notifications, etc.

### Generate an output and pass it to the next hook

```yaml
- name: exec
  stage: file
  args:
    cmd: [gdal_translate, -of, COG, "{file}", "{output}"]
    output:
      suffix: _cog
      extension: .tif
```

When `output` is supplied, Fetchez generates the destination name, passes a **temporary path** to the command via `{output}`, verifies that a file was produced, and atomically publishes it. Only after success does it register an artifact and update `entry['dst_fn']`. The next file hook therefore receives the newly generated raster through `{file}`.

The original input is retained; the output name must not resolve to the input name. For single-file formats, an existing destination is replaced by default after success.

## Recipe examples

### Reprojection followed by COG conversion

```yaml
hooks:
  - name: exec
    stage: file
    args:
      cmd: [gdalwarp, -t_srs, EPSG:4326, "{file}", "{output}"]
      output:
        suffix: _warped
        extension: .tif
        artifact_id: warped_raster

  - name: exec
    stage: file
    args:
      cmd: [gdal_translate, -of, COG, "{file}", "{output}"]
      output:
        suffix: _cog
        extension: .tif
        artifact_id: cog_raster
```

The second command receives the reprojected raster, not the original input. Artifact IDs should be distinct when multiple `exec` instances contribute outputs to the same entry; otherwise later results replace the earlier artifact key.

### A standalone Python processing script

```yaml
- name: exec
  stage: file
  args:
    cmd: [python, /path/to/clean_dem.py, --input, "{file}", --output, "{output}"]
    output:
      output_path: "processed/{stem}_clean.tif"
      extension: .tif
```

### Keep the original as the primary file

```yaml
- name: exec
  stage: collection
  args:
    cmd: [gdal_translate, -of, GTiff, "{file}", "{output}"]
    output:
      suffix: _copy
      extension: .tif
      artifact_id: converted_copy
      update_entry: false
```

The artifact is registered, but `dst_fn` remains unchanged.

## Configuration reference

| Option | Meaning |
| --- | --- |
| `cmd` | Required executable and arguments, preferably a YAML list; string commands are also supported. |
| `output` | Optional mapping declaring an output file; omitted for side-effect commands. |
| `output.output_path` | Directory (existing or ending in `/`), explicit filename for one entry, or template. |
| `output.suffix` | Suffix used in the default filename; defaults to `_processed`. |
| `output.extension` | Output extension; defaults to the input extension. |
| `output.artifact_id` | Key for `entry['artifacts']`; defaults to `exec`. |
| `output.update_entry` | Whether to replace `entry['dst_fn']`; defaults to `true` when output is declared. |
| `output.overwrite` | Whether to replace an existing destination; defaults to `true`. |
| `timeout` | Optional subprocess timeout in seconds. |
| `stage` | Usually `file` or `collection`. |

Output naming accepts `{stem}`, `{name}`, `{suffix}`, and `{index}`. With multiple entries, use a directory or template containing a per-file identifier to avoid collisions. A directory not yet created should be written with a trailing slash, e.g. `processed/`, or expressed as `processed/{stem}_final.tif`.

### Command placeholders

| Placeholder | Value |
| --- | --- |
| `{file}` | Current entry `dst_fn` (input to this command) |
| `{dir}` | Parent directory of the input |
| `{filename}` | Input basename including extension |
| `{name}` / `{stem}` | Input basename without its final extension |
| `{url}` | Entry source URL, if available |
| `{output}` | Staged output filename; only meaningful when `output` is declared |

For command strings, the hook parses shell-like quoting using `shlex` before expanding placeholders. A list of arguments is more reliable, particularly for paths with spaces. The command runs with `shell=False`: shell syntax such as pipes, globbing, redirection, or `&&` is **not interpreted**. For advanced shell workflows, invoke a script explicitly.

## Execution, errors, and outputs

- Command execution uses `subprocess.run(..., check=True)`. A failing return code raises an exception, allowing Fetchez's normal stage-specific error handling to apply.
- Missing expected outputs also raise an exception. An unsuccessful transformation does not update the entry's `dst_fn` or register the new artifact.
- Successfully published outputs are stored in `entry['artifacts'][artifact_id]` and, by default, become the new `dst_fn`.
- The output is staged in the destination directory and published via `os.replace`, so an earlier single-file output is not replaced until the command succeeds. This is **not** a multi-file or concurrent-writer transaction.
- The staged name has the same extension as the requested output. Some programs create sidecar files or multiple outputs; those require separate handling and should **not** use this single-file publication mode without additional staging support.
- Entries with an explicit nonzero `status` are skipped; entries with `status` omitted or set to `0` are eligible.
- `exec` processes each supplied entry independently. It does not implement a shell pipeline between entries.

## When to use `exec`, `RasterPipeline`, or a custom hook

Use **`exec`** when a well-supported existing command-line program already performs the file-level transformation. Use **`RasterPipeline`** to compose Fetchez native raster-stream hooks over files at the file or collection stage. Write a **custom hook** when you need a novel algorithm, direct streaming transformations, rich domain-specific state, or tighter integration with Fetchez and Globato.

Keeping these roles separate lets Fetchez orchestrate existing geospatial software without duplicating the algorithms provided by GDAL, GMT, Rasterio, and related ecosystems.
