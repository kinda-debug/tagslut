import { z } from 'zod';
import {
  TracksResponse,
  tracksResponse,
  tracksResponseRequest,
  tracksResponseResponse,
} from './tracks-response';
import {
  ArtistsResponse,
  artistsResponse,
  artistsResponseRequest,
  artistsResponseResponse,
} from './artists-response';
import {
  ChartsResponse,
  chartsResponse,
  chartsResponseRequest,
  chartsResponseResponse,
} from './charts-response';
import {
  LabelsResponse,
  labelsResponse,
  labelsResponseRequest,
  labelsResponseResponse,
} from './labels-response';
import {
  ReleasesResponse,
  releasesResponse,
  releasesResponseRequest,
  releasesResponseResponse,
} from './releases-response';

/**
 * Zod schema for the MultisearchResponse model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const multisearchResponse = z.lazy(() => {
  return z.object({
    tracks: tracksResponse,
    artists: artistsResponse,
    charts: chartsResponse,
    labels: labelsResponse,
    releases: releasesResponse,
  });
});

/**
 * Response model for the `all-search` endpoint.
 * @typedef  {MultisearchResponse} multisearchResponse - Response model for the `all-search` endpoint. - Response model for the `all-search` endpoint.
 * @property {TracksResponse} - Response model for the `tracks` endpoint.
 * @property {ArtistsResponse}
 * @property {ChartsResponse}
 * @property {LabelsResponse}
 * @property {ReleasesResponse} - Response model for the `releases` endpoint.
 */
export type MultisearchResponse = z.infer<typeof multisearchResponse>;

/**
 * Zod schema for mapping API responses to the MultisearchResponse application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const multisearchResponseResponse = z.lazy(() => {
  return z
    .object({
      tracks: tracksResponseResponse,
      artists: artistsResponseResponse,
      charts: chartsResponseResponse,
      labels: labelsResponseResponse,
      releases: releasesResponseResponse,
    })
    .transform((data) => ({
      tracks: data['tracks'],
      artists: data['artists'],
      charts: data['charts'],
      labels: data['labels'],
      releases: data['releases'],
    }));
});

/**
 * Zod schema for mapping the MultisearchResponse application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const multisearchResponseRequest = z.lazy(() => {
  return z
    .object({
      tracks: tracksResponseRequest,
      artists: artistsResponseRequest,
      charts: chartsResponseRequest,
      labels: labelsResponseRequest,
      releases: releasesResponseRequest,
    })
    .transform((data) => ({
      tracks: data['tracks'],
      artists: data['artists'],
      charts: data['charts'],
      labels: data['labels'],
      releases: data['releases'],
    }));
});
