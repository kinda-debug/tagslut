/**
 * Available API environments with their base URLs.
 * Use these constants to configure the SDK for different environments (production, staging, etc.).
 */
export enum Environment {
  /** DEFAULT environment base URL */
  DEFAULT = 'https://{{base_url}}',
  /** BASE_URL environment base URL */
  BASE_URL = 'https://{{base_url}}',
  /** BASE_URL_1 environment base URL */
  BASE_URL_1 = '://{{base_url}}',
  /** API environment base URL */
  API = 'https://api.tidal.com',
  /** API_1 environment base URL */
  API_1 = 'https://api.spotify.com',
  /** EXAMPLE environment base URL */
  EXAMPLE = 'https://example.com',
}
