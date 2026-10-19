import logging
import pytest


@pytest.fixture(autouse=True)
def reset_logging_infrastructure():
    root_logger = logging.getLogger()
    orig_handlers = list(root_logger.handlers)
    orig_level = root_logger.level

    my_logger = logging.getLogger("fetchez")
    orig_propagate = my_logger.propagate

    yield

    root_logger.handlers = orig_handlers
    root_logger.setLevel(orig_level)

    my_logger.propagate = orig_propagate
