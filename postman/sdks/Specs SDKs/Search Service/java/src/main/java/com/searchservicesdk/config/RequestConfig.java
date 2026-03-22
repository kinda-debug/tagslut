package com.searchservicesdk.config;

import com.searchservicesdk.http.Environment;
import lombok.Builder;
import lombok.Data;

/**
 * Configuration class for request-level, method-level, and service-level overrides.
 *
 * <p>Provides a hierarchical configuration override mechanism with the following priority
 * (highest to lowest):
 * <ol>
 *   <li>Request config - passed directly to a method call</li>
 *   <li>Method config - set via {@code set<MethodName>Config()} on a service</li>
 *   <li>Service config - set via {@code setConfig()} on a service</li>
 *   <li>SDK config - set at SDK initialization</li>
 * </ol>
 *
 * <p>All fields are optional (nullable). Only non-null fields will override the corresponding
 * SDK-level configuration values.
 */
@Builder
@Data
public class RequestConfig {

  /** Override the base URL for API requests. */
  private String baseUrl;

  /** Override the environment for API requests. */
  private Environment environment;

  /** Override the request timeout in milliseconds. */
  private Long timeout;

  /** Override the access token (Bearer token) for authentication. */
  private String accessToken;

  /** Override the retry configuration. */
  private RetryConfig retryConfig;

  /**
   * Merges multiple {@link RequestConfig} instances in order. Later configs take precedence
   * over earlier ones for any non-null field.
   *
   * @param configs The configs to merge (in order of increasing priority)
   * @return A new merged {@link RequestConfig}
   */
  public static RequestConfig merge(RequestConfig... configs) {
    RequestConfigBuilder builder = RequestConfig.builder();
    for (RequestConfig cfg : configs) {
      if (cfg == null) continue;
      if (cfg.getBaseUrl() != null) builder.baseUrl(cfg.getBaseUrl());
      if (cfg.getEnvironment() != null) builder.environment(cfg.getEnvironment());
      if (cfg.getTimeout() != null) builder.timeout(cfg.getTimeout());
      if (cfg.getAccessToken() != null) builder.accessToken(cfg.getAccessToken());
      if (cfg.getRetryConfig() != null) builder.retryConfig(cfg.getRetryConfig());
    }
    return builder.build();
  }
}
