from __future__ import annotations
from typing import Union
from typing import List
from pydantic import Field
from typing import Optional
from typing import Annotated
from pydantic import TypeAdapter
from .utils.base_model import BaseModel
from .track_or_release_artist_model import TrackOrReleaseArtistModel
from .current_status_model import CurrentStatusModel
from .track_or_release_label_model import TrackOrReleaseLabelModel
from .track_release_model import TrackReleaseModel
from .track_suggest_model import TrackSuggestModel
from .price_model import PriceModel
from .sub_genre_model import SubGenreModel
from .genre_model import GenreModel

# Union type for TracksDefaultModelGenre
# Pydantic will attempt to validate against each type in order
TracksDefaultModelGenre = Union[List[GenreModel], GenreModel]
# TypeAdapter for runtime validation of TracksDefaultModelGenre
# This allows validation of Union types which are not directly instantiable
from pydantic import TypeAdapter

TracksDefaultModelGenre_adapter = TypeAdapter(TracksDefaultModelGenre)


class TracksDefaultModel(BaseModel):
    """TracksDefaultModel

    :param score: score
    :type score: float
    :param add_date: add_date
    :type add_date: str
    :param artists: artists
    :type artists: List[TrackOrReleaseArtistModel]
    :param available_worldwide: available_worldwide
    :type available_worldwide: int
    :param bpm: bpm, defaults to None
    :type bpm: int, optional
    :param catalog_number: catalog_number, defaults to None
    :type catalog_number: str, optional
    :param change_date: change_date
    :type change_date: str
    :param chord_type_id: chord_type_id, defaults to None
    :type chord_type_id: int, optional
    :param current_status: current_status
    :type current_status: CurrentStatusModel
    :param enabled: enabled
    :type enabled: int
    :param encode_status: encode_status
    :type encode_status: str
    :param exclusive_date: exclusive_date, defaults to None
    :type exclusive_date: str, optional
    :param exclusive_period: exclusive_period
    :type exclusive_period: int
    :param free_download_end_date: free_download_end_date, defaults to None
    :type free_download_end_date: str, optional
    :param free_download_start_date: free_download_start_date, defaults to None
    :type free_download_start_date: str, optional
    :param genre_enabled: genre_enabled
    :type genre_enabled: int
    :param guid: guid, defaults to None
    :type guid: str, optional
    :param is_available_for_streaming: is_available_for_streaming
    :type is_available_for_streaming: int
    :param is_classic: is_classic
    :type is_classic: int
    :param isrc: isrc, defaults to None
    :type isrc: str, optional
    :param key_id: key_id, defaults to None
    :type key_id: int, optional
    :param key_name: key_name, defaults to None
    :type key_name: str, optional
    :param label: label
    :type label: TrackOrReleaseLabelModel
    :param label_manager: label_manager
    :type label_manager: str
    :param length: length, defaults to None
    :type length: int, optional
    :param mix_name: mix_name
    :type mix_name: str
    :param pre_order_date: pre_order_date, defaults to None
    :type pre_order_date: str, optional
    :param publish_date: publish_date
    :type publish_date: str
    :param publish_status: publish_status
    :type publish_status: str
    :param release: release
    :type release: TrackReleaseModel
    :param release_date: release_date
    :type release_date: str
    :param sale_type: sale_type
    :type sale_type: str
    :param streaming_date: streaming_date, defaults to None
    :type streaming_date: str, optional
    :param suggest: suggest
    :type suggest: TrackSuggestModel
    :param supplier_id: supplier_id
    :type supplier_id: int
    :param track_id: track_id
    :type track_id: int
    :param track_name: track_name
    :type track_name: str
    :param track_number: track_number
    :type track_number: int
    :param update_date: update_date
    :type update_date: str
    :param was_ever_exclusive: was_ever_exclusive
    :type was_ever_exclusive: int
    :param downloads: downloads, defaults to None
    :type downloads: int, optional
    :param plays: plays, defaults to None
    :type plays: int, optional
    :param price: price, defaults to None
    :type price: PriceModel, optional
    :param is_explicit: is_explicit, defaults to None
    :type is_explicit: bool, optional
    :param is_available_for_alacarte: is_available_for_alacarte, defaults to None
    :type is_available_for_alacarte: bool, optional
    :param is_dj_edit: is_dj_edit, defaults to None
    :type is_dj_edit: bool, optional
    :param is_ugc_remix: is_ugc_remix, defaults to None
    :type is_ugc_remix: bool, optional
    :param is_pre_order: is_pre_order, defaults to None
    :type is_pre_order: bool, optional
    :param track_image_uri: track_image_uri, defaults to None
    :type track_image_uri: str, optional
    :param track_image_dynamic_uri: track_image_dynamic_uri, defaults to None
    :type track_image_dynamic_uri: str, optional
    :param genre: genre, defaults to None
    :type genre: TracksDefaultModelGenre, optional
    :param sub_genre: sub_genre, defaults to None
    :type sub_genre: SubGenreModel, optional
    """

    score: float
    add_date: str
    artists: List[TrackOrReleaseArtistModel]
    available_worldwide: int
    bpm: Optional[int] = Field(default=None)
    catalog_number: Optional[str] = Field(default=None)
    change_date: str
    chord_type_id: Optional[int] = Field(default=None)
    current_status: CurrentStatusModel
    enabled: int
    encode_status: str
    exclusive_date: Optional[str] = Field(default=None)
    exclusive_period: int
    free_download_end_date: Optional[str] = Field(default=None)
    free_download_start_date: Optional[str] = Field(default=None)
    genre_enabled: int
    guid: Optional[str] = Field(default=None)
    is_available_for_streaming: int
    is_classic: int
    isrc: Optional[str] = Field(default=None)
    key_id: Optional[int] = Field(default=None)
    key_name: Optional[str] = Field(default=None)
    label: TrackOrReleaseLabelModel
    label_manager: str
    length: Optional[int] = Field(default=None)
    mix_name: str
    pre_order_date: Optional[str] = Field(default=None)
    publish_date: str
    publish_status: str
    release: TrackReleaseModel
    release_date: str
    sale_type: str
    streaming_date: Optional[str] = Field(default=None)
    suggest: TrackSuggestModel
    supplier_id: int
    track_id: int
    track_name: str
    track_number: int
    update_date: str
    was_ever_exclusive: int
    downloads: Optional[int] = Field(default=None)
    plays: Optional[int] = Field(default=None)
    price: Optional[PriceModel] = Field(default=None)
    is_explicit: Optional[bool] = Field(default=None)
    is_available_for_alacarte: Optional[bool] = Field(default=None)
    is_dj_edit: Optional[bool] = Field(default=None)
    is_ugc_remix: Optional[bool] = Field(default=None)
    is_pre_order: Optional[bool] = Field(default=None)
    track_image_uri: Optional[str] = Field(default=None)
    track_image_dynamic_uri: Optional[str] = Field(default=None)
    genre: Optional[TracksDefaultModelGenre] = Field(default=None)
    sub_genre: Optional[SubGenreModel] = Field(default=None)
