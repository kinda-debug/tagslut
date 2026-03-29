import { z } from 'zod';
import { BaseService } from '../base-service';
import { ContentType, HttpResponse, SdkConfig } from '../../http/types';
import { RequestBuilder } from '../../http/transport/request-builder';
import { SerializationStyle } from '../../http/serialization/base-serializer';
import { ThrowableError } from '../../http/errors/throwable-error';
import { Environment } from '../../http/environment';
import {
  _5aBeatportIsrcLookupParams,
  _5bTidalIsrcCrossCheckParams,
  _5cSpotifyIsrcCrossCheckParams,
} from './request-params';

/**
 * Service class for IdentityVerificationService operations.
 * Provides methods to interact with IdentityVerificationService-related API endpoints.
 * All methods return promises and handle request/response serialization automatically.
 */
export class IdentityVerificationService extends BaseService {
  protected _5aBeatportIsrcLookupConfig: Partial<SdkConfig> = {
    environment: Environment.BASE_URL_1,
  };

  protected _5bTidalIsrcCrossCheckConfig: Partial<SdkConfig> = { environment: Environment.API };

  protected _5cSpotifyIsrcCrossCheckConfig: Partial<SdkConfig> = { environment: Environment.API_1 };

  /**
   * Sets method-level configuration for _5aBeatportIsrcLookup.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  set_5aBeatportIsrcLookupConfig(config: Partial<SdkConfig>): this {
    this._5aBeatportIsrcLookupConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for _5bTidalIsrcCrossCheck.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  set_5bTidalIsrcCrossCheckConfig(config: Partial<SdkConfig>): this {
    this._5bTidalIsrcCrossCheckConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for _5cSpotifyIsrcCrossCheck.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  set_5cSpotifyIsrcCrossCheckConfig(config: Partial<SdkConfig>): this {
    this._5cSpotifyIsrcCrossCheckConfig = config;
    return this;
  }

  /**
   *
   * @param {string} [params.isrc] -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async _5aBeatportIsrcLookup(
    params?: _5aBeatportIsrcLookupParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this._5aBeatportIsrcLookupConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v4/catalog/tracks')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token, 'Bearer')
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .addQueryParam({
        key: 'isrc',
        value: params?.isrc,
      })
      .build();
    return this.client.callDirect<any>(request);
  }

  /**
   *
   * @param {string} [params.isrc] -
   * @param {string} [params.countryCode] -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async _5bTidalIsrcCrossCheck(
    params?: _5bTidalIsrcCrossCheckParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this._5bTidalIsrcCrossCheckConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v1/tracks')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token, 'Bearer')
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .addQueryParam({
        key: 'isrc',
        value: params?.isrc,
      })
      .addQueryParam({
        key: 'countryCode',
        value: params?.countryCode,
      })
      .build();
    return this.client.callDirect<any>(request);
  }

  /**
   *
   * @param {string} [params.q] -
   * @param {string} [params.type] -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async _5cSpotifyIsrcCrossCheck(
    params?: _5cSpotifyIsrcCrossCheckParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(
      this._5cSpotifyIsrcCrossCheckConfig,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v1/search')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token, 'Bearer')
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .addQueryParam({
        key: 'q',
        value: params?.q,
      })
      .addQueryParam({
        key: 'type',
        value: params?.type,
      })
      .build();
    return this.client.callDirect<any>(request);
  }
}
