import { z } from 'zod';
import {
  ArtistsDefaultModel,
  artistsDefaultModel,
  artistsDefaultModelRequest,
  artistsDefaultModelResponse,
} from './artists-default-model';

/**
 * Zod schema for the ArtistsResponse model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const artistsResponse = z.lazy(() => {
  return z.object({
    debug: z.any().optional().nullable(),
    explain: z.any().optional().nullable(),
    data: z.array(artistsDefaultModel),
  });
});

/**
 *
 * @typedef  {ArtistsResponse} artistsResponse
 * @property {any}
 * @property {any}
 * @property {ArtistsDefaultModel[]} - List of artist models.
 */
export type ArtistsResponse = z.infer<typeof artistsResponse>;

/**
 * Zod schema for mapping API responses to the ArtistsResponse application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const artistsResponseResponse = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(artistsDefaultModelResponse),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});

/**
 * Zod schema for mapping the ArtistsResponse application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const artistsResponseRequest = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(artistsDefaultModelRequest),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});
