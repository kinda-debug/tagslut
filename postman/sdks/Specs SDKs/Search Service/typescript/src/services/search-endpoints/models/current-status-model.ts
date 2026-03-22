import { z } from 'zod';

/**
 * Zod schema for the CurrentStatusModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const currentStatusModel = z.lazy(() => {
  return z.object({
    currentStatusId: z.number().optional().nullable(),
    currentStatusName: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {CurrentStatusModel} currentStatusModel
 * @property {number}
 * @property {string}
 */
export type CurrentStatusModel = z.infer<typeof currentStatusModel>;

/**
 * Zod schema for mapping API responses to the CurrentStatusModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const currentStatusModelResponse = z.lazy(() => {
  return z
    .object({
      current_status_id: z.number().optional().nullable(),
      current_status_name: z.string().optional().nullable(),
    })
    .transform((data) => ({
      currentStatusId: data['current_status_id'],
      currentStatusName: data['current_status_name'],
    }));
});

/**
 * Zod schema for mapping the CurrentStatusModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const currentStatusModelRequest = z.lazy(() => {
  return z
    .object({
      currentStatusId: z.number().optional().nullable(),
      currentStatusName: z.string().optional().nullable(),
    })
    .transform((data) => ({
      current_status_id: data['currentStatusId'],
      current_status_name: data['currentStatusName'],
    }));
});
