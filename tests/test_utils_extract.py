# tests/test_utils_extract.py

import multiprocessing
import time
import zipfile
from pathlib import Path

from fetchez import utils


def _extract_worker(
    archive_path: str,
    output_dir: str,
) -> list[str]:
    return utils.p_f_extract(
        archive_path,
        outdir=output_dir,
    )


def test_p_f_extract_is_safe_with_multiple_processes(tmp_path):
    archive_path = tmp_path / "input.zip"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    expected = b"Transformez/Fetchez shared-cache test data\n" * 10000

    # Create a reasonably large member so extraction has some measurable work.
    source_file = tmp_path / "source.dat"
    source_file.write_bytes(expected)

    import zipfile

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(source_file, "resource.dat")

    ctx = multiprocessing.get_context("spawn")

    with ctx.Pool(processes=4) as pool:
        results = pool.starmap(
            _extract_worker,
            [(str(archive_path), str(output_dir)) for _ in range(4)],
        )

    output_path = output_dir / "resource.dat"

    assert output_path.exists()
    assert output_path.read_bytes() == expected

    for result in results:
        assert output_path in result

    # No temporary extraction artifacts should remain.
    assert not list(output_dir.glob("*.tmp"))
    assert not list(output_dir.glob(".*.tmp"))


def _lock_worker(lock_path, started, finished):
    started.set()

    with utils.filelock.FileLock(str(lock_path), timeout=10):
        finished.set()


def test_filelock_blocks_across_processes(tmp_path):
    lock_path = tmp_path / "test.lock"

    ctx = multiprocessing.get_context("spawn")
    started = ctx.Event()
    finished = ctx.Event()

    lock = utils.filelock.FileLock(str(lock_path))

    with lock:
        process = ctx.Process(
            target=_lock_worker,
            args=(str(lock_path), started, finished),
        )
        process.start()

        assert started.wait(timeout=2)

        # Child should be blocked inside FileLock.
        assert not finished.wait(timeout=0.25)

    process.join(timeout=5)

    assert process.exitcode == 0
    assert finished.is_set()


def _extract_worker2(
    archive_path: str,
    output_dir: str,
    result_queue,
) -> None:
    started = time.monotonic()

    utils.p_f_extract(
        archive_path,
        outdir=output_dir,
    )

    result_queue.put(time.monotonic() - started)


def _extract_worker3(
    archive_path: str,
    output_dir: str,
    started,
    finished,
) -> None:
    started.set()

    utils.p_f_extract(
        archive_path,
        outdir=output_dir,
    )

    finished.set()


def test_p_f_extract_waits_for_existing_process_lock(tmp_path):
    archive_path = tmp_path / "input.zip"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    source_file = tmp_path / "resource.dat"
    source_file.write_bytes(b"shared-cache test")

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(source_file, "resource.dat")

    lock_path = utils._extract_lock_path(
        archive_path,
        output_dir,
    )

    ctx = multiprocessing.get_context("spawn")
    started = ctx.Event()
    finished = ctx.Event()

    lock = utils.filelock.FileLock(
        str(lock_path),
        timeout=10,
    )

    with lock:
        process = ctx.Process(
            target=_extract_worker3,
            args=(
                str(archive_path),
                str(output_dir),
                started,
                finished,
            ),
        )
        process.start()

        # The child has entered p_f_extract(), but should be blocked
        # waiting for the lock.
        assert started.wait(timeout=2)
        assert not finished.wait(timeout=0.25)

        # It should not have published the output while the lock is held.
        assert not (output_dir / "resource.dat").exists()

    process.join(timeout=10)

    assert process.exitcode == 0
    assert finished.is_set()
    assert (output_dir / "resource.dat").read_bytes() == b"shared-cache test"


def test_p_f_extract_reuses_complete_existing_file(tmp_path):
    archive_path = tmp_path / "input.zip"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    source_file = tmp_path / "source.dat"
    source_file.write_bytes(b"original data")

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(source_file, "resource.dat")

    _first = utils.p_f_extract(
        archive_path,
        outdir=output_dir,
    )

    output_path = output_dir / "resource.dat"
    first_mtime = output_path.stat().st_mtime_ns

    second = utils.p_f_extract(
        archive_path,
        outdir=output_dir,
    )

    assert second == [output_path]
    assert output_path.read_bytes() == b"original data"
    assert output_path.stat().st_mtime_ns == first_mtime


def _reader_worker(
    path: str,
    expected_values: tuple[bytes, bytes],
    stop_event,
    failures,
):
    path = Path(path)

    while not stop_event.is_set():
        if not path.exists():
            continue

        try:
            data = path.read_bytes()
        except OSError:
            continue

        if data and data not in expected_values:
            failures.append(
                f"Observed unexpected intermediate file of {len(data)} bytes"
            )
