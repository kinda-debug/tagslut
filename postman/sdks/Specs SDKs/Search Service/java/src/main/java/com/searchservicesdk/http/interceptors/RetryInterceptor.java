package com.searchservicesdk.http.interceptors;

import com.searchservicesdk.config.RetryConfig;
import com.searchservicesdk.http.HttpMethod;
import java.io.IOException;
import lombok.AllArgsConstructor;
import okhttp3.Interceptor;
import okhttp3.Request;
import okhttp3.Response;

/**
 * OkHttp interceptor that automatically retries failed HTTP requests.
 * Supports configurable retry attempts, backoff delays, and specific status codes or exceptions to retry.
 */
@AllArgsConstructor
public class RetryInterceptor implements Interceptor {

  private RetryConfig config;

  /**
   * Intercepts an HTTP request and retries it according to the configured retry policy.
   * Implements exponential backoff between retry attempts.
   *
   * @param chain The OkHttp interceptor chain
   * @return The HTTP response from a successful attempt
   * @throws IOException if all retry attempts fail or a non-retryable exception occurs
   */
  @Override
  public Response intercept(Chain chain) throws IOException {
    Request request = chain.request();
    int tryCount = 0;

    Response response = null;
    while (tryCount <= config.getMaxRetries()) {
      if (response != null) {
        response.close();
      }

      try {
        response = chain.proceed(request);
        if (!isRetryable(response)) {
          return response;
        }
        tryCount++;
      } catch (IOException e) {
        if (
          !config.getExceptionsToRetry().contains(e.getClass()) ||
          tryCount == config.getMaxRetries()
        ) {
          throw e;
        }
      }

      final int delay = calculateDelay(tryCount);
      try {
        Thread.sleep(delay);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IOException("Thread interrupted while waiting for retry", e);
      }
    }

    return response;
  }

  /**
   * Calculates the delay before the next retry attempt using exponential backoff.
   *
   * @param tryCount The current retry attempt number (1-indexed)
   * @return The delay in milliseconds, capped at the configured maximum delay
   */
  private int calculateDelay(int tryCount) {
    final int delay = (int) (config.getInitialDelay() *
      Math.pow(config.getBackoffFactor(), tryCount - 1));
    return Math.min(delay, config.getMaxDelay());
  }

  /**
   * Determines if a response should be retried based on status code and HTTP method.
   * By default, retries all 5xx server errors and specific 4xx client errors (408 Timeout, 429 Rate Limit).
   *
   * @param response The HTTP response to check
   * @return true if the response should be retried, false otherwise
   */
  private boolean isRetryable(Response response) {
    final int statusCode = response.code();
    final boolean isRetryableStatusCode = !config.getStatusCodesToRetry().isEmpty()
      ? config.getStatusCodesToRetry().contains(statusCode)
      : statusCode >= 500 || statusCode == 408 || statusCode == 429;

    final boolean isRetryableMethod = config
      .getHttpMethodsToRetry()
      .stream()
      .map((HttpMethod m) -> m.getMethod())
      .anyMatch(method -> method.equals(response.request().method()));

    return isRetryableStatusCode && isRetryableMethod;
  }
}
