import { z } from 'zod';
import { BaseService } from '../base-service';
import { ContentType, HttpResponse, SdkConfig } from '../../http/types';
import { RequestBuilder } from '../../http/transport/request-builder';
import { SerializationStyle } from '../../http/serialization/base-serializer';
import { ThrowableError } from '../../http/errors/throwable-error';
import { Environment } from '../../http/environment';
import {
  GetTokenClientCredentialsRequest,
  getTokenClientCredentialsRequestRequest,
} from './models/get-token-client-credentials-request';

/**
 * Service class for AuthService operations.
 * Provides methods to interact with AuthService-related API endpoints.
 * All methods return promises and handle request/response serialization automatically.
 */
export class AuthService extends BaseService {
  protected getTokenClientCredentials_Config: Partial<SdkConfig> = {
    environment: Environment.BASE_URL,
  };

  protected introspectTokenConfig: Partial<SdkConfig> = { environment: Environment.BASE_URL };

  /**
   * Sets method-level configuration for getTokenClientCredentials_.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setGetTokenClientCredentials_Config(config: Partial<SdkConfig>): this {
    this.getTokenClientCredentials_Config = config;
    return this;
  }

  /**
   * Sets method-level configuration for introspectToken.
   * @param config - Partial configuration to override service-level defaults
   * @returns This service instance for method chaining
   */
  setIntrospectTokenConfig(config: Partial<SdkConfig>): this {
    this.introspectTokenConfig = config;
    return this;
  }

  /**
   *
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async getTokenClientCredentials_(
    body: GetTokenClientCredentialsRequest,
    requestConfig?: Partial<SdkConfig>,
  ): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(
      this.getTokenClientCredentials_Config,
      requestConfig,
    );
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('POST')
      .setPath('/v4/auth/o/token')
      .setRequestSchema(getTokenClientCredentialsRequestRequest)
      .setRequestContentType(ContentType.FormUrlEncoded)
      .addResponse({
        schema: z.any(),
        contentType: ContentType.Json,
        status: 200,
      })
      .addHeaderParam({ key: 'Content-Type', value: 'application/x-www-form-urlencoded' })
      .addBody(body)
      .build();
    return this.client.callDirect<any>(request);
  }

  /**
   *
   * @param {Partial<SdkConfig>} [requestConfig] - The request configuration for retry and validation.
   * @returns {Promise<HttpResponse<any>>} - OK
   */
  async introspectToken(requestConfig?: Partial<SdkConfig>): Promise<any> {
    const resolvedConfig = this.getResolvedConfig(this.introspectTokenConfig, requestConfig);
    const request = new RequestBuilder()
      .setConfig(resolvedConfig)
      .setBaseUrl(resolvedConfig)
      .setMethod('GET')
      .setPath('/v4/auth/o/introspect')
      .setRequestSchema(z.any())
      .addAccessTokenAuth(resolvedConfig?.token, 'Bearer')
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
