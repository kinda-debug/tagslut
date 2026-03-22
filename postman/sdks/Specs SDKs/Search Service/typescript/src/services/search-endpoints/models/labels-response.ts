import { z } from 'zod';
import {
  LabelsDefaultModel,
  labelsDefaultModel,
  labelsDefaultModelRequest,
  labelsDefaultModelResponse,
} from './labels-default-model';

/**
 * Zod schema for the LabelsResponse model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const labelsResponse = z.lazy(() => {
  return z.object({
    debug: z.any().optional().nullable(),
    explain: z.any().optional().nullable(),
    data: z.array(labelsDefaultModel),
  });
});

/**
 *
 * @typedef  {LabelsResponse} labelsResponse
 * @property {any}
 * @property {any}
 * @property {LabelsDefaultModel[]} - List of label models.
 */
export type LabelsResponse = z.infer<typeof labelsResponse>;

/**
 * Zod schema for mapping API responses to the LabelsResponse application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const labelsResponseResponse = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(labelsDefaultModelResponse),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});

/**
 * Zod schema for mapping the LabelsResponse application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const labelsResponseRequest = z.lazy(() => {
  return z
    .object({
      debug: z.any().optional().nullable(),
      explain: z.any().optional().nullable(),
      data: z.array(labelsDefaultModelRequest),
    })
    .transform((data) => ({
      debug: data['debug'],
      explain: data['explain'],
      data: data['data'],
    }));
});
