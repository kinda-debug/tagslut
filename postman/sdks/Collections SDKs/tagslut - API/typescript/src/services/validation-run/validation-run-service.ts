import { z } from 'zod';
import { BaseService } from '../base-service';
import { ContentType, HttpResponse, SdkConfig } from '../../http/types';
import { RequestBuilder } from '../../http/transport/request-builder';
import { SerializationStyle } from '../../http/serialization/base-serializer';
import { ThrowableError } from '../../http/errors/throwable-error';
import { Environment } from '../../http/environment';
import { _6aResolveTidalAlbumToIsrcParams } from './request-params';

/**
 * Service class for ValidationRunService operations.
 * Provides methods to interact with ValidationRunService-related API endpoints.
 * All methods return promises and handle request/response serialization automatically.
 */
export class ValidationRunService extends BaseService {
  protected _6aResolveTidalAlbumToIsrcConfig: Partial<SdkConfig> = { environment: Environment.API };

  protected _6bTrackByIdValidation_Config: Partial<SdkConfig> = {
    environment: Environment.BASE_URL,
  };

  protected _6cRunNotesConfig: Partial<SdkConfig> = { environment: Environment.EXAMPLE };

  /**
   * Sets method-level configuration for _6aResolveTidalAlbumToIsrc.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  set_6aResolveTidalAlbumToIsrcConfig(config: Partial<SdkConfig>): this {
    this._6aResolveTidalAlbumToIsrcConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for _6bTrackByIdValidation_.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  set_6bTrackByIdValidation_Config(config: Partial<SdkConfig>): this {
    this._6bTrackByIdValidation_Config = config;
    return this;
  }

  /**
   * Sets method-level configuration for _6cRunNotes.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  set_6cRunNotesConfig(config: Partial<SdkConfig>): this {
    this._6cRunNotesConfig = config;
    return this;
  }

  /**
   *
   * @param {string} [params.countryCode] -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async _6aResolveTidalAlbumToIsrc(
    params?: _6aResolveTidalAlbumToIsrcParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(
      this._6aResolveTidalAlbumToIsrcConfig,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v1/albums/507881809/tracks')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token, 'Bearer')
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
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
   * @param {string} beatportTestTrackId -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async _6bTrackByIdValidation_(
    beatportTestTrackId: string,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(
      this._6bTrackByIdValidation_Config,
      requestConfig,
    );
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
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async _6cRunNotes(requestConfig?: Partial<SdkConfig>): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this._6cRunNotesConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/')
      .setRequestSchema(z.any())
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .build();
    return this.client.callDirect<any>(request);
  }
}
