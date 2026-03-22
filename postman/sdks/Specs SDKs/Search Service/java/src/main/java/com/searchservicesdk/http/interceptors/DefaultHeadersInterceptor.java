package com.searchservicesdk.http.interceptors;

import com.searchservicesdk.config.SearchServiceSdkConfig;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import okhttp3.Interceptor;
import okhttp3.Request;
import okhttp3.Request.Builder;
import okhttp3.Response;

/**
 * OkHttp interceptor that adds default headers to all requests.
 * Currently adds the User-Agent header based on SDK configuration.
 */
public class DefaultHeadersInterceptor implements Interceptor {

  private final Map<String, String> defaultHeaders = new HashMap<>();

  /**
   * Constructs a new DefaultHeadersInterceptor.
   *
   * @param config The SDK configuration containing default header values
   */
  public DefaultHeadersInterceptor(SearchServiceSdkConfig config) {
    defaultHeaders.put("User-Agent", config.getUserAgent());
  }

  /**
   * Intercepts a request to add default headers before proceeding.
   *
   * @param chain The OkHttp interceptor chain
   * @return The HTTP response
   * @throws IOException if an I/O error occurs during request execution
   */
  @Override
  public Response intercept(Chain chain) throws IOException {
    return chain.proceed(addDefaultHeadersToRequest(chain.request()));
  }

  /**
   * Adds default headers to a request.
   *
   * @param request The HTTP request to modify
   * @return The modified request with default headers added
   */
  private Request addDefaultHeadersToRequest(Request request) {
    if (defaultHeaders.isEmpty()) {
      return request;
    }

    Builder requestBuilder = request.newBuilder();

    defaultHeaders.forEach(requestBuilder::addHeader);

    return requestBuilder.build();
  }
}
