from __future__ import annotations
from pydantic import Field
from typing import Optional
from typing import Union
from .utils.base_model import BaseModel
from .tracks_response import TracksResponse
from .artists_response import ArtistsResponse
from .charts_response import ChartsResponse
from .labels_response import LabelsResponse
from .releases_response import ReleasesResponse


class MultisearchResponse(BaseModel):
    """Response model for the `all-search` endpoint.

    :param tracks: Response model for the `tracks` endpoint.
    :type tracks: TracksResponse
    :param artists: artists
    :type artists: ArtistsResponse
    :param charts: charts
    :type charts: ChartsResponse
    :param labels: labels
    :type labels: LabelsResponse
    :param releases: Response model for the `releases` endpoint.
    :type releases: ReleasesResponse
    """

    tracks: TracksResponse = Field(
        description="Response model for the `tracks` endpoint."
    )
    artists: ArtistsResponse
    charts: ChartsResponse
    labels: LabelsResponse
    releases: ReleasesResponse = Field(
        description="Response model for the `releases` endpoint."
    )
