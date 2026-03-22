import { z } from 'zod';
import {
  TracksDefaultModel,
  tracksDefaultModel,
  tracksDefaultModelRequest,
  tracksDefaultModelResponse,
} from './tracks-default-model';

/**
 * Zod schema for the TracksResponse model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const tracksResponse = z.lazy(() => {
  return z.object({
    debug: z.any().optional().nullable(),
    explain: z.any().optional().nullable(),
    data: z.array(tracksDefaultModel),
  });
});

/**
 * Response model for the `tracks` endpoint.
 * @typedef  {TracksResponse} tracksResponse - Response model for the `tracks` endpoint. - Response model for the `tracks` endpoint.
 * @property {any}
 * @property {any}
 * @property {TracksDefaultModel[]} - List of track models.
 */
export type TracksResponse = z.infer<typeof tracksResponse>;

/**
 * Zod schema for mapping API responses to the TracksResponse application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const tracksResponseResponse = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(tracksDefaultModelResponse),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});

/**
 * Zod schema for mapping the TracksResponse application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const tracksResponseRequest = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(tracksDefaultModelRequest),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});
