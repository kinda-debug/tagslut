import { z } from 'zod';

/**
 * Zod schema for the HealthCheckResponse model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const healthCheckResponse = z.lazy(() => {
  return z.object({
    remoteAddr: z.string(),
    commitHash: z.string(),
    serviceEsConnected: z.boolean(),
  });
});

/**
 * Response model for the `health-check` endpoint.
 * @typedef  {HealthCheckResponse} healthCheckResponse - Response model for the `health-check` endpoint. - Response model for the `health-check` endpoint.
 * @property {string} - The origin of the request.
 * @property {string} - The current docker image used by the service.
 * @property {boolean} - Bool that indicates if the service is connected to elasticsearch or not.
 */
export type HealthCheckResponse = z.infer<typeof healthCheckResponse>;

/**
 * Zod schema for mapping API responses to the HealthCheckResponse application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const healthCheckResponseResponse = z.lazy(() => {
  return z
    .object({
      remote_addr: z.string(),
      commit_hash: z.string(),
      service_es_connected: z.boolean(),
    })
    .transform((data) => ({
      remoteAddr: data['remote_addr'],
      commitHash: data['commit_hash'],
      serviceEsConnected: data['service_es_connected'],
    }));
});

/**
 * Zod schema for mapping the HealthCheckResponse application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const healthCheckResponseRequest = z.lazy(() => {
  return z
    .object({
      remoteAddr: z.string(),
      commitHash: z.string(),
      serviceEsConnected: z.boolean(),
    })
    .transform((data) => ({
      remote_addr: data['remoteAddr'],
      commit_hash: data['commitHash'],
      service_es_connected: data['serviceEsConnected'],
    }));
});
