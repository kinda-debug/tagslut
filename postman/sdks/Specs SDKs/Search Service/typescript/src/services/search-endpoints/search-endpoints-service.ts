import { z } from 'zod';
import { BaseService } from '../base-service';
import { ContentType, HttpResponse, SdkConfig } from '../../http/types';
import { RequestBuilder } from '../../http/transport/request-builder';
import { SerializationStyle } from '../../http/serialization/base-serializer';
import { ThrowableError } from '../../http/errors/throwable-error';
import { Environment } from '../../http/environment';
import { TracksResponse, tracksResponseResponse } from './models/tracks-response';
import { HttpValidationError } from './models/http-validation-error';
import {
  AllSearchSearchV1AllGetParams,
  ArtistsSearchSearchV1ArtistsGetParams,
  ChartsSearchSearchV1ChartsGetParams,
  LabelsSearchSearchV1LabelsGetParams,
  ReleasesSearchSearchV1ReleasesGetParams,
  TracksSearchSearchV1TracksGetParams,
} from './request-params';
import { ReleasesResponse, releasesResponseResponse } from './models/releases-response';
import { ArtistsResponse, artistsResponseResponse } from './models/artists-response';
import { LabelsResponse, labelsResponseResponse } from './models/labels-response';
import { ChartsResponse, chartsResponseResponse } from './models/charts-response';
import { MultisearchResponse, multisearchResponseResponse } from './models/multisearch-response';

/**
 * Service class for SearchEndpointsService operations.
 * Provides methods to interact with SearchEndpointsService-related API endpoints.
 * All methods return promises and handle request/response serialization automatically.
 */
export class SearchEndpointsService extends BaseService {
  protected tracksSearchSearchV1TracksGetConfig?: Partial<SdkConfig>;

  protected releasesSearchSearchV1ReleasesGetConfig?: Partial<SdkConfig>;

  protected artistsSearchSearchV1ArtistsGetConfig?: Partial<SdkConfig>;

  protected labelsSearchSearchV1LabelsGetConfig?: Partial<SdkConfig>;

  protected chartsSearchSearchV1ChartsGetConfig?: Partial<SdkConfig>;

  protected allSearchSearchV1AllGetConfig?: Partial<SdkConfig>;

  /**
   * Sets method-level configuration for tracksSearchSearchV1TracksGet.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setTracksSearchSearchV1TracksGetConfig(config: Partial<SdkConfig>): this {
    this.tracksSearchSearchV1TracksGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for releasesSearchSearchV1ReleasesGet.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setReleasesSearchSearchV1ReleasesGetConfig(config: Partial<SdkConfig>): this {
    this.releasesSearchSearchV1ReleasesGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for artistsSearchSearchV1ArtistsGet.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setArtistsSearchSearchV1ArtistsGetConfig(config: Partial<SdkConfig>): this {
    this.artistsSearchSearchV1ArtistsGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for labelsSearchSearchV1LabelsGet.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setLabelsSearchSearchV1LabelsGetConfig(config: Partial<SdkConfig>): this {
    this.labelsSearchSearchV1LabelsGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for chartsSearchSearchV1ChartsGet.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setChartsSearchSearchV1ChartsGetConfig(config: Partial<SdkConfig>): this {
    this.chartsSearchSearchV1ChartsGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for allSearchSearchV1AllGet.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setAllSearchSearchV1AllGetConfig(config: Partial<SdkConfig>): this {
    this.allSearchSearchV1AllGetConfig = config;
    return this;
  }

  /**
 * Returns a set of track results
 * @param {string} params.q - Search query text
 * @param {number} [params.count] - The number of results returned in the response
 * @param {boolean} [params.preorder] - 
When FALSE, the response will not include tracks in a pre-order status.

When TRUE, the response will include tracks that are in a pre-order status

 * @param {string} [params.fromPublishDate] - 
The date a track was published on Beatport.com or Beatsource.com.

Format: YYYY-MM-DD

 * @param {string} [params.toPublishDate] - 
The date a track was published on Beatport.com or Beatsource.com.

Format: YYYY-MM-DD

 * @param {string} [params.fromReleaseDate] - 
The date a track was released to the public.

Format: YYYY-MM-DD

 * @param {string} [params.toReleaseDate] - 
The date a track was released to the public.

Format: YYYY-MM-DD

 * @param {string} [params.genreId] - 
Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added
by separating them with a comma, ex: (89, 6, 14).

For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/

 * @param {string} [params.genreName] - 
Returns tracks that have a genre which partially matches the value inputed.

For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc.

For a list of genres and their names, make a GET call to our API route /catalog/genres/

 * @param {string} [params.mixName] - Search for a specific mix name, ex: original
 * @param {number} [params.fromBpm] - 
 * @param {number} [params.toBpm] - 
 * @param {string} [params.keyName] - 
Search for a specific key in the following format:

A Major, A Minor, A# Major, A# Minor, Ab Major, Ab Minor

 * @param {number} [params.mixNameWeight] - 
This parameter determines how much weight to put on mix_name using the search query text from q.

The higher the value the more weight is put on matching q to mix_name

 * @param {number} [params.labelNameWeight] - 
This parameter determines how much weight to put on label_name using the search query text from q.

The higher the value the more weight is put on matching q to label_name

 * @param {boolean} [params.djEdits] - 
When FALSE, the response will exclude DJ Edit tracks.

When TRUE, the response will return only DJ Edit tracks.

 * @param {boolean} [params.ugcRemixes] - 
When FALSE, the response will exclude UGC Remix tracks.

When TRUE, the response will return only UGC Remix tracks.

 * @param {boolean} [params.djEditsAndUgcRemixes] - 
When FALSE, the response will exclude DJ Edits and UGC Remix tracks.

When TRUE, the response will return only DJ Edits or UGC Remix tracks.

When parameter is not included, the response will include DJ edits and UGC remixes amongst other tracks.

 * @param {boolean} [params.isAvailableForStreaming] - 
By default the response will return both streamable and non-streamable tracks.

**Note**: This is dependent on your app scope, if your scope inherently does not allow
non-streamable tracks then only streamable tracks will be returned always.

When FALSE, the response will return only tracks that are not available for streaming.

When TRUE, the response will return only tracks that are available for streaming.

 * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
 * @returns {Promise<HttpResponse<TracksResponse>>} - Successful Response
 */
  async tracksSearchSearchV1TracksGet(
    params: TracksSearchSearchV1TracksGetParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<TracksResponse> {
    const resolvedConfig = this.getResolvedConfig(
      this.tracksSearchSearchV1TracksGetConfig,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/search/v1/tracks')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token)
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: tracksResponseResponse,
        contentType: ContentType.Json,
        status: 200,
      })
      .addError({
        error: HttpValidationError,
        contentType: ContentType.Json,
        status: 422,
      })
      .addQueryParam({
        key: 'q',
        value: params?.q,
      })
      .addQueryParam({
        key: 'count',
        value: params?.count,
      })
      .addQueryParam({
        key: 'preorder',
        value: params?.preorder,
      })
      .addQueryParam({
        key: 'from_publish_date',
        value: params?.fromPublishDate,
      })
      .addQueryParam({
        key: 'to_publish_date',
        value: params?.toPublishDate,
      })
      .addQueryParam({
        key: 'from_release_date',
        value: params?.fromReleaseDate,
      })
      .addQueryParam({
        key: 'to_release_date',
        value: params?.toReleaseDate,
      })
      .addQueryParam({
        key: 'genre_id',
        value: params?.genreId,
      })
      .addQueryParam({
        key: 'genre_name',
        value: params?.genreName,
      })
      .addQueryParam({
        key: 'mix_name',
        value: params?.mixName,
      })
      .addQueryParam({
        key: 'from_bpm',
        value: params?.fromBpm,
      })
      .addQueryParam({
        key: 'to_bpm',
        value: params?.toBpm,
      })
      .addQueryParam({
        key: 'key_name',
        value: params?.keyName,
      })
      .addQueryParam({
        key: 'mix_name_weight',
        value: params?.mixNameWeight,
      })
      .addQueryParam({
        key: 'label_name_weight',
        value: params?.labelNameWeight,
      })
      .addQueryParam({
        key: 'dj_edits',
        value: params?.djEdits,
      })
      .addQueryParam({
        key: 'ugc_remixes',
        value: params?.ugcRemixes,
      })
      .addQueryParam({
        key: 'dj_edits_and_ugc_remixes',
        value: params?.djEditsAndUgcRemixes,
      })
      .addQueryParam({
        key: 'is_available_for_streaming',
        value: params?.isAvailableForStreaming,
      })
      .build();
    return this.client.callDirect<TracksResponse>(request);
  }

  /**
 * Returns a set of release results
 * @param {string} params.q - Search query text
 * @param {number} [params.count] - The number of results returned in the response
 * @param {boolean} [params.preorder] - 
When FALSE, the response will not include tracks in a pre-order status.

When TRUE, the response will include tracks that are in a pre-order status

 * @param {string} [params.fromPublishDate] - 
The date a track was published on Beatport.com or Beatsource.com.

Format: YYYY-MM-DD

 * @param {string} [params.toPublishDate] - 
The date a track was published on Beatport.com or Beatsource.com.

Format: YYYY-MM-DD

 * @param {string} [params.fromReleaseDate] - 
The date a track was released to the public.

Format: YYYY-MM-DD

 * @param {string} [params.toReleaseDate] - 
The date a track was released to the public.

Format: YYYY-MM-DD

 * @param {string} [params.genreId] - 
Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added
by separating them with a comma, ex: (89, 6, 14).

For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/

 * @param {string} [params.genreName] - 
Returns tracks that have a genre which partially matches the value inputed.

For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc.

For a list of genres and their names, make a GET call to our API route /catalog/genres/

 * @param {number} [params.releaseNameWeight] - 
 * @param {number} [params.labelNameWeight] - 
This parameter determines how much weight to put on label_name using the search query text from q.

The higher the value the more weight is put on matching q to label_name

 * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
 * @returns {Promise<HttpResponse<ReleasesResponse>>} - Successful Response
 */
  async releasesSearchSearchV1ReleasesGet(
    params: ReleasesSearchSearchV1ReleasesGetParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<ReleasesResponse> {
    const resolvedConfig = this.getResolvedConfig(
      this.releasesSearchSearchV1ReleasesGetConfig,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/search/v1/releases')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token)
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: releasesResponseResponse,
        contentType: ContentType.Json,
        status: 200,
      })
      .addError({
        error: HttpValidationError,
        contentType: ContentType.Json,
        status: 422,
      })
      .addQueryParam({
        key: 'q',
        value: params?.q,
      })
      .addQueryParam({
        key: 'count',
        value: params?.count,
      })
      .addQueryParam({
        key: 'preorder',
        value: params?.preorder,
      })
      .addQueryParam({
        key: 'from_publish_date',
        value: params?.fromPublishDate,
      })
      .addQueryParam({
        key: 'to_publish_date',
        value: params?.toPublishDate,
      })
      .addQueryParam({
        key: 'from_release_date',
        value: params?.fromReleaseDate,
      })
      .addQueryParam({
        key: 'to_release_date',
        value: params?.toReleaseDate,
      })
      .addQueryParam({
        key: 'genre_id',
        value: params?.genreId,
      })
      .addQueryParam({
        key: 'genre_name',
        value: params?.genreName,
      })
      .addQueryParam({
        key: 'release_name_weight',
        value: params?.releaseNameWeight,
      })
      .addQueryParam({
        key: 'label_name_weight',
        value: params?.labelNameWeight,
      })
      .build();
    return this.client.callDirect<ReleasesResponse>(request);
  }

  /**
 * Returns a set of artist results
 * @param {string} params.q - Search query text
 * @param {number} [params.count] - The number of results returned in the response
 * @param {string} [params.genreId] - 
Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added
by separating them with a comma, ex: (89, 6, 14).

For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/

 * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
 * @returns {Promise<HttpResponse<ArtistsResponse>>} - Successful Response
 */
  async artistsSearchSearchV1ArtistsGet(
    params: ArtistsSearchSearchV1ArtistsGetParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<ArtistsResponse> {
    const resolvedConfig = this.getResolvedConfig(
      this.artistsSearchSearchV1ArtistsGetConfig,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/search/v1/artists')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token)
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: artistsResponseResponse,
        contentType: ContentType.Json,
        status: 200,
      })
      .addError({
        error: HttpValidationError,
        contentType: ContentType.Json,
        status: 422,
      })
      .addQueryParam({
        key: 'q',
        value: params?.q,
      })
      .addQueryParam({
        key: 'count',
        value: params?.count,
      })
      .addQueryParam({
        key: 'genre_id',
        value: params?.genreId,
      })
      .build();
    return this.client.callDirect<ArtistsResponse>(request);
  }

  /**
   * Returns a set of label results
   * @param {string} params.q - Search query text
   * @param {number} [params.count] - The number of results returned in the response
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<LabelsResponse>>} - Successful Response
   */
  async labelsSearchSearchV1LabelsGet(
    params: LabelsSearchSearchV1LabelsGetParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<LabelsResponse> {
    const resolvedConfig = this.getResolvedConfig(
      this.labelsSearchSearchV1LabelsGetConfig,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/search/v1/labels')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token)
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: labelsResponseResponse,
        contentType: ContentType.Json,
        status: 200,
      })
      .addError({
        error: HttpValidationError,
        contentType: ContentType.Json,
        status: 422,
      })
      .addQueryParam({
        key: 'q',
        value: params?.q,
      })
      .addQueryParam({
        key: 'count',
        value: params?.count,
      })
      .build();
    return this.client.callDirect<LabelsResponse>(request);
  }

  /**
 * Returns a set of chart results
 * @param {string} params.q - Search query text
 * @param {number} [params.count] - The number of results returned in the response
 * @param {string} [params.genreId] - 
Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added
by separating them with a comma, ex: (89, 6, 14).

For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/

 * @param {string} [params.genreName] - 
Returns tracks that have a genre which partially matches the value inputed.

For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc.

For a list of genres and their names, make a GET call to our API route /catalog/genres/

 * @param {boolean} [params.isApproved] - 
When TRUE, the response will only include charts that have been approved.

When FALSE, the response will include all charts.

It is recommended to leave this set to TRUE

 * @param {string} [params.fromPublishDate] - 
The date a chart was published on Beatport.com or Beatsource.com.

Format: YYYY-MM-DD

 * @param {string} [params.toPublishDate] - 
The date a chart was published on Beatport.com or Beatsource.com.

Format: YYYY-MM-DD

 * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
 * @returns {Promise<HttpResponse<ChartsResponse>>} - Successful Response
 */
  async chartsSearchSearchV1ChartsGet(
    params: ChartsSearchSearchV1ChartsGetParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<ChartsResponse> {
    const resolvedConfig = this.getResolvedConfig(
      this.chartsSearchSearchV1ChartsGetConfig,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/search/v1/charts')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token)
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: chartsResponseResponse,
        contentType: ContentType.Json,
        status: 200,
      })
      .addError({
        error: HttpValidationError,
        contentType: ContentType.Json,
        status: 422,
      })
      .addQueryParam({
        key: 'q',
        value: params?.q,
      })
      .addQueryParam({
        key: 'count',
        value: params?.count,
      })
      .addQueryParam({
        key: 'genre_id',
        value: params?.genreId,
      })
      .addQueryParam({
        key: 'genre_name',
        value: params?.genreName,
      })
      .addQueryParam({
        key: 'is_approved',
        value: params?.isApproved,
      })
      .addQueryParam({
        key: 'from_publish_date',
        value: params?.fromPublishDate,
      })
      .addQueryParam({
        key: 'to_publish_date',
        value: params?.toPublishDate,
      })
      .build();
    return this.client.callDirect<ChartsResponse>(request);
  }

  /**
 * Returns a set of results for all search types
 * @param {string} params.q - Search query text
 * @param {number} [params.count] - The number of results returned in the response
 * @param {boolean} [params.preorder] - 
When FALSE, the response will not include tracks or releases in a pre-order status.

When TRUE, the response will include tracks and releases that are in a pre-order status

 * @param {string} [params.tracksFromReleaseDate] - 
The date a track was released to the public.

Format: YYYY-MM-DD

 * @param {string} [params.tracksToReleaseDate] - 
The date a track was released to the public.

Format: YYYY-MM-DD

 * @param {string} [params.releasesFromReleaseDate] - 
The date a release was released to the public.

Format: YYYY-MM-DD

 * @param {string} [params.releasesToReleaseDate] - 
The date a release was released to the public.

Format: YYYY-MM-DD

 * @param {boolean} [params.isApproved] - 
When TRUE, the response will only include charts that have been approved.

When FALSE, the response will include all charts.

It is recommended to leave this set to TRUE

 * @param {boolean} [params.isAvailableForStreaming] - 
By default the response will return both streamable and non-streamable tracks.

**Note**: This is dependent on your app scope, if your scope inherently does not allow
non-streamable tracks then only streamable tracks will be returned always.

When FALSE, the response will return only tracks that are not available for streaming.

When TRUE, the response will return only tracks that are available for streaming.

 * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
 * @returns {Promise<HttpResponse<MultisearchResponse>>} - Successful Response
 */
  async allSearchSearchV1AllGet(
    params: AllSearchSearchV1AllGetParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<MultisearchResponse> {
    const resolvedConfig = this.getResolvedConfig(
      this.allSearchSearchV1AllGetConfig,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/search/v1/all')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token)
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: multisearchResponseResponse,
        contentType: ContentType.Json,
        status: 200,
      })
      .addError({
        error: HttpValidationError,
        contentType: ContentType.Json,
        status: 422,
      })
      .addQueryParam({
        key: 'q',
        value: params?.q,
      })
      .addQueryParam({
        key: 'count',
        value: params?.count,
      })
      .addQueryParam({
        key: 'preorder',
        value: params?.preorder,
      })
      .addQueryParam({
        key: 'tracks_from_release_date',
        value: params?.tracksFromReleaseDate,
      })
      .addQueryParam({
        key: 'tracks_to_release_date',
        value: params?.tracksToReleaseDate,
      })
      .addQueryParam({
        key: 'releases_from_release_date',
        value: params?.releasesFromReleaseDate,
      })
      .addQueryParam({
        key: 'releases_to_release_date',
        value: params?.releasesToReleaseDate,
      })
      .addQueryParam({
        key: 'is_approved',
        value: params?.isApproved,
      })
      .addQueryParam({
        key: 'is_available_for_streaming',
        value: params?.isAvailableForStreaming,
      })
      .build();
    return this.client.callDirect<MultisearchResponse>(request);
  }
}
