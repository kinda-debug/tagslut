import { z } from 'zod';

/**
 * Zod schema for the GetTokenClientCredentialsRequest model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const getTokenClientCredentialsRequest = z.lazy(() => {
  return z.object({
    grantType: z.string().optional().nullable(),
    clientId: z.string().optional().nullable(),
    clientSecret: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {GetTokenClientCredentialsRequest} getTokenClientCredentialsRequest
 * @property {string}
 * @property {string}
 * @property {string}
 */
export type GetTokenClientCredentialsRequest = z.infer<typeof getTokenClientCredentialsRequest>;

/**
 * Zod schema for mapping API responses to the GetTokenClientCredentialsRequest application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const getTokenClientCredentialsRequestResponse = z.lazy(() => {
  return z
    .object({
      grant_type: z.string().optional().nullable(),
      client_id: z.string().optional().nullable(),
      client_secret: z.string().optional().nullable(),
    })
    .transform((data) => ({
      grantType: data['grant_type'],
      clientId: data['client_id'],
      clientSecret: data['client_secret'],
    }));
});

/**
 * Zod schema for mapping the GetTokenClientCredentialsRequest application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const getTokenClientCredentialsRequestRequest = z.lazy(() => {
  return z
    .object({
      grantType: z.string().optional().nullable(),
      clientId: z.string().optional().nullable(),
      clientSecret: z.string().optional().nullable(),
    })
    .transform((data) => ({
      grant_type: data['grantType'],
      client_id: data['clientId'],
      client_secret: data['clientSecret'],
    }));
});
