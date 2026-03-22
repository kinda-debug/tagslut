import { z } from 'zod';
import { genreModel, genreModelRequest, genreModelResponse } from './genre-model';

/**
 * Zod schema for the TracksDefaultModelGenre model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const tracksDefaultModelGenre = z.lazy(() => {
  return z.union([z.array(genreModel), genreModel]);
});

/**
 *
 * @typedef  {TracksDefaultModelGenre} tracksDefaultModelGenre
 * @property {GenreModel[]}
 * @property {GenreModel}
 */
export type TracksDefaultModelGenre = z.infer<typeof tracksDefaultModelGenre>;

/**
 * The shape of the model mapping from the api schema into the application shape.
 * Is equal to application shape if all property names match the api schema
 */
export const tracksDefaultModelGenreResponse = z.lazy(() => {
  return z.union([z.array(genreModel), genreModelResponse]);
});

/**
 * The shape of the model mapping from the application shape into the api schema.
 * Is equal to application shape if all property names match the api schema
 */
export const tracksDefaultModelGenreRequest = z.lazy(() => {
  return z.union([z.array(genreModel), genreModelRequest]);
});
