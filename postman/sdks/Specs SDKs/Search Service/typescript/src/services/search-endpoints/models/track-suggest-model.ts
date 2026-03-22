import { z } from 'zod';

/**
 * Zod schema for the TrackSuggestModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const trackSuggestModel = z.lazy(() => {
  return z.object({
    input: z.string(),
    weight: z.number().optional().nullable(),
  });
});

/**
 *
 * @typedef  {TrackSuggestModel} trackSuggestModel
 * @property {string}
 * @property {number}
 */
export type TrackSuggestModel = z.infer<typeof trackSuggestModel>;

/**
 * Zod schema for mapping API responses to the TrackSuggestModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const trackSuggestModelResponse = z.lazy(() => {
  return z
    .object({
      input: z.string(),
      weight: z.number().optional().nullable(),
    })
    .transform((data) => ({
      input: data['input'],
      weight: data['weight'],
    }));
});

/**
 * Zod schema for mapping the TrackSuggestModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const trackSuggestModelRequest = z.lazy(() => {
  return z
    .object({
      input: z.string(),
      weight: z.number().optional().nullable(),
    })
    .transform((data) => ({
      input: data['input'],
      weight: data['weight'],
    }));
});
