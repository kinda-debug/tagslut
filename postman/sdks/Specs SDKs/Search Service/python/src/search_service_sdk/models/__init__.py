from .health_check_response import HealthCheckResponse
from .tracks_response import TracksResponse
from .releases_response import ReleasesResponse
from .artists_response import ArtistsResponse
from .labels_response import LabelsResponse
from .charts_response import ChartsResponse
from .multisearch_response import MultisearchResponse
from .tracks_default_model import TracksDefaultModel, TracksDefaultModelGenre
from .track_or_release_artist_model import TrackOrReleaseArtistModel
from .current_status_model import CurrentStatusModel
from .track_or_release_label_model import TrackOrReleaseLabelModel
from .track_release_model import TrackReleaseModel
from .track_suggest_model import TrackSuggestModel
from .price_model import PriceModel
from .sub_genre_model import SubGenreModel
from .genre_model import GenreModel
from .releases_default_model import ReleasesDefaultModel, ReleasesDefaultModelGenre
from .release_track_model import ReleaseTrackModel
from .release_key_model import ReleaseKeyModel
from .release_aggregator_model import ReleaseAggregatorModel
from .artists_default_model import ArtistsDefaultModel
from .labels_default_model import LabelsDefaultModel
from .charts_default_model import ChartsDefaultModel
from .http_validation_error import HttpValidationError
from .validation_error import ValidationError, Loc

# Rebuild models to resolve circular forward references
# This ensures Pydantic can properly validate models that reference each other
HealthCheckResponse.model_rebuild()
TracksResponse.model_rebuild()
ReleasesResponse.model_rebuild()
ArtistsResponse.model_rebuild()
LabelsResponse.model_rebuild()
ChartsResponse.model_rebuild()
MultisearchResponse.model_rebuild()
TracksDefaultModel.model_rebuild()
TrackOrReleaseArtistModel.model_rebuild()
CurrentStatusModel.model_rebuild()
TrackOrReleaseLabelModel.model_rebuild()
TrackReleaseModel.model_rebuild()
TrackSuggestModel.model_rebuild()
PriceModel.model_rebuild()
SubGenreModel.model_rebuild()
GenreModel.model_rebuild()
ReleasesDefaultModel.model_rebuild()
ReleaseTrackModel.model_rebuild()
ReleaseKeyModel.model_rebuild()
ReleaseAggregatorModel.model_rebuild()
ArtistsDefaultModel.model_rebuild()
LabelsDefaultModel.model_rebuild()
ChartsDefaultModel.model_rebuild()
ValidationError.model_rebuild()
