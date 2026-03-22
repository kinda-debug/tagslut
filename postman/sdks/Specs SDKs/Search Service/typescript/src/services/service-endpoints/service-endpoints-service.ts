import { z } from 'zod';
import { BaseService } from '../base-service';
import { ContentType, HttpResponse, SdkConfig } from '../../http/types';
import { RequestBuilder } from '../../http/transport/request-builder';
import { SerializationStyle } from '../../http/serialization/base-serializer';
import { ThrowableError } from '../../http/errors/throwable-error';
import { Environment } from '../../http/environment';
import { HealthCheckResponse, healthCheckResponseResponse } from './models/health-check-response';

/**
 * Service class for ServiceEndpointsService operations.
 * Provides methods to interact with ServiceEndpointsService-related API endpoints.
 * All methods return promises and handle request/response serialization automatically.
 */
export class ServiceEndpointsService extends BaseService {
  protected healthCheckSearchHealthCheckGetConfig?: Partial<SdkConfig>;

  /**
   * Sets method-level configuration for healthCheckSearchHealthCheckGet.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setHealthCheckSearchHealthCheckGetConfig(config: Partial<SdkConfig>): this {
    this.healthCheckSearchHealthCheckGetConfig = config;
    return this;
  }

  /**
   * Endpoint used for health checking the service and the ES connectivity status.
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<HealthCheckResponse>>} - Successful Response
   */
  async healthCheckSearchHealthCheckGet(
    requestConfig?: Partial<SdkConfig>,
  ): Promise<HealthCheckResponse> {
    const resolvedConfig = this.getResolvedConfig(
      this.healthCheckSearchHealthCheckGetConfig,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/search/health-check')
      .setRequestSchema(z.any())
      .setRequestContentType(ContentType.Json)
      .addResponse({
        schema: healthCheckResponseResponse,
        contentType: ContentType.Json,
        status: 200,
      })
      .build();
    return this.client.callDirect<HealthCheckResponse>(request);
  }
}
