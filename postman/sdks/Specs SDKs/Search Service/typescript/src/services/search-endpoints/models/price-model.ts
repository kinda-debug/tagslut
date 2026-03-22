import { z } from 'zod';

/**
 * Zod schema for the PriceModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const priceModel = z.lazy(() => {
  return z.object({
    code: z.string(),
    symbol: z.string(),
    value: z.number(),
    display: z.string(),
  });
});

/**
 *
 * @typedef  {PriceModel} priceModel
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {string}
 */
export type PriceModel = z.infer<typeof priceModel>;

/**
 * Zod schema for mapping API responses to the PriceModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const priceModelResponse = z.lazy(() => {
  return z
    .object({
      code: z.string(),
      symbol: z.string(),
      value: z.number(),
      display: z.string(),
    })
    .transform((data) => ({
      code: data['code'],
      symbol: data['symbol'],
      value: data['value'],
      display: data['display'],
    }));
});

/**
 * Zod schema for mapping the PriceModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const priceModelRequest = z.lazy(() => {
  return z
    .object({
      code: z.string(),
      symbol: z.string(),
      value: z.number(),
      display: z.string(),
    })
    .transform((data) => ({
      code: data['code'],
      symbol: data['symbol'],
      value: data['value'],
      display: data['display'],
    }));
});
