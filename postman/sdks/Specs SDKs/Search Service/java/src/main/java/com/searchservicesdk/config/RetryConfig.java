package com.searchservicesdk.config;

import com.searchservicesdk.http.HttpMethod;
import java.net.ProtocolException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import lombok.Builder;
import lombok.Data;

/**
 * Configuration for automatic retry behavior on failed requests.
 * Defines retry limits, backoff strategy, and conditions for retrying requests.
 * Uses builder pattern for flexible configuration with sensible defaults.
 */
@Data
@Builder
public class RetryConfig {

  @Builder.Default
  private int maxRetries = 3;

  @Builder.Default
  private int initialDelay = 150;

  @Builder.Default
  private int maxDelay = 5000;

  @Builder.Default
  private double backoffFactor = 2;

  @Builder.Default
  private int jitter = 50;

  @Builder.Default
  private List<Integer> statusCodesToRetry = Collections.emptyList();

  @Builder.Default
  private List<HttpMethod> httpMethodsToRetry = Arrays.asList(
    HttpMethod.GET,
    HttpMethod.POST,
    HttpMethod.PUT,
    HttpMethod.DELETE,
    HttpMethod.PATCH,
    HttpMethod.HEAD,
    HttpMethod.OPTIONS
  );

  @Builder.Default
  private List<Class<? extends Throwable>> exceptionsToRetry = Arrays.asList(
    SocketException.class,
    SocketTimeoutException.class,
    ProtocolException.class
  );
}
