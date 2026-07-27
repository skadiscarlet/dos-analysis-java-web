from typing import Protocol

from dosweb.growth.models import BoundedSlice, GrowthContract


class GrowthClassifier(Protocol):
    def classify_growth(self, slice_: BoundedSlice) -> GrowthContract:
        raise NotImplementedError
