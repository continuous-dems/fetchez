from fetchez.registry import ProfileRegistry, DataTypeRegistry, ReaderRegistry

ProfileRegistry.load_all()
DataTypeRegistry.load_all()
ReaderRegistry.load_all()


def test_profile_declares_data_type():
    profile = ProfileRegistry.get_yaml("csv-standard")
    assert profile["data_type"] == "csv"


def test_data_type_resolves_default_profile():
    profile = DataTypeRegistry.get_default_profile("csv")

    assert profile is not None
    assert profile["name"] == "csv-standard"


# def test_reader_resolves_profile_from_entry():
#     entry = {
#         "url": "...",
#         "dst_fn": "...",
#         "data_type": "raster",
#         "profile": "rasterio",
#     }

#     reader = ReaderRegistry.get_reader_from_entry(entry)

#     assert isinstance(reader, ...)


# def test_reader_resolves_default_profile_from_data_type():
#     entry = {
#         "url": "...",
#         "dst_fn": "...",
#         "data_type": "raster",
#     }

#     reader = ReaderRegistry.get_reader_from_entry(entry)

#     assert ...
