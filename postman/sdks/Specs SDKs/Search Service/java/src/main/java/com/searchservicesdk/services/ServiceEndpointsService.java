package com.searchservicesdk.services;

import com.fasterxml.jackson.core.type.TypeReference;
import com.searchservicesdk.config.RequestConfig;
import com.searchservicesdk.config.SearchServiceSdkConfig;
import com.searchservicesdk.exceptions.ApiError;
import com.searchservicesdk.http.Environment;
import com.searchservicesdk.http.HttpMethod;
import com.searchservicesdk.http.ModelConverter;
import com.searchservicesdk.http.util.RequestBuilder;
import com.searchservicesdk.models.HealthCheckResponse;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import lombok.NonNull;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * ServiceEndpointsService Service
 */
public class ServiceEndpointsService extends BaseService {

  private RequestConfig healthCheckSearchHealthCheckGetConfig;

  /**
   * Constructs a new instance of ServiceEndpointsService.
   *
   * @param httpClient The HTTP client to use for requests
   * @param config The SDK configuration
   */
  public ServiceEndpointsService(@NonNull OkHttpClient httpClient, SearchServiceSdkConfig config) {
    super(httpClient, config);
  }

  /**
   * Sets method-level configuration for {@code healthCheckSearchHealthCheckGet}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public ServiceEndpointsService setHealthCheckSearchHealthCheckGetConfig(RequestConfig config) {
    this.healthCheckSearchHealthCheckGetConfig = config;
    return this;
  }

  /**
   * Health-Check
   *
   * @return response of {@code HealthCheckResponse}
   */
  public HealthCheckResponse healthCheckSearchHealthCheckGet() throws ApiError {
    return this.healthCheckSearchHealthCheckGet(null);
  }

  /**
   * Health-Check
   *
   * @return response of {@code HealthCheckResponse}
   */
  public HealthCheckResponse healthCheckSearchHealthCheckGet(RequestConfig requestConfig)
    throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.healthCheckSearchHealthCheckGetConfig, requestConfig);
    Request request = this.buildHealthCheckSearchHealthCheckGetRequest(resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<HealthCheckResponse>() {});
  }

  /**
   * Health-Check
   *
   * @return response of {@code CompletableFuture<HealthCheckResponse>}
   */
  public CompletableFuture<HealthCheckResponse> healthCheckSearchHealthCheckGetAsync()
    throws ApiError {
    return this.healthCheckSearchHealthCheckGetAsync(null);
  }

  /**
   * Health-Check
   *
   * @return response of {@code CompletableFuture<HealthCheckResponse>}
   */
  public CompletableFuture<HealthCheckResponse> healthCheckSearchHealthCheckGetAsync(
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.healthCheckSearchHealthCheckGetConfig, requestConfig);
    Request request = this.buildHealthCheckSearchHealthCheckGetRequest(resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<HealthCheckResponse>() {});
    });
  }

  private Request buildHealthCheckSearchHealthCheckGetRequest(RequestConfig resolvedConfig) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.DEFAULT),
      "search/health-check"
    ).build();
  }
}
