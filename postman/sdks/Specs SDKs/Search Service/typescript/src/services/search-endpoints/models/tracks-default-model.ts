import { z } from 'zod';
import {
  TrackOrReleaseArtistModel,
  trackOrReleaseArtistModel,
  trackOrReleaseArtistModelRequest,
  trackOrReleaseArtistModelResponse,
} from './track-or-release-artist-model';
import {
  CurrentStatusModel,
  currentStatusModel,
  currentStatusModelRequest,
  currentStatusModelResponse,
} from './current-status-model';
import {
  TrackOrReleaseLabelModel,
  trackOrReleaseLabelModel,
  trackOrReleaseLabelModelRequest,
  trackOrReleaseLabelModelResponse,
} from './track-or-release-label-model';
import {
  TrackReleaseModel,
  trackReleaseModel,
  trackReleaseModelRequest,
  trackReleaseModelResponse,
} from './track-release-model';
import {
  TrackSuggestModel,
  trackSuggestModel,
  trackSuggestModelRequest,
  trackSuggestModelResponse,
} from './track-suggest-model';
import { PriceModel, priceModel, priceModelRequest, priceModelResponse } from './price-model';
import {
  TracksDefaultModelGenre,
  tracksDefaultModelGenre,
  tracksDefaultModelGenreRequest,
  tracksDefaultModelGenreResponse,
} from './tracks-default-model-genre';
import {
  SubGenreModel,
  subGenreModel,
  subGenreModelRequest,
  subGenreModelResponse,
} from './sub-genre-model';

/**
 * Zod schema for the TracksDefaultModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const tracksDefaultModel = z.lazy(() => {
  return z.object({
    score: z.number(),
    addDate: z.string(),
    artists: z.array(trackOrReleaseArtistModel),
    availableWorldwide: z.number(),
    bpm: z.number().optional().nullable(),
    catalogNumber: z.string().optional().nullable(),
    changeDate: z.string(),
    chordTypeId: z.number().optional().nullable(),
    currentStatus: currentStatusModel,
    enabled: z.number(),
    encodeStatus: z.string(),
    exclusiveDate: z.string().optional().nullable(),
    exclusivePeriod: z.number(),
    freeDownloadEndDate: z.string().optional().nullable(),
    freeDownloadStartDate: z.string().optional().nullable(),
    genreEnabled: z.number(),
    guid: z.string().optional().nullable(),
    isAvailableForStreaming: z.number(),
    isClassic: z.number(),
    isrc: z.string().optional().nullable(),
    keyId: z.number().optional().nullable(),
    keyName: z.string().optional().nullable(),
    label: trackOrReleaseLabelModel,
    labelManager: z.string(),
    length: z.number().optional().nullable(),
    mixName: z.string(),
    preOrderDate: z.string().optional().nullable(),
    publishDate: z.string(),
    publishStatus: z.string(),
    release: trackReleaseModel,
    releaseDate: z.string(),
    saleType: z.string(),
    streamingDate: z.string().optional().nullable(),
    suggest: trackSuggestModel,
    supplierId: z.number(),
    trackId: z.number(),
    trackName: z.string(),
    trackNumber: z.number(),
    updateDate: z.string(),
    wasEverExclusive: z.number(),
    downloads: z.number().optional().nullable(),
    plays: z.number().optional().nullable(),
    price: priceModel.optional().nullable(),
    isExplicit: z.boolean().optional().nullable(),
    isAvailableForAlacarte: z.boolean().optional().nullable(),
    isDjEdit: z.boolean().optional().nullable(),
    isUgcRemix: z.boolean().optional().nullable(),
    isPreOrder: z.boolean().optional().nullable(),
    trackImageUri: z.string().optional().nullable(),
    trackImageDynamicUri: z.string().optional().nullable(),
    genre: tracksDefaultModelGenre.optional().nullable(),
    subGenre: subGenreModel.optional().nullable(),
  });
});

/**
 *
 * @typedef  {TracksDefaultModel} tracksDefaultModel
 * @property {number}
 * @property {string}
 * @property {TrackOrReleaseArtistModel[]}
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {CurrentStatusModel}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {TrackOrReleaseLabelModel}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {TrackReleaseModel}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {TrackSuggestModel}
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {number}
 * @property {number}
 * @property {number}
 * @property {PriceModel}
 * @property {boolean}
 * @property {boolean}
 * @property {boolean}
 * @property {boolean}
 * @property {boolean}
 * @property {string}
 * @property {string}
 * @property {TracksDefaultModelGenre}
 * @property {SubGenreModel}
 */
export type TracksDefaultModel = z.infer<typeof tracksDefaultModel>;

/**
 * Zod schema for mapping API responses to the TracksDefaultModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const tracksDefaultModelResponse = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      add_date: z.string(),
      artists: z.array(trackOrReleaseArtistModelResponse),
      available_worldwide: z.number(),
      bpm: z.number().optional().nullable(),
      catalog_number: z.string().optional().nullable(),
      change_date: z.string(),
      chord_type_id: z.number().optional().nullable(),
      current_status: currentStatusModelResponse,
      enabled: z.number(),
      encode_status: z.string(),
      exclusive_date: z.string().optional().nullable(),
      exclusive_period: z.number(),
      free_download_end_date: z.string().optional().nullable(),
      free_download_start_date: z.string().optional().nullable(),
      genre_enabled: z.number(),
      guid: z.string().optional().nullable(),
      is_available_for_streaming: z.number(),
      is_classic: z.number(),
      isrc: z.string().optional().nullable(),
      key_id: z.number().optional().nullable(),
      key_name: z.string().optional().nullable(),
      label: trackOrReleaseLabelModelResponse,
      label_manager: z.string(),
      length: z.number().optional().nullable(),
      mix_name: z.string(),
      pre_order_date: z.string().optional().nullable(),
      publish_date: z.string(),
      publish_status: z.string(),
      release: trackReleaseModelResponse,
      release_date: z.string(),
      sale_type: z.string(),
      streaming_date: z.string().optional().nullable(),
      suggest: trackSuggestModelResponse,
      supplier_id: z.number(),
      track_id: z.number(),
      track_name: z.string(),
      track_number: z.number(),
      update_date: z.string(),
      was_ever_exclusive: z.number(),
      downloads: z.number().optional().nullable(),
      plays: z.number().optional().nullable(),
      price: priceModelResponse.optional().nullable(),
      is_explicit: z.boolean().optional().nullable(),
      is_available_for_alacarte: z.boolean().optional().nullable(),
      is_dj_edit: z.boolean().optional().nullable(),
      is_ugc_remix: z.boolean().optional().nullable(),
      is_pre_order: z.boolean().optional().nullable(),
      track_image_uri: z.string().optional().nullable(),
      track_image_dynamic_uri: z.string().optional().nullable(),
      genre: tracksDefaultModelGenreResponse.optional().nullable(),
      sub_genre: subGenreModelResponse.optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      addDate: data['add_date'],
      artists: data['artists'],
      availableWorldwide: data['available_worldwide'],
      bpm: data['bpm'],
      catalogNumber: data['catalog_number'],
      changeDate: data['change_date'],
      chordTypeId: data['chord_type_id'],
      currentStatus: data['current_status'],
      enabled: data['enabled'],
      encodeStatus: data['encode_status'],
      exclusiveDate: data['exclusive_date'],
      exclusivePeriod: data['exclusive_period'],
      freeDownloadEndDate: data['free_download_end_date'],
      freeDownloadStartDate: data['free_download_start_date'],
      genreEnabled: data['genre_enabled'],
      guid: data['guid'],
      isAvailableForStreaming: data['is_available_for_streaming'],
      isClassic: data['is_classic'],
      isrc: data['isrc'],
      keyId: data['key_id'],
      keyName: data['key_name'],
      label: data['label'],
      labelManager: data['label_manager'],
      length: data['length'],
      mixName: data['mix_name'],
      preOrderDate: data['pre_order_date'],
      publishDate: data['publish_date'],
      publishStatus: data['publish_status'],
      release: data['release'],
      releaseDate: data['release_date'],
      saleType: data['sale_type'],
      streamingDate: data['streaming_date'],
      suggest: data['suggest'],
      supplierId: data['supplier_id'],
      trackId: data['track_id'],
      trackName: data['track_name'],
      trackNumber: data['track_number'],
      updateDate: data['update_date'],
      wasEverExclusive: data['was_ever_exclusive'],
      downloads: data['downloads'],
      plays: data['plays'],
      price: data['price'],
      isExplicit: data['is_explicit'],
      isAvailableForAlacarte: data['is_available_for_alacarte'],
      isDjEdit: data['is_dj_edit'],
      isUgcRemix: data['is_ugc_remix'],
      isPreOrder: data['is_pre_order'],
      trackImageUri: data['track_image_uri'],
      trackImageDynamicUri: data['track_image_dynamic_uri'],
      genre: data['genre'],
      subGenre: data['sub_genre'],
    }));
});

/**
 * Zod schema for mapping the TracksDefaultModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const tracksDefaultModelRequest = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      addDate: z.string(),
      artists: z.array(trackOrReleaseArtistModelRequest),
      availableWorldwide: z.number(),
      bpm: z.number().optional().nullable(),
      catalogNumber: z.string().optional().nullable(),
      changeDate: z.string(),
      chordTypeId: z.number().optional().nullable(),
      currentStatus: currentStatusModelRequest,
      enabled: z.number(),
      encodeStatus: z.string(),
      exclusiveDate: z.string().optional().nullable(),
      exclusivePeriod: z.number(),
      freeDownloadEndDate: z.string().optional().nullable(),
      freeDownloadStartDate: z.string().optional().nullable(),
      genreEnabled: z.number(),
      guid: z.string().optional().nullable(),
      isAvailableForStreaming: z.number(),
      isClassic: z.number(),
      isrc: z.string().optional().nullable(),
      keyId: z.number().optional().nullable(),
      keyName: z.string().optional().nullable(),
      label: trackOrReleaseLabelModelRequest,
      labelManager: z.string(),
      length: z.number().optional().nullable(),
      mixName: z.string(),
      preOrderDate: z.string().optional().nullable(),
      publishDate: z.string(),
      publishStatus: z.string(),
      release: trackReleaseModelRequest,
      releaseDate: z.string(),
      saleType: z.string(),
      streamingDate: z.string().optional().nullable(),
      suggest: trackSuggestModelRequest,
      supplierId: z.number(),
      trackId: z.number(),
      trackName: z.string(),
      trackNumber: z.number(),
      updateDate: z.string(),
      wasEverExclusive: z.number(),
      downloads: z.number().optional().nullable(),
      plays: z.number().optional().nullable(),
      price: priceModelRequest.optional().nullable(),
      isExplicit: z.boolean().optional().nullable(),
      isAvailableForAlacarte: z.boolean().optional().nullable(),
      isDjEdit: z.boolean().optional().nullable(),
      isUgcRemix: z.boolean().optional().nullable(),
      isPreOrder: z.boolean().optional().nullable(),
      trackImageUri: z.string().optional().nullable(),
      trackImageDynamicUri: z.string().optional().nullable(),
      genre: tracksDefaultModelGenreRequest.optional().nullable(),
      subGenre: subGenreModelRequest.optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      add_date: data['addDate'],
      artists: data['artists'],
      available_worldwide: data['availableWorldwide'],
      bpm: data['bpm'],
      catalog_number: data['catalogNumber'],
      change_date: data['changeDate'],
      chord_type_id: data['chordTypeId'],
      current_status: data['currentStatus'],
      enabled: data['enabled'],
      encode_status: data['encodeStatus'],
      exclusive_date: data['exclusiveDate'],
      exclusive_period: data['exclusivePeriod'],
      free_download_end_date: data['freeDownloadEndDate'],
      free_download_start_date: data['freeDownloadStartDate'],
      genre_enabled: data['genreEnabled'],
      guid: data['guid'],
      is_available_for_streaming: data['isAvailableForStreaming'],
      is_classic: data['isClassic'],
      isrc: data['isrc'],
      key_id: data['keyId'],
      key_name: data['keyName'],
      label: data['label'],
      label_manager: data['labelManager'],
      length: data['length'],
      mix_name: data['mixName'],
      pre_order_date: data['preOrderDate'],
      publish_date: data['publishDate'],
      publish_status: data['publishStatus'],
      release: data['release'],
      release_date: data['releaseDate'],
      sale_type: data['saleType'],
      streaming_date: data['streamingDate'],
      suggest: data['suggest'],
      supplier_id: data['supplierId'],
      track_id: data['trackId'],
      track_name: data['trackName'],
      track_number: data['trackNumber'],
      update_date: data['updateDate'],
      was_ever_exclusive: data['wasEverExclusive'],
      downloads: data['downloads'],
      plays: data['plays'],
      price: data['price'],
      is_explicit: data['isExplicit'],
      is_available_for_alacarte: data['isAvailableForAlacarte'],
      is_dj_edit: data['isDjEdit'],
      is_ugc_remix: data['isUgcRemix'],
      is_pre_order: data['isPreOrder'],
      track_image_uri: data['trackImageUri'],
      track_image_dynamic_uri: data['trackImageDynamicUri'],
      genre: data['genre'],
      sub_genre: data['subGenre'],
    }));
});
