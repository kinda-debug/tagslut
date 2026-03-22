import { z } from 'zod';
import {
  CurrentStatusModel,
  currentStatusModel,
  currentStatusModelRequest,
  currentStatusModelResponse,
} from './current-status-model';
import {
  ReleasesDefaultModelGenre,
  releasesDefaultModelGenre,
  releasesDefaultModelGenreRequest,
  releasesDefaultModelGenreResponse,
} from './releases-default-model-genre';
import {
  TrackOrReleaseLabelModel,
  trackOrReleaseLabelModel,
  trackOrReleaseLabelModelRequest,
  trackOrReleaseLabelModelResponse,
} from './track-or-release-label-model';
import {
  ReleaseTrackModel,
  releaseTrackModel,
  releaseTrackModelRequest,
  releaseTrackModelResponse,
} from './release-track-model';
import {
  ReleaseKeyModel,
  releaseKeyModel,
  releaseKeyModelRequest,
  releaseKeyModelResponse,
} from './release-key-model';
import {
  TrackOrReleaseArtistModel,
  trackOrReleaseArtistModel,
  trackOrReleaseArtistModelRequest,
  trackOrReleaseArtistModelResponse,
} from './track-or-release-artist-model';
import {
  ReleaseAggregatorModel,
  releaseAggregatorModel,
  releaseAggregatorModelRequest,
  releaseAggregatorModelResponse,
} from './release-aggregator-model';
import { PriceModel, priceModel, priceModelRequest, priceModelResponse } from './price-model';

/**
 * Zod schema for the ReleasesDefaultModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const releasesDefaultModel = z.lazy(() => {
  return z.object({
    score: z.number(),
    currentStatus: z.array(currentStatusModel).optional().nullable(),
    genre: releasesDefaultModelGenre.optional().nullable(),
    label: trackOrReleaseLabelModel,
    tracks: z.array(releaseTrackModel).optional().nullable(),
    key: z.array(releaseKeyModel).optional().nullable(),
    artists: z.array(trackOrReleaseArtistModel).optional().nullable(),
    aggregator: releaseAggregatorModel,
    availableWorldwide: z.number(),
    catalogNumber: z.string().optional().nullable(),
    createDate: z.string().optional().nullable(),
    encodedDate: z.string().optional().nullable(),
    exclusive: z.number(),
    exclusiveDate: z.string().optional().nullable(),
    streamingDate: z.string().optional().nullable(),
    preorderDate: z.string().optional().nullable(),
    labelManager: z.string().optional().nullable(),
    preOrderDate_1: z.string().optional().nullable(),
    publishDate: z.string(),
    releaseDate: z.string(),
    releaseId: z.number(),
    releaseName: z.string(),
    releaseType: z.string(),
    status: z.number(),
    upc: z.string().optional().nullable(),
    updateDate: z.string(),
    price: priceModel.optional(),
    isExplicit: z.boolean().optional().nullable(),
    trackCount: z.number().optional().nullable(),
    releaseImageUri: z.string().optional().nullable(),
    releaseImageDynamicUri: z.string().optional().nullable(),
    downloads: z.number().optional().nullable(),
    isHype: z.boolean().optional().nullable(),
    isPreOrder: z.boolean().optional().nullable(),
    plays: z.number().optional().nullable(),
  });
});

/**
 *
 * @typedef  {ReleasesDefaultModel} releasesDefaultModel
 * @property {number}
 * @property {CurrentStatusModel[]}
 * @property {ReleasesDefaultModelGenre}
 * @property {TrackOrReleaseLabelModel}
 * @property {ReleaseTrackModel[]}
 * @property {ReleaseKeyModel[]}
 * @property {TrackOrReleaseArtistModel[]}
 * @property {ReleaseAggregatorModel}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {PriceModel}
 * @property {boolean}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {boolean}
 * @property {boolean}
 * @property {number}
 */
export type ReleasesDefaultModel = z.infer<typeof releasesDefaultModel>;

/**
 * Zod schema for mapping API responses to the ReleasesDefaultModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releasesDefaultModelResponse = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      current_status: z.array(currentStatusModelResponse).optional().nullable(),
      genre: releasesDefaultModelGenreResponse.optional().nullable(),
      label: trackOrReleaseLabelModelResponse,
      tracks: z.array(releaseTrackModelResponse).optional().nullable(),
      key: z.array(releaseKeyModelResponse).optional().nullable(),
      artists: z.array(trackOrReleaseArtistModelResponse).optional().nullable(),
      aggregator: releaseAggregatorModelResponse,
      available_worldwide: z.number(),
      catalog_number: z.string().optional().nullable(),
      create_date: z.string().optional().nullable(),
      encoded_date: z.string().optional().nullable(),
      exclusive: z.number(),
      exclusive_date: z.string().optional().nullable(),
      streaming_date: z.string().optional().nullable(),
      preorder_date: z.string().optional().nullable(),
      label_manager: z.string().optional().nullable(),
      pre_order_date: z.string().optional().nullable(),
      publish_date: z.string(),
      release_date: z.string(),
      release_id: z.number(),
      release_name: z.string(),
      release_type: z.string(),
      status: z.number(),
      upc: z.string().optional().nullable(),
      update_date: z.string(),
      price: priceModelResponse.optional(),
      is_explicit: z.boolean().optional().nullable(),
      track_count: z.number().optional().nullable(),
      release_image_uri: z.string().optional().nullable(),
      release_image_dynamic_uri: z.string().optional().nullable(),
      downloads: z.number().optional().nullable(),
      is_hype: z.boolean().optional().nullable(),
      is_pre_order: z.boolean().optional().nullable(),
      plays: z.number().optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      currentStatus: data['current_status'],
      genre: data['genre'],
      label: data['label'],
      tracks: data['tracks'],
      key: data['key'],
      artists: data['artists'],
      aggregator: data['aggregator'],
      availableWorldwide: data['available_worldwide'],
      catalogNumber: data['catalog_number'],
      createDate: data['create_date'],
      encodedDate: data['encoded_date'],
      exclusive: data['exclusive'],
      exclusiveDate: data['exclusive_date'],
      streamingDate: data['streaming_date'],
      preorderDate: data['preorder_date'],
      labelManager: data['label_manager'],
      preOrderDate_1: data['pre_order_date'],
      publishDate: data['publish_date'],
      releaseDate: data['release_date'],
      releaseId: data['release_id'],
      releaseName: data['release_name'],
      releaseType: data['release_type'],
      status: data['status'],
      upc: data['upc'],
      updateDate: data['update_date'],
      price: data['price'],
      isExplicit: data['is_explicit'],
      trackCount: data['track_count'],
      releaseImageUri: data['release_image_uri'],
      releaseImageDynamicUri: data['release_image_dynamic_uri'],
      downloads: data['downloads'],
      isHype: data['is_hype'],
      isPreOrder: data['is_pre_order'],
      plays: data['plays'],
    }));
});

/**
 * Zod schema for mapping the ReleasesDefaultModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releasesDefaultModelRequest = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      currentStatus: z.array(currentStatusModelRequest).optional().nullable(),
      genre: releasesDefaultModelGenreRequest.optional().nullable(),
      label: trackOrReleaseLabelModelRequest,
      tracks: z.array(releaseTrackModelRequest).optional().nullable(),
      key: z.array(releaseKeyModelRequest).optional().nullable(),
      artists: z.array(trackOrReleaseArtistModelRequest).optional().nullable(),
      aggregator: releaseAggregatorModelRequest,
      availableWorldwide: z.number(),
      catalogNumber: z.string().optional().nullable(),
      createDate: z.string().optional().nullable(),
      encodedDate: z.string().optional().nullable(),
      exclusive: z.number(),
      exclusiveDate: z.string().optional().nullable(),
      streamingDate: z.string().optional().nullable(),
      preorderDate: z.string().optional().nullable(),
      labelManager: z.string().optional().nullable(),
      preOrderDate_1: z.string().optional().nullable(),
      publishDate: z.string(),
      releaseDate: z.string(),
      releaseId: z.number(),
      releaseName: z.string(),
      releaseType: z.string(),
      status: z.number(),
      upc: z.string().optional().nullable(),
      updateDate: z.string(),
      price: priceModelRequest.optional(),
      isExplicit: z.boolean().optional().nullable(),
      trackCount: z.number().optional().nullable(),
      releaseImageUri: z.string().optional().nullable(),
      releaseImageDynamicUri: z.string().optional().nullable(),
      downloads: z.number().optional().nullable(),
      isHype: z.boolean().optional().nullable(),
      isPreOrder: z.boolean().optional().nullable(),
      plays: z.number().optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      current_status: data['currentStatus'],
      genre: data['genre'],
      label: data['label'],
      tracks: data['tracks'],
      key: data['key'],
      artists: data['artists'],
      aggregator: data['aggregator'],
      available_worldwide: data['availableWorldwide'],
      catalog_number: data['catalogNumber'],
      create_date: data['createDate'],
      encoded_date: data['encodedDate'],
      exclusive: data['exclusive'],
      exclusive_date: data['exclusiveDate'],
      streaming_date: data['streamingDate'],
      preorder_date: data['preorderDate'],
      label_manager: data['labelManager'],
      pre_order_date: data['preOrderDate_1'],
      publish_date: data['publishDate'],
      release_date: data['releaseDate'],
      release_id: data['releaseId'],
      release_name: data['releaseName'],
      release_type: data['releaseType'],
      status: data['status'],
      upc: data['upc'],
      update_date: data['updateDate'],
      price: data['price'],
      is_explicit: data['isExplicit'],
      track_count: data['trackCount'],
      release_image_uri: data['releaseImageUri'],
      release_image_dynamic_uri: data['releaseImageDynamicUri'],
      downloads: data['downloads'],
      is_hype: data['isHype'],
      is_pre_order: data['isPreOrder'],
      plays: data['plays'],
    }));
});
