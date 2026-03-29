import { z } from 'zod';
import { BaseService } from '../base-service';
import { ContentType, HttpResponse, SdkConfig } from '../../http/types';
import { RequestBuilder } from '../../http/transport/request-builder';
import { SerializationStyle } from '../../http/serialization/base-serializer';
import { ThrowableError } from '../../http/errors/throwable-error';
import { Environment } from '../../http/environment';
import { MyBeatportTracksParams } from './request-params';

/**
 * Service class for MyLibraryService operations.
 * Provides methods to interact with MyLibraryService-related API endpoints.
 * All methods return promises and handle request/response serialization automatically.
 */
export class MyLibraryService extends BaseService {
  protected myBeatportTracksConfig: Partial<SdkConfig> = { environment: Environment.BASE_URL_1 };

  protected myAccountConfig: Partial<SdkConfig> = { environment: Environment.BASE_URL };

  /**
   * Sets method-level configuration for myBeatportTracks.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setMyBeatportTracksConfig(config: Partial<SdkConfig>): this {
    this.myBeatportTracksConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for myAccount.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setMyAccountConfig(config: Partial<SdkConfig>): this {
    this.myAccountConfig = config;
    return this;
  }

  /**
   *
   * @param {string} [params.page] -
   * @param {string} [params.perPage] -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async myBeatportTracks(
    params?: MyBeatportTracksParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this.myBeatportTracksConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v4/my/beatport/tracks')
      .setRequestSchema(z.any())
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .addQueryParam({
        key: 'page',
        value: params?.page,
      })
      .addQueryParam({
        key: 'per_page',
        value: params?.perPage,
      })
      .build();
    return this.client.callDirect<any>(request);
  }

  /**
   *
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async myAccount(requestConfig?: Partial<SdkConfig>): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this.myAccountConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v4/my/account')
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
