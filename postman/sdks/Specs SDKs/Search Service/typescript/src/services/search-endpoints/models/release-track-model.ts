import { z } from 'zod';

/**
 * Zod schema for the ReleaseTrackModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const releaseTrackModel = z.lazy(() => {
  return z.object({
    trackId: z.number().optional().nullable(),
    trackName: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {ReleaseTrackModel} releaseTrackModel
 * @property {number}
 * @property {string}
 */
export type ReleaseTrackModel = z.infer<typeof releaseTrackModel>;

/**
 * Zod schema for mapping API responses to the ReleaseTrackModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releaseTrackModelResponse = z.lazy(() => {
  return z
    .object({
      track_id: z.number().optional().nullable(),
      track_name: z.string().optional().nullable(),
    })
    .transform((data) => ({
      trackId: data['track_id'],
      trackName: data['track_name'],
    }));
});

/**
 * Zod schema for mapping the ReleaseTrackModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releaseTrackModelRequest = z.lazy(() => {
  return z
    .object({
      trackId: z.number().optional().nullable(),
      trackName: z.string().optional().nullable(),
    })
    .transform((data) => ({
      track_id: data['trackId'],
      track_name: data['trackName'],
    }));
});
