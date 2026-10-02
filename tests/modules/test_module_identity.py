from fetchez.modules import FetchModule


class IdentityModule(FetchModule):
    name = "identity-test"

    def __init__(
        self,
        product=None,
        resolution=None,
        enabled=True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.product = product
        self.resolution = resolution
        self.enabled = enabled

    def run(self):
        return self


def test_identical_constructor_args_produce_identical_module_id(tmp_path):
    """Equivalent module invocations should have stable identities."""

    first = IdentityModule(
        product="foo",
        resolution=10,
        outdir=tmp_path,
    )
    second = IdentityModule(
        product="foo",
        resolution=10,
        outdir=tmp_path,
    )

    assert first.module_id() == second.module_id()


def test_subclass_argument_changes_module_id(tmp_path):
    """Subclass constructor arguments must participate in identity."""

    first = IdentityModule(
        product="foo",
        resolution=10,
        outdir=tmp_path,
    )
    second = IdentityModule(
        product="bar",
        resolution=10,
        outdir=tmp_path,
    )

    assert first.module_id() != second.module_id()


def test_second_subclass_argument_changes_module_id(tmp_path):
    """Identity should not depend on only one selected subclass argument."""

    first = IdentityModule(
        product="foo",
        resolution=10,
        outdir=tmp_path,
    )
    second = IdentityModule(
        product="foo",
        resolution=30,
        outdir=tmp_path,
    )

    assert first.module_id() != second.module_id()


def test_keyword_only_forwarded_argument_changes_module_id(tmp_path):
    """Arguments forwarded through **kwargs should still affect identity."""

    first = IdentityModule(
        product="foo",
        params={"format": "json"},
        outdir=tmp_path,
    )
    second = IdentityModule(
        product="foo",
        params={"format": "xml"},
        outdir=tmp_path,
    )

    assert first.module_id() != second.module_id()


def test_execution_only_arguments_do_not_change_module_id(tmp_path):
    """Runtime settings such as outdir/use_cache are not module identity."""

    first = IdentityModule(
        product="foo",
        resolution=10,
        outdir=tmp_path / "one",
        use_cache=True,
    )
    second = IdentityModule(
        product="foo",
        resolution=10,
        outdir=tmp_path / "two",
        use_cache=False,
    )

    assert first.module_id() == second.module_id()


class LocalVariableModule(FetchModule):
    name = "local-variable-test"

    def __init__(self, product=None, **kwargs):
        temporary_value = f"derived-{product}"
        another_internal = {"product": product}

        super().__init__(**kwargs)

        self.product = product
        self.temporary_value = temporary_value
        self.another_internal = another_internal

    def run(self):
        return self


def test_constructor_locals_are_not_captured(tmp_path):
    """Only declared constructor arguments should enter module identity."""

    module = LocalVariableModule(
        product="foo",
        outdir=tmp_path,
    )

    assert module._init_kwargs["product"] == "foo"

    assert "temporary_value" not in module._init_kwargs
    assert "another_internal" not in module._init_kwargs


class ParentIdentityModule(FetchModule):
    name = "parent-identity-test"

    def __init__(self, parent_option=None, **kwargs):
        super().__init__(**kwargs)
        self.parent_option = parent_option

    def run(self):
        return self


class ChildIdentityModule(ParentIdentityModule):
    name = "child-identity-test"

    def __init__(self, child_option=None, **kwargs):
        super().__init__(**kwargs)
        self.child_option = child_option


def test_outermost_subclass_constructor_is_captured(tmp_path):
    module = ChildIdentityModule(
        child_option="child",
        parent_option="parent",
        outdir=tmp_path,
    )

    assert module._init_kwargs["child_option"] == "child"
    assert module._init_kwargs["parent_option"] == "parent"


def test_inherited_kwargs_participate_in_identity(tmp_path):
    first = ChildIdentityModule(
        child_option="same",
        parent_option="one",
        outdir=tmp_path,
    )
    second = ChildIdentityModule(
        child_option="same",
        parent_option="two",
        outdir=tmp_path,
    )

    assert first.module_id() != second.module_id()


def test_child_argument_participates_in_identity(tmp_path):
    first = ChildIdentityModule(
        child_option="one",
        parent_option="same",
        outdir=tmp_path,
    )
    second = ChildIdentityModule(
        child_option="two",
        parent_option="same",
        outdir=tmp_path,
    )

    assert first.module_id() != second.module_id()


def test_mapping_order_does_not_change_module_id(tmp_path):
    first = IdentityModule(
        product="foo",
        params={
            "alpha": 1,
            "beta": 2,
        },
        outdir=tmp_path,
    )

    second = IdentityModule(
        product="foo",
        params={
            "beta": 2,
            "alpha": 1,
        },
        outdir=tmp_path,
    )

    assert first.module_id() == second.module_id()


class SetIdentityModule(FetchModule):
    name = "set-identity-test"

    def __init__(self, values=None, **kwargs):
        super().__init__(**kwargs)
        self.values = values

    def run(self):
        return self


def test_set_order_does_not_change_module_id(tmp_path):
    first = SetIdentityModule(
        values={"a", "b", "c"},
        outdir=tmp_path,
    )
    second = SetIdentityModule(
        values={"c", "a", "b"},
        outdir=tmp_path,
    )

    assert first.module_id() == second.module_id()


def test_base_defaults_do_not_change_identity_when_explicit(tmp_path):
    implicit = IdentityModule(
        product="foo",
        outdir=tmp_path,
    )

    explicit = IdentityModule(
        product="foo",
        min_year=None,
        max_year=None,
        weight=1.0,
        uncertainty=0.0,
        params={},
        outdir=tmp_path,
    )

    assert implicit.module_id() == explicit.module_id()


class OtherIdentityModule(IdentityModule):
    name = "identity-test"


def test_different_module_classes_never_share_identity(tmp_path):
    first = IdentityModule(
        product="foo",
        resolution=10,
        outdir=tmp_path,
    )
    second = OtherIdentityModule(
        product="foo",
        resolution=10,
        outdir=tmp_path,
    )

    assert first.module_id() != second.module_id()
