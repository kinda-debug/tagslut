from __future__ import annotations
from typing import Union
from typing import List
from pydantic import Field
from typing import Optional
from typing import Annotated
from pydantic import TypeAdapter
from .utils.base_model import BaseModel
from .current_status_model import CurrentStatusModel
from .track_or_release_label_model import TrackOrReleaseLabelModel
from .release_track_model import ReleaseTrackModel
from .release_key_model import ReleaseKeyModel
from .track_or_release_artist_model import TrackOrReleaseArtistModel
from .release_aggregator_model import ReleaseAggregatorModel
from .price_model import PriceModel
from .genre_model import GenreModel

# Union type for ReleasesDefaultModelGenre
# Pydantic will attempt to validate against each type in order
ReleasesDefaultModelGenre = Union[List[GenreModel], GenreModel]
# TypeAdapter for runtime validation of ReleasesDefaultModelGenre
# This allows validation of Union types which are not directly instantiable
from pydantic import TypeAdapter

ReleasesDefaultModelGenre_adapter = TypeAdapter(ReleasesDefaultModelGenre)


class ReleasesDefaultModel(BaseModel):
    """ReleasesDefaultModel

    :param score: score
    :type score: float
    :param current_status: current_status, defaults to None
    :type current_status: List[CurrentStatusModel], optional
    :param genre: genre, defaults to None
    :type genre: ReleasesDefaultModelGenre, optional
    :param label: label
    :type label: TrackOrReleaseLabelModel
    :param tracks: tracks, defaults to None
    :type tracks: List[ReleaseTrackModel], optional
    :param key: key, defaults to None
    :type key: List[ReleaseKeyModel], optional
    :param artists: artists, defaults to None
    :type artists: List[TrackOrReleaseArtistModel], optional
    :param aggregator: aggregator
    :type aggregator: ReleaseAggregatorModel
    :param available_worldwide: available_worldwide
    :type available_worldwide: int
    :param catalog_number: catalog_number, defaults to None
    :type catalog_number: str, optional
    :param create_date: create_date, defaults to None
    :type create_date: str, optional
    :param encoded_date: encoded_date, defaults to None
    :type encoded_date: str, optional
    :param exclusive: exclusive
    :type exclusive: int
    :param exclusive_date: exclusive_date, defaults to None
    :type exclusive_date: str, optional
    :param streaming_date: streaming_date, defaults to None
    :type streaming_date: str, optional
    :param preorder_date: preorder_date, defaults to None
    :type preorder_date: str, optional
    :param label_manager: label_manager, defaults to None
    :type label_manager: str, optional
    :param pre_order_date: pre_order_date, defaults to None
    :type pre_order_date: str, optional
    :param publish_date: publish_date
    :type publish_date: str
    :param release_date: release_date
    :type release_date: str
    :param release_id: release_id
    :type release_id: int
    :param release_name: release_name
    :type release_name: str
    :param release_type: release_type
    :type release_type: str
    :param status: status
    :type status: int
    :param upc: upc, defaults to None
    :type upc: str, optional
    :param update_date: update_date
    :type update_date: str
    :param price: price, defaults to None
    :type price: PriceModel, optional
    :param is_explicit: is_explicit, defaults to None
    :type is_explicit: bool, optional
    :param track_count: track_count, defaults to None
    :type track_count: int, optional
    :param release_image_uri: release_image_uri, defaults to None
    :type release_image_uri: str, optional
    :param release_image_dynamic_uri: release_image_dynamic_uri, defaults to None
    :type release_image_dynamic_uri: str, optional
    :param downloads: downloads, defaults to None
    :type downloads: int, optional
    :param is_hype: is_hype, defaults to None
    :type is_hype: bool, optional
    :param is_pre_order: is_pre_order, defaults to None
    :type is_pre_order: bool, optional
    :param plays: plays, defaults to None
    :type plays: int, optional
    """

    score: float
    current_status: Optional[List[CurrentStatusModel]] = Field(default=None)
    genre: Optional[ReleasesDefaultModelGenre] = Field(default=None)
    label: TrackOrReleaseLabelModel
    tracks: Optional[List[ReleaseTrackModel]] = Field(default=None)
    key: Optional[List[ReleaseKeyModel]] = Field(default=None)
    artists: Optional[List[TrackOrReleaseArtistModel]] = Field(default=None)
    aggregator: ReleaseAggregatorModel
    available_worldwide: int
    catalog_number: Optional[str] = Field(default=None)
    create_date: Optional[str] = Field(default=None)
    encoded_date: Optional[str] = Field(default=None)
    exclusive: int
    exclusive_date: Optional[str] = Field(default=None)
    streaming_date: Optional[str] = Field(default=None)
    preorder_date: Optional[str] = Field(default=None)
    label_manager: Optional[str] = Field(default=None)
    pre_order_date: Optional[str] = Field(default=None)
    publish_date: str
    release_date: str
    release_id: int
    release_name: str
    release_type: str
    status: int
    upc: Optional[str] = Field(default=None)
    update_date: str
    price: Optional[PriceModel] = Field(default=None)
    is_explicit: Optional[bool] = Field(default=None)
    track_count: Optional[int] = Field(default=None)
    release_image_uri: Optional[str] = Field(default=None)
    release_image_dynamic_uri: Optional[str] = Field(default=None)
    downloads: Optional[int] = Field(default=None)
    is_hype: Optional[bool] = Field(default=None)
    is_pre_order: Optional[bool] = Field(default=None)
    plays: Optional[int] = Field(default=None)
