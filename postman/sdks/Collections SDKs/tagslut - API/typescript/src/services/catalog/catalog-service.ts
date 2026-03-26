import { z } from 'zod';
import { BaseService } from '../base-service';
import { ContentType, HttpResponse, SdkConfig } from '../../http/types';
import { RequestBuilder } from '../../http/transport/request-builder';
import { SerializationStyle } from '../../http/serialization/base-serializer';
import { ThrowableError } from '../../http/errors/throwable-error';
import { Environment } from '../../http/environment';
import { ReleaseTracksParams, TracksByIsrcQueryParam_Params } from './request-params';

/**
 * Service class for CatalogService operations.
 * Provides methods to interact with CatalogService-related API endpoints.
 * All methods return promises and handle request/response serialization automatically.
 */
export class CatalogService extends BaseService {
  protected trackByIdConfig: Partial<SdkConfig> = { environment: Environment.BASE_URL };

  protected tracksByIsrcQueryParam_Config: Partial<SdkConfig> = {
    environment: Environment.BASE_URL_1,
  };

  protected isrcStoreLookupPathBasedPhase3d_Config: Partial<SdkConfig> = {
    environment: Environment.BASE_URL,
  };

  protected releaseByIdConfig: Partial<SdkConfig> = { environment: Environment.BASE_URL };

  protected releaseTracksConfig: Partial<SdkConfig> = { environment: Environment.BASE_URL_1 };

  /**
   * Sets method-level configuration for trackById.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setTrackByIdConfig(config: Partial<SdkConfig>): this {
    this.trackByIdConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for tracksByIsrcQueryParam_.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setTracksByIsrcQueryParam_Config(config: Partial<SdkConfig>): this {
    this.tracksByIsrcQueryParam_Config = config;
    return this;
  }

  /**
   * Sets method-level configuration for isrcStoreLookupPathBasedPhase3d_.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setIsrcStoreLookupPathBasedPhase3d_Config(config: Partial<SdkConfig>): this {
    this.isrcStoreLookupPathBasedPhase3d_Config = config;
    return this;
  }

  /**
   * Sets method-level configuration for releaseById.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setReleaseByIdConfig(config: Partial<SdkConfig>): this {
    this.releaseByIdConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for releaseTracks.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setReleaseTracksConfig(config: Partial<SdkConfig>): this {
    this.releaseTracksConfig = config;
    return this;
  }

  /**
   *
   * @param {string} beatportTestTrackId -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async trackById(beatportTestTrackId: string, requestConfig?: Partial<SdkConfig>): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this.trackByIdConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v4/catalog/tracks/{beatport_test_track_id}')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token, 'Bearer')
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .addPathParam({
        key: 'beatport_test_track_id',
        value: beatportTestTrackId,
      })
      .build();
    return this.client.callDirect<any>(request);
  }

  /**
   *
   * @param {string} [params.isrc] -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async tracksByIsrcQueryParam_(
    params?: TracksByIsrcQueryParam_Params,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(
      this.tracksByIsrcQueryParam_Config,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v4/catalog/tracks')
      .setRequestSchema(z.any())
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
   * @param {string} beatportTestIsrc -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async isrcStoreLookupPathBasedPhase3d_(
    beatportTestIsrc: string,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(
      this.isrcStoreLookupPathBasedPhase3d_Config,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v4/catalog/tracks/store/{beatport_test_isrc}')
      .setRequestSchema(z.any())
      .addBasicAuth(resolvedConfig?.username, resolvedConfig?.password)
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .addPathParam({
        key: 'beatport_test_isrc',
        value: beatportTestIsrc,
      })
      .build();
    return this.client.callDirect<any>(request);
  }

  /**
   *
   * @param {string} beatportTestReleaseId -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async releaseById(
    beatportTestReleaseId: string,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this.releaseByIdConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v4/catalog/releases/{beatport_test_release_id}')
      .setRequestSchema(z.any())
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .addPathParam({
        key: 'beatport_test_release_id',
        value: beatportTestReleaseId,
      })
      .build();
    return this.client.callDirect<any>(request);
  }

  /**
   *
   * @param {string} beatportTestReleaseId -
   * @param {string} [params.perPage] -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async releaseTracks(
    beatportTestReleaseId: string,
    params?: ReleaseTracksParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this.releaseTracksConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v4/catalog/releases/{beatport_test_release_id}/tracks')
      .setRequestSchema(z.any())
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .addPathParam({
        key: 'beatport_test_release_id',
        value: beatportTestReleaseId,
      })
      .addQueryParam({
        key: 'per_page',
        value: params?.perPage,
      })
      .build();
    return this.client.callDirect<any>(request);
  }
}
