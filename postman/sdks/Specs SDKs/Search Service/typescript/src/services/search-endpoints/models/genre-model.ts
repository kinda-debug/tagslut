import { z } from 'zod';

/**
 * Zod schema for the GenreModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const genreModel = z.lazy(() => {
  return z.object({
    genreId: z.number().optional().nullable(),
    genreName: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {GenreModel} genreModel
 * @property {number}
 * @property {string}
 */
export type GenreModel = z.infer<typeof genreModel>;

/**
 * Zod schema for mapping API responses to the GenreModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const genreModelResponse = z.lazy(() => {
  return z
    .object({
      genre_id: z.number().optional().nullable(),
      genre_name: z.string().optional().nullable(),
    })
    .transform((data) => ({
      genreId: data['genre_id'],
      genreName: data['genre_name'],
    }));
});

/**
 * Zod schema for mapping the GenreModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const genreModelRequest = z.lazy(() => {
  return z
    .object({
      genreId: z.number().optional().nullable(),
      genreName: z.string().optional().nullable(),
    })
    .transform((data) => ({
      genre_id: data['genreId'],
      genre_name: data['genreName'],
    }));
});
