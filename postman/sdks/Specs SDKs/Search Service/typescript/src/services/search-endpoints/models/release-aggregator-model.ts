import { z } from 'zod';

/**
 * Zod schema for the ReleaseAggregatorModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const releaseAggregatorModel = z.lazy(() => {
  return z.object({
    aggregatorId: z.number(),
    aggregatorName: z.string(),
  });
});

/**
 *
 * @typedef  {ReleaseAggregatorModel} releaseAggregatorModel
 * @property {number}
 * @property {string}
 */
export type ReleaseAggregatorModel = z.infer<typeof releaseAggregatorModel>;

/**
 * Zod schema for mapping API responses to the ReleaseAggregatorModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releaseAggregatorModelResponse = z.lazy(() => {
  return z
    .object({
      aggregator_id: z.number(),
      aggregator_name: z.string(),
    })
    .transform((data) => ({
      aggregatorId: data['aggregator_id'],
      aggregatorName: data['aggregator_name'],
    }));
});

/**
 * Zod schema for mapping the ReleaseAggregatorModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releaseAggregatorModelRequest = z.lazy(() => {
  return z
    .object({
      aggregatorId: z.number(),
      aggregatorName: z.string(),
    })
    .transform((data) => ({
      aggregator_id: data['aggregatorId'],
      aggregator_name: data['aggregatorName'],
    }));
});
