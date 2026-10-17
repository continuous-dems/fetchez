from fetchez.hooks.base import FetchHook


def test_fetchhook_stream_helpers():
    """Test that the base hook correctly identifies stream types using the helpers."""

    hook = FetchHook()

    entry_empty = {"dst_fn": "test.txt"}
    assert not hook.has_stream(entry_empty)

    entry_points = {"stream": (x for x in []), "stream_type": "point-stream"}
    assert hook.has_stream(entry_points)
    assert hook.is_point_stream(entry_points)
    assert not hook.is_raster_stream(entry_points)

    entry_raster = {"stream": (x for x in []), "stream_type": "raster-stream"}
    assert hook.is_raster_stream(entry_raster)
    assert not hook.is_point_stream(entry_raster)
