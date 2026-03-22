import { z } from 'zod';
import { GenreModel, genreModel, genreModelRequest, genreModelResponse } from './genre-model';

/**
 * Zod schema for the ChartsDefaultModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const chartsDefaultModel = z.lazy(() => {
  return z.object({
    score: z.number(),
    chartId: z.number(),
    chartName: z.string(),
    artistId: z.number().optional().nullable(),
    artistName: z.string().optional().nullable(),
    createDate: z.string(),
    isApproved: z.number(),
    updateDate: z.string(),
    enabled: z.number(),
    isIndexed: z.number(),
    personId: z.number().optional().nullable(),
    publishDate: z.string().optional().nullable(),
    itemTypeId: z.number().optional().nullable(),
    personUsername: z.string().optional().nullable(),
    isPublished: z.number(),
    trackCount: z.number().optional().nullable(),
    chartImageUri: z.string().optional().nullable(),
    chartImageDynamicUri: z.string().optional().nullable(),
    genres: z.array(genreModel).optional().nullable(),
  });
});

/**
 *
 * @typedef  {ChartsDefaultModel} chartsDefaultModel
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {number}
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {number}
 * @property {string}
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {GenreModel[]}
 */
export type ChartsDefaultModel = z.infer<typeof chartsDefaultModel>;

/**
 * Zod schema for mapping API responses to the ChartsDefaultModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const chartsDefaultModelResponse = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      chart_id: z.number(),
      chart_name: z.string(),
      artist_id: z.number().optional().nullable(),
      artist_name: z.string().optional().nullable(),
      create_date: z.string(),
      is_approved: z.number(),
      update_date: z.string(),
      enabled: z.number(),
      is_indexed: z.number(),
      person_id: z.number().optional().nullable(),
      publish_date: z.string().optional().nullable(),
      item_type_id: z.number().optional().nullable(),
      person_username: z.string().optional().nullable(),
      is_published: z.number(),
      track_count: z.number().optional().nullable(),
      chart_image_uri: z.string().optional().nullable(),
      chart_image_dynamic_uri: z.string().optional().nullable(),
      genres: z.array(genreModelResponse).optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      chartId: data['chart_id'],
      chartName: data['chart_name'],
      artistId: data['artist_id'],
      artistName: data['artist_name'],
      createDate: data['create_date'],
      isApproved: data['is_approved'],
      updateDate: data['update_date'],
      enabled: data['enabled'],
      isIndexed: data['is_indexed'],
      personId: data['person_id'],
      publishDate: data['publish_date'],
      itemTypeId: data['item_type_id'],
      personUsername: data['person_username'],
      isPublished: data['is_published'],
      trackCount: data['track_count'],
      chartImageUri: data['chart_image_uri'],
      chartImageDynamicUri: data['chart_image_dynamic_uri'],
      genres: data['genres'],
    }));
});

/**
 * Zod schema for mapping the ChartsDefaultModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const chartsDefaultModelRequest = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      chartId: z.number(),
      chartName: z.string(),
      artistId: z.number().optional().nullable(),
      artistName: z.string().optional().nullable(),
      createDate: z.string(),
      isApproved: z.number(),
      updateDate: z.string(),
      enabled: z.number(),
      isIndexed: z.number(),
      personId: z.number().optional().nullable(),
      publishDate: z.string().optional().nullable(),
      itemTypeId: z.number().optional().nullable(),
      personUsername: z.string().optional().nullable(),
      isPublished: z.number(),
      trackCount: z.number().optional().nullable(),
      chartImageUri: z.string().optional().nullable(),
      chartImageDynamicUri: z.string().optional().nullable(),
      genres: z.array(genreModelRequest).optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      chart_id: data['chartId'],
      chart_name: data['chartName'],
      artist_id: data['artistId'],
      artist_name: data['artistName'],
      create_date: data['createDate'],
      is_approved: data['isApproved'],
      update_date: data['updateDate'],
      enabled: data['enabled'],
      is_indexed: data['isIndexed'],
      person_id: data['personId'],
      publish_date: data['publishDate'],
      item_type_id: data['itemTypeId'],
      person_username: data['personUsername'],
      is_published: data['isPublished'],
      track_count: data['trackCount'],
      chart_image_uri: data['chartImageUri'],
      chart_image_dynamic_uri: data['chartImageDynamicUri'],
      genres: data['genres'],
    }));
});
