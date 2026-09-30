from fetchez.modules.tnm import TheNationalMap


def test_tnm_products_changes_module_id():
    one = TheNationalMap(products="1m")
    ninth = TheNationalMap(products="1_9as")

    assert one.module_id() != ninth.module_id()


def test_tnm_products_is_in_canonical_config():
    module = TheNationalMap(products="1m")

    assert module.canonical_module_config()["products"] == "1m"


def test_tnm_identity_includes_product_configuration():
    one = TheNationalMap(products="1m")
    nine = TheNationalMap(products="1_9as")

    assert one.module_id() != nine.module_id()
