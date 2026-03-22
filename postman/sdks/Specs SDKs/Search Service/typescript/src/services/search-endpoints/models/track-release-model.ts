import { z } from 'zod';

/**
 * Zod schema for the TrackReleaseModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const trackReleaseModel = z.lazy(() => {
  return z.object({
    releaseId: z.number(),
    releaseName: z.string(),
    releaseImageUri: z.string().optional().nullable(),
    releaseImageDynamicUri: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {TrackReleaseModel} trackReleaseModel
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {string}
 */
export type TrackReleaseModel = z.infer<typeof trackReleaseModel>;

/**
 * Zod schema for mapping API responses to the TrackReleaseModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const trackReleaseModelResponse = z.lazy(() => {
  return z
    .object({
      release_id: z.number(),
      release_name: z.string(),
      release_image_uri: z.string().optional().nullable(),
      release_image_dynamic_uri: z.string().optional().nullable(),
    })
    .transform((data) => ({
      releaseId: data['release_id'],
      releaseName: data['release_name'],
      releaseImageUri: data['release_image_uri'],
      releaseImageDynamicUri: data['release_image_dynamic_uri'],
    }));
});

/**
 * Zod schema for mapping the TrackReleaseModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const trackReleaseModelRequest = z.lazy(() => {
  return z
    .object({
      releaseId: z.number(),
      releaseName: z.string(),
      releaseImageUri: z.string().optional().nullable(),
      releaseImageDynamicUri: z.string().optional().nullable(),
    })
    .transform((data) => ({
      release_id: data['releaseId'],
      release_name: data['releaseName'],
      release_image_uri: data['releaseImageUri'],
      release_image_dynamic_uri: data['releaseImageDynamicUri'],
    }));
});
