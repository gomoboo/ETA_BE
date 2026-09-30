from typing import List

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class PlaceItem(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    place_name: str
    address: str
    latitude: float
    longitude: float


class PlaceSearchResponse(BaseModel):
    places: List[PlaceItem]
