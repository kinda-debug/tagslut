import { z } from 'zod';
import {
  ChartsDefaultModel,
  chartsDefaultModel,
  chartsDefaultModelRequest,
  chartsDefaultModelResponse,
} from './charts-default-model';

/**
 * Zod schema for the ChartsResponse model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const chartsResponse = z.lazy(() => {
  return z.object({
    debug: z.any().optional().nullable(),
    explain: z.any().optional().nullable(),
    data: z.array(chartsDefaultModel),
  });
});

/**
 *
 * @typedef  {ChartsResponse} chartsResponse
 * @property {any}
 * @property {any}
 * @property {ChartsDefaultModel[]} - List of chart models.
 */
export type ChartsResponse = z.infer<typeof chartsResponse>;

/**
 * Zod schema for mapping API responses to the ChartsResponse application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const chartsResponseResponse = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(chartsDefaultModelResponse),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});

/**
 * Zod schema for mapping the ChartsResponse application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const chartsResponseRequest = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(chartsDefaultModelRequest),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});
