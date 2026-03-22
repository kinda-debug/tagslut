import { z } from 'zod';

/**
 * Zod schema for the __ model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const __ = z.lazy(() => {
  return z.union([z.string(), z.number()]);
});

/**
 *
 * @typedef  {__} __
 * @property {string}
 * @property {number}
 */
export type __ = z.infer<typeof __>;

/**
 * The shape of the model mapping from the api schema into the application shape.
 * Is equal to application shape if all property names match the api schema
 */
export const _response = z.lazy(() => {
  return z.union([z.string(), z.number()]);
});

/**
 * The shape of the model mapping from the application shape into the api schema.
 * Is equal to application shape if all property names match the api schema
 */
export const _request = z.lazy(() => {
  return z.union([z.string(), z.number()]);
});
