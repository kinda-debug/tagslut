export interface TracksSearchSearchV1TracksGetParams {
  q: string;
  count?: number;
  preorder?: boolean;
  fromPublishDate?: string;
  toPublishDate?: string;
  fromReleaseDate?: string;
  toReleaseDate?: string;
  genreId?: string;
  genreName?: string;
  mixName?: string;
  fromBpm?: number;
  toBpm?: number;
  keyName?: string;
  mixNameWeight?: number;
  labelNameWeight?: number;
  djEdits?: boolean;
  ugcRemixes?: boolean;
  djEditsAndUgcRemixes?: boolean;
  isAvailableForStreaming?: boolean;
}

export interface ReleasesSearchSearchV1ReleasesGetParams {
  q: string;
  count?: number;
  preorder?: boolean;
  fromPublishDate?: string;
  toPublishDate?: string;
  fromReleaseDate?: string;
  toReleaseDate?: string;
  genreId?: string;
  genreName?: string;
  releaseNameWeight?: number;
  labelNameWeight?: number;
}

export interface ArtistsSearchSearchV1ArtistsGetParams {
  q: string;
  count?: number;
  genreId?: string;
}

export interface LabelsSearchSearchV1LabelsGetParams {
  q: string;
  count?: number;
}

export interface ChartsSearchSearchV1ChartsGetParams {
  q: string;
  count?: number;
  genreId?: string;
  genreName?: string;
  isApproved?: boolean;
  fromPublishDate?: string;
  toPublishDate?: string;
}

export interface AllSearchSearchV1AllGetParams {
  q: string;
  count?: number;
  preorder?: boolean;
  tracksFromReleaseDate?: string;
  tracksToReleaseDate?: string;
  releasesFromReleaseDate?: string;
  releasesToReleaseDate?: string;
  isApproved?: boolean;
  isAvailableForStreaming?: boolean;
}
