import { z } from 'zod';
import { BaseService } from '../base-service';
import { ContentType, HttpResponse, SdkConfig } from '../../http/types';
import { RequestBuilder } from '../../http/transport/request-builder';
import { SerializationStyle } from '../../http/serialization/base-serializer';
import { ThrowableError } from '../../http/errors/throwable-error';
import { Environment } from '../../http/environment';
import { SearchTracksByTextParams } from './request-params';

/**
 * Service class for SearchService operations.
 * Provides methods to interact with SearchService-related API endpoints.
 * All methods return promises and handle request/response serialization automatically.
 */
export class SearchService extends BaseService {
  protected searchTracksByTextConfig: Partial<SdkConfig> = { environment: Environment.BASE_URL_1 };

  /**
   * Sets method-level configuration for searchTracksByText.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setSearchTracksByTextConfig(config: Partial<SdkConfig>): this {
    this.searchTracksByTextConfig = config;
    return this;
  }

  /**
   *
   * @param {string} [params.q] -
   * @param {string} [params.count] -
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async searchTracksByText(
    params?: SearchTracksByTextParams,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this.searchTracksByTextConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/search/v1/tracks')
      .setRequestSchema(z.any())
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
        key: 'count',
        value: params?.count,
      })
      .build();
    return this.client.callDirect<any>(request);
  }
}
