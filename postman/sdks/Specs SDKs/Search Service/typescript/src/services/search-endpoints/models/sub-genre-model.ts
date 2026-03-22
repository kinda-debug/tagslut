import { z } from 'zod';

/**
 * Zod schema for the SubGenreModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const subGenreModel = z.lazy(() => {
  return z.object({
    subGenreId: z.number().optional().nullable(),
    subGenreName: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {SubGenreModel} subGenreModel
 * @property {number}
 * @property {string}
 */
export type SubGenreModel = z.infer<typeof subGenreModel>;

/**
 * Zod schema for mapping API responses to the SubGenreModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const subGenreModelResponse = z.lazy(() => {
  return z
    .object({
      sub_genre_id: z.number().optional().nullable(),
      sub_genre_name: z.string().optional().nullable(),
    })
    .transform((data) => ({
      subGenreId: data['sub_genre_id'],
      subGenreName: data['sub_genre_name'],
    }));
});

/**
 * Zod schema for mapping the SubGenreModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const subGenreModelRequest = z.lazy(() => {
  return z
    .object({
      subGenreId: z.number().optional().nullable(),
      subGenreName: z.string().optional().nullable(),
    })
    .transform((data) => ({
      sub_genre_id: data['subGenreId'],
      sub_genre_name: data['subGenreName'],
    }));
});
