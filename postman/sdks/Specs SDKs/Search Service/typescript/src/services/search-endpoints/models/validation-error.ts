import { z } from 'zod';
import { __, _request, _response } from './__';

/**
 * Zod schema for the ValidationError model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const validationError = z.lazy(() => {
  return z.object({
    loc: z.array(__),
    msg: z.string(),
    type: z.string(),
  });
});

/**
 *
 * @typedef  {ValidationError} validationError
 * @property {__[]}
 * @property {string}
 * @property {string}
 */
export type ValidationError = z.infer<typeof validationError>;

/**
 * Zod schema for mapping API responses to the ValidationError application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const validationErrorResponse = z.lazy(() => {
  return z
    .object({
      loc: z.array(_response),
      msg: z.string(),
      type: z.string(),
    })
    .transform((data) => ({
      loc: data['loc'],
      msg: data['msg'],
      type: data['type'],
    }));
});

/**
 * Zod schema for mapping the ValidationError application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const validationErrorRequest = z.lazy(() => {
  return z
    .object({
      loc: z.array(_request),
      msg: z.string(),
      type: z.string(),
    })
    .transform((data) => ({
      loc: data['loc'],
      msg: data['msg'],
      type: data['type'],
    }));
});
