"""Motion catalog assembled through directory-owned character interfaces."""

from functools import lru_cache
from .characters import motion_catalog


@lru_cache(maxsize=1)
def catalog():
    return motion_catalog()
