import { z } from 'zod';

/**
 * Zod schema for the TrackOrReleaseArtistModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const trackOrReleaseArtistModel = z.lazy(() => {
  return z.object({
    artistId: z.number().optional().nullable(),
    artistName: z.string().optional().nullable(),
    artistTypeName: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {TrackOrReleaseArtistModel} trackOrReleaseArtistModel
 * @property {number}
 * @property {string}
 * @property {string}
 */
export type TrackOrReleaseArtistModel = z.infer<typeof trackOrReleaseArtistModel>;

/**
 * Zod schema for mapping API responses to the TrackOrReleaseArtistModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const trackOrReleaseArtistModelResponse = z.lazy(() => {
  return z
    .object({
      artist_id: z.number().optional().nullable(),
      artist_name: z.string().optional().nullable(),
      artist_type_name: z.string().optional().nullable(),
    })
    .transform((data) => ({
      artistId: data['artist_id'],
      artistName: data['artist_name'],
      artistTypeName: data['artist_type_name'],
    }));
});

/**
 * Zod schema for mapping the TrackOrReleaseArtistModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const trackOrReleaseArtistModelRequest = z.lazy(() => {
  return z
    .object({
      artistId: z.number().optional().nullable(),
      artistName: z.string().optional().nullable(),
      artistTypeName: z.string().optional().nullable(),
    })
    .transform((data) => ({
      artist_id: data['artistId'],
      artist_name: data['artistName'],
      artist_type_name: data['artistTypeName'],
    }));
});
