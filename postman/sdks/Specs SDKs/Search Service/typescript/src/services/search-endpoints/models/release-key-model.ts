import { z } from 'zod';

/**
 * Zod schema for the ReleaseKeyModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const releaseKeyModel = z.lazy(() => {
  return z.object({
    keyId: z.number().optional().nullable(),
    keyName: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {ReleaseKeyModel} releaseKeyModel
 * @property {number}
 * @property {string}
 */
export type ReleaseKeyModel = z.infer<typeof releaseKeyModel>;

/**
 * Zod schema for mapping API responses to the ReleaseKeyModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releaseKeyModelResponse = z.lazy(() => {
  return z
    .object({
      key_id: z.number().optional().nullable(),
      key_name: z.string().optional().nullable(),
    })
    .transform((data) => ({
      keyId: data['key_id'],
      keyName: data['key_name'],
    }));
});

/**
 * Zod schema for mapping the ReleaseKeyModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const releaseKeyModelRequest = z.lazy(() => {
  return z
    .object({
      keyId: z.number().optional().nullable(),
      keyName: z.string().optional().nullable(),
    })
    .transform((data) => ({
      key_id: data['keyId'],
      key_name: data['keyName'],
    }));
});
