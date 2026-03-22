import { z } from 'zod';
import { genreModel, genreModelRequest, genreModelResponse } from './genre-model';

/**
 * Zod schema for the ReleasesDefaultModelGenre model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const releasesDefaultModelGenre = z.lazy(() => {
  return z.union([z.array(genreModel), genreModel]);
});

/**
 *
 * @typedef  {ReleasesDefaultModelGenre} releasesDefaultModelGenre
 * @property {GenreModel[]}
 * @property {GenreModel}
 */
export type ReleasesDefaultModelGenre = z.infer<typeof releasesDefaultModelGenre>;

/**
 * The shape of the model mapping from the api schema into the application shape.
 * Is equal to application shape if all property names match the api schema
 */
export const releasesDefaultModelGenreResponse = z.lazy(() => {
  return z.union([z.array(genreModel), genreModelResponse]);
});

/**
 * The shape of the model mapping from the application shape into the api schema.
 * Is equal to application shape if all property names match the api schema
 */
export const releasesDefaultModelGenreRequest = z.lazy(() => {
  return z.union([z.array(genreModel), genreModelRequest]);
});
