import { z } from 'zod';
import { GenreModel, genreModel, genreModelRequest, genreModelResponse } from './genre-model';

/**
 * Zod schema for the ArtistsDefaultModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const artistsDefaultModel = z.lazy(() => {
  return z.object({
    score: z.number(),
    enabled: z.number(),
    updateDate: z.string().optional().nullable(),
    latestPublishDate: z.string().optional().nullable(),
    availableWorldwide: z.number(),
    downloads: z.number().optional().nullable(),
    artistId: z.number(),
    artistName: z.string(),
    genre: z.array(genreModel).optional().nullable(),
    artistImageUri: z.string().optional().nullable(),
    artistImageDynamicUri: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {ArtistsDefaultModel} artistsDefaultModel
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {GenreModel[]}
 * @property {string}
 * @property {string}
 */
export type ArtistsDefaultModel = z.infer<typeof artistsDefaultModel>;

/**
 * Zod schema for mapping API responses to the ArtistsDefaultModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const artistsDefaultModelResponse = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      enabled: z.number(),
      update_date: z.string().optional().nullable(),
      latest_publish_date: z.string().optional().nullable(),
      available_worldwide: z.number(),
      downloads: z.number().optional().nullable(),
      artist_id: z.number(),
      artist_name: z.string(),
      genre: z.array(genreModelResponse).optional().nullable(),
      artist_image_uri: z.string().optional().nullable(),
      artist_image_dynamic_uri: z.string().optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      enabled: data['enabled'],
      updateDate: data['update_date'],
      latestPublishDate: data['latest_publish_date'],
      availableWorldwide: data['available_worldwide'],
      downloads: data['downloads'],
      artistId: data['artist_id'],
      artistName: data['artist_name'],
      genre: data['genre'],
      artistImageUri: data['artist_image_uri'],
      artistImageDynamicUri: data['artist_image_dynamic_uri'],
    }));
});

/**
 * Zod schema for mapping the ArtistsDefaultModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const artistsDefaultModelRequest = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      enabled: z.number(),
      updateDate: z.string().optional().nullable(),
      latestPublishDate: z.string().optional().nullable(),
      availableWorldwide: z.number(),
      downloads: z.number().optional().nullable(),
      artistId: z.number(),
      artistName: z.string(),
      genre: z.array(genreModelRequest).optional().nullable(),
      artistImageUri: z.string().optional().nullable(),
      artistImageDynamicUri: z.string().optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      enabled: data['enabled'],
      update_date: data['updateDate'],
      latest_publish_date: data['latestPublishDate'],
      available_worldwide: data['availableWorldwide'],
      downloads: data['downloads'],
      artist_id: data['artistId'],
      artist_name: data['artistName'],
      genre: data['genre'],
      artist_image_uri: data['artistImageUri'],
      artist_image_dynamic_uri: data['artistImageDynamicUri'],
    }));
});
