import logging
from rich.logging import RichHandler

_root_logger = logging.getLogger("remote-containers-management")
_root_logger.setLevel(logging.INFO)
_handler = RichHandler()
_handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
_root_logger.addHandler(_handler)

def get_logger(name: str):
    return _root_logger.getChild(name)
