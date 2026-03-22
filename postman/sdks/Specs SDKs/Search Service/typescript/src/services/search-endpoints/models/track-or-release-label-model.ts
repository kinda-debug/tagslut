import { z } from 'zod';

/**
 * Zod schema for the TrackOrReleaseLabelModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const trackOrReleaseLabelModel = z.lazy(() => {
  return z.object({
    enabled: z.number(),
    labelId: z.number(),
    labelName: z.string(),
  });
});

/**
 *
 * @typedef  {TrackOrReleaseLabelModel} trackOrReleaseLabelModel
 * @property {number}
 * @property {number}
 * @property {string}
 */
export type TrackOrReleaseLabelModel = z.infer<typeof trackOrReleaseLabelModel>;

/**
 * Zod schema for mapping API responses to the TrackOrReleaseLabelModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const trackOrReleaseLabelModelResponse = z.lazy(() => {
  return z
    .object({
      enabled: z.number(),
      label_id: z.number(),
      label_name: z.string(),
    })
    .transform((data) => ({
      enabled: data['enabled'],
      labelId: data['label_id'],
      labelName: data['label_name'],
    }));
});

/**
 * Zod schema for mapping the TrackOrReleaseLabelModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const trackOrReleaseLabelModelRequest = z.lazy(() => {
  return z
    .object({
      enabled: z.number(),
      labelId: z.number(),
      labelName: z.string(),
    })
    .transform((data) => ({
      enabled: data['enabled'],
      label_id: data['labelId'],
      label_name: data['labelName'],
    }));
});
