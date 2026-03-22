package com.searchservicesdk;

import com.searchservicesdk.config.SearchServiceSdkConfig;
import com.searchservicesdk.http.Environment;
import com.searchservicesdk.http.interceptors.DefaultHeadersInterceptor;
import com.searchservicesdk.http.interceptors.RetryInterceptor;
import com.searchservicesdk.services.SearchEndpointsService;
import com.searchservicesdk.services.ServiceEndpointsService;
import java.util.concurrent.TimeUnit;
import okhttp3.OkHttpClient;

/**
 * Main SDK client class for SearchServiceSdk.
 * Provides centralized access to all service endpoints with configurable authentication,
 * environment management, hooks, and HTTP client settings.
 */
public class SearchServiceSdk {

  public final ServiceEndpointsService serviceEndpoints;
  public final SearchEndpointsService searchEndpoints;

  private final SearchServiceSdkConfig config;

  /**
   * Constructs a new instance of SearchServiceSdk with default configuration.
   */
  public SearchServiceSdk() {
    // Default configs
    this(SearchServiceSdkConfig.builder().build());
  }

  /**
   * Constructs a new instance of SearchServiceSdk with custom configuration.
   * Initializes all services, HTTP client, and optional OAuth token manager.
   *
   * @param config The SDK configuration including base URL, authentication, timeout, and retry settings
   */
  public SearchServiceSdk(SearchServiceSdkConfig config) {
    this.config = config;

    final OkHttpClient httpClient = new OkHttpClient.Builder()
      .addInterceptor(new DefaultHeadersInterceptor(config))
      .addInterceptor(new RetryInterceptor(config.getRetryConfig()))
      .readTimeout(config.getTimeout(), TimeUnit.MILLISECONDS)
      .build();

    this.serviceEndpoints = new ServiceEndpointsService(httpClient, config);
    this.searchEndpoints = new SearchEndpointsService(httpClient, config);
  }

  /**
   * Sets the environment for all API requests.
   *
   * @param environment The environment to use (e.g., DEFAULT, PRODUCTION, STAGING)
   */
  public void setEnvironment(Environment environment) {
    setBaseUrl(environment.getUrl());
  }

  /**
   * Sets the base URL for all API requests.
   *
   * @param baseUrl The base URL to use for API requests
   */
  public void setBaseUrl(String baseUrl) {
    this.config.setBaseUrl(baseUrl);
  }

  /**
   * Sets the access token (Bearer token) for all API requests.
   *
   * @param token The access token to use for authentication
   */
  public void setAccessToken(String token) {
    this.config.setAccessToken(token);
  }
}
// c029837e0e474b76bc487506e8799df5e3335891efe4fb02bda7a1441840310c
