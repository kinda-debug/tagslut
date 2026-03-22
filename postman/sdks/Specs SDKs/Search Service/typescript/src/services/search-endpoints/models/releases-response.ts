import { z } from 'zod';
import {
  ReleasesDefaultModel,
  releasesDefaultModel,
  releasesDefaultModelRequest,
  releasesDefaultModelResponse,
} from './releases-default-model';

/**
 * Zod schema for the ReleasesResponse model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const releasesResponse = z.lazy(() => {
  return z.object({
    debug: z.any().optional().nullable(),
    explain: z.any().optional().nullable(),
    data: z.array(releasesDefaultModel),
  });
});

/**
 * Response model for the `releases` endpoint.
 * @typedef  {ReleasesResponse} releasesResponse - Response model for the `releases` endpoint. - Response model for the `releases` endpoint.
 * @property {any}
 * @property {any}
 * @property {ReleasesDefaultModel[]} - List of release models.
 */
export type ReleasesResponse = z.infer<typeof releasesResponse>;

/**
 * Zod schema for mapping API responses to the ReleasesResponse application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releasesResponseResponse = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(releasesDefaultModelResponse),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});

/**
 * Zod schema for mapping the ReleasesResponse application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releasesResponseRequest = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(releasesDefaultModelRequest),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});
