from fetchez.registry import BundleRegistry


def test_products_is_part_of_module_signature():
    one = {"module": "tnm", "args": {"products": "1m"}}
    ninth = {"module": "tnm", "args": {"products": "1_9as"}}
    assert BundleRegistry.get_module_signature(
        one
    ) != BundleRegistry.get_module_signature(ninth)
    assert "products=1m" in BundleRegistry.get_module_signature(one)
