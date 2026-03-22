package com.searchservicesdk.services;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.searchservicesdk.config.RequestConfig;
import com.searchservicesdk.config.SearchServiceSdkConfig;
import com.searchservicesdk.exceptions.ApiError;
import com.searchservicesdk.http.Environment;
import com.searchservicesdk.http.ModelConverter;
import com.searchservicesdk.http.interceptors.RetryInterceptor;
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.net.SocketTimeoutException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;
import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import org.jetbrains.annotations.NotNull;

/**
 * Base service class that all API service classes extend.
 * Provides common functionality including HTTP request execution, error handling,
 * and configuration management.
 */
public class BaseService {

  private static final Logger logger = Logger.getLogger(BaseService.class.getName());
  protected OkHttpClient httpClient;
  protected SearchServiceSdkConfig config;
  protected Map<Integer, ErrorMapping<?>> errorMappings;
  protected ErrorMapping<?> defaultErrorMapping;

  /** Service-level configuration overrides */
  protected RequestConfig serviceConfig;

  /**
   * Internal class for mapping HTTP status codes to error models and exception types.
   *
   * @param <T> The error model type
   */
  private static class ErrorMapping<T> {

    private final Class<T> modelClass;
    private final Class<? extends ApiError> exceptionClass;

    public ErrorMapping(Class<T> modelClass, Class<? extends ApiError> exceptionClass) {
      this.modelClass = modelClass;
      this.exceptionClass = exceptionClass;
    }
  }

  /**
   * Constructs a new BaseService instance.
   *
   * @param httpClient The HTTP client to use for making requests
   * @param config The SDK configuration
   */
  public BaseService(OkHttpClient httpClient, SearchServiceSdkConfig config) {
    this.httpClient = httpClient;
    this.config = config;
    this.errorMappings = new HashMap<>();
  }

  /**
   * Sets the base URL for API requests.
   *
   * @param baseUrl The base URL to use
   */
  public void setBaseUrl(String baseUrl) {
    this.config.setBaseUrl(baseUrl);
  }

  /**
   * Sets the environment for API requests.
   *
   * @param environment The environment to use (e.g., DEFAULT, PRODUCTION, STAGING)
   */
  public void setEnvironment(Environment environment) {
    this.config.setEnvironment(environment);
  }

  /**
   * Sets service-level configuration that applies to all methods in this service.
   * Service-level overrides take precedence over SDK-level configuration but are
   * overridden by method-level and request-level configurations.
   *
   * @param config The configuration overrides to apply at the service level
   */
  public void setConfig(RequestConfig config) {
    this.serviceConfig = config;
  }

  /**
   * Resolves configuration from the hierarchy: requestConfig > methodConfig > serviceConfig.
   * Merges override configs into a single {@link RequestConfig}. SDK defaults are used as
   * fallbacks where these overrides are not provided.
   *
   * @param methodConfig Method-level configuration override (may be null)
   * @param requestConfig Request-level configuration override (may be null)
   * @return Merged configuration with all overrides applied
   */
  protected RequestConfig getResolvedConfig(
    RequestConfig methodConfig,
    RequestConfig requestConfig
  ) {
    return RequestConfig.merge(this.serviceConfig, methodConfig, requestConfig);
  }

  /**
   * Resolves the base URL from the configuration hierarchy.
   * Priority: resolvedConfig.baseUrl > sdkConfig.baseUrl > resolvedConfig.environment > defaultEnvironment.
   *
   * @param resolvedConfig The merged request configuration (may be null)
   * @param defaultEnvironment The default environment for this method
   * @return The resolved base URL
   */
  protected String resolveBaseUrl(RequestConfig resolvedConfig, Environment defaultEnvironment) {
    if (resolvedConfig != null && resolvedConfig.getBaseUrl() != null) {
      return resolvedConfig.getBaseUrl();
    }
    if (this.config.getBaseUrl() != null) {
      return this.config.getBaseUrl();
    }
    if (resolvedConfig != null && resolvedConfig.getEnvironment() != null) {
      return resolvedConfig.getEnvironment().getUrl();
    }
    return defaultEnvironment.getUrl();
  }

  /**
   * Resolves the access token from the configuration hierarchy.
   *
   * @param resolvedConfig The merged request configuration (may be null)
   * @return The resolved access token
   */
  protected String resolveAccessToken(RequestConfig resolvedConfig) {
    if (resolvedConfig != null && resolvedConfig.getAccessToken() != null) {
      return resolvedConfig.getAccessToken();
    }
    return this.config.getAccessToken();
  }

  /**
   * Creates an OkHttpClient with per-request overrides from the resolved configuration.
   * Applies timeout and/or retry config overrides when present.
   * If no overrides are present, returns the original client.
   *
   * @param resolvedConfig The resolved request configuration
   * @return An OkHttpClient with the appropriate overrides applied
   */
  protected OkHttpClient getHttpClientForRequest(RequestConfig resolvedConfig) {
    if (resolvedConfig == null) {
      return this.httpClient;
    }

    boolean needsRebuild = resolvedConfig.getTimeout() != null;
    needsRebuild = needsRebuild || resolvedConfig.getRetryConfig() != null;

    if (!needsRebuild) {
      return this.httpClient;
    }

    OkHttpClient.Builder builder = this.httpClient.newBuilder();

    if (resolvedConfig.getTimeout() != null) {
      builder.readTimeout(resolvedConfig.getTimeout(), TimeUnit.MILLISECONDS);
    }

    if (resolvedConfig.getRetryConfig() != null) {
      List<okhttp3.Interceptor> interceptors = new ArrayList<>(builder.interceptors());
      interceptors.replaceAll(i ->
        i instanceof RetryInterceptor ? new RetryInterceptor(resolvedConfig.getRetryConfig()) : i
      );
      builder.interceptors().clear();
      interceptors.forEach(builder::addInterceptor);
    }

    return builder.build();
  }

  /**
   * Registers an error mapping for a specific HTTP status code.
   * When a response with this status is received, the SDK will deserialize the error
   * response to the specified model class and throw the specified exception type.
   *
   * @param <T> The error model type
   * @param status The HTTP status code to map
   * @param modelClass The class to deserialize the error response into
   * @param exceptionClass The exception class to throw
   */
  protected <T> void addErrorMapping(
    int status,
    Class<T> modelClass,
    Class<? extends ApiError> exceptionClass
  ) {
    this.errorMappings.put(status, new ErrorMapping<>(modelClass, exceptionClass));
  }

  /**
   * Registers a default error mapping for unmapped HTTP status codes.
   * When a response with an unmapped status is received the SDK will deserialize the error
   * response to the specified model class and throw the specified exception type.
   *
   * @param <T> The error model type
   * @param modelClass The class to deserialize the error response into
   * @param exceptionClass The exception class to throw
   */
  protected <T> void addDefaultErrorMapping(
    Class<T> modelClass,
    Class<? extends ApiError> exceptionClass
  ) {
    this.defaultErrorMapping = new ErrorMapping<>(modelClass, exceptionClass);
  }

  /**
   * Extracts an error message from a response and optional error model.
   * Attempts to get the message from the error model's getMessage() method,
   * falls back to the response message, or constructs a message from the status code and URL.
   *
   * @param response The HTTP response
   * @param errorModel The deserialized error model (may be null)
   * @return The extracted or constructed error message
   */
  private String extractErrorMessage(Response response, Object errorModel) {
    String message = null;

    if (errorModel != null) {
      try {
        message = (String) errorModel.getClass().getMethod("getMessage").invoke(errorModel);
      } catch (Exception e) {
        // Ignore if getMessage doesn't exist or fails
      }
    }

    if (Objects.isNull(message) || message.trim().isEmpty()) {
      message = response.message();
    }

    if (Objects.isNull(message) || message.trim().isEmpty()) {
      message = String.format(
        "%d error in request to: %s",
        response.code(),
        response.request().url()
      );
    }

    return message;
  }

  /**
   * Executes an HTTP request synchronously.
   * Handles error responses by checking error mappings and throwing appropriate exceptions.
   *
   * @param request The HTTP request to execute
   * @param resolvedConfig The resolved request configuration (may contain timeout override)
   * @return The HTTP response if successful
   * @throws ApiError if the request fails or returns an error status code
   */
  protected Response execute(Request request, RequestConfig resolvedConfig) throws ApiError {
    OkHttpClient client = this.getHttpClientForRequest(resolvedConfig);
    Response response;
    try {
      response = client.newCall(request).execute();
    } catch (IOException e) {
      if (e instanceof SocketTimeoutException) {
        throw new ApiError("Request timed out", 408, null);
      }
      throw new ApiError(e.getMessage(), 0, null);
    }

    if (response.isSuccessful()) {
      return response;
    }

    // Handle error response
    ErrorMapping<?> errorMapping =
      this.errorMappings.getOrDefault(response.code(), this.defaultErrorMapping);
    if (errorMapping != null) {
      Object errorModel = null;
      try {
        errorModel = ModelConverter.convert(response, errorMapping.modelClass);
      } catch (Exception e) {
        logger.log(
          Level.WARNING,
          "Failed to deserialize error response to " + errorMapping.modelClass.getName(),
          e
        );
      }

      if (errorModel != null) {
        try {
          Constructor<? extends ApiError> constructor = errorMapping.exceptionClass.getConstructor(
            errorMapping.modelClass,
            String.class,
            int.class,
            Response.class
          );
          String message = extractErrorMessage(response, errorModel);
          throw constructor.newInstance(errorModel, message, response.code(), response);
        } catch (ReflectiveOperationException e) {
          logger.log(
            Level.WARNING,
            "Failed to create exception instance for " + errorMapping.exceptionClass.getName(),
            e
          );
        }
      }
    }

    // If no specific error model is mapped or conversion failed, throw generic ApiError
    throw new ApiError(extractErrorMessage(response, null), response.code(), response);
  }

  /**
   * Executes an HTTP request asynchronously.
   * Returns a CompletableFuture that completes with the response or completes exceptionally
   * if an error occurs. Handles error responses by checking error mappings.
   *
   * @param request The HTTP request to execute
   * @param resolvedConfig The resolved request configuration (may contain timeout override)
   * @return A CompletableFuture that completes with the HTTP response
   */
  protected CompletableFuture<Response> executeAsync(
    Request request,
    RequestConfig resolvedConfig
  ) {
    OkHttpClient client = this.getHttpClientForRequest(resolvedConfig);
    CompletableFuture<Response> future = new CompletableFuture<>();
    client
      .newCall(request)
      .enqueue(
        new Callback() {
          @Override
          public void onResponse(@NotNull Call call, @NotNull Response response) {
            if (!response.isSuccessful()) {
              // Handle error response
              ErrorMapping<?> errorMapping = errorMappings.get(response.code());
              if (errorMapping != null) {
                try {
                  Object errorModel = ModelConverter.convert(response, errorMapping.modelClass);
                  if (errorModel != null) {
                    // Use reflection to create the exception
                    Constructor<? extends ApiError> constructor =
                      errorMapping.exceptionClass.getConstructor(
                        errorMapping.modelClass,
                        String.class,
                        int.class,
                        Response.class
                      );
                    String message = extractErrorMessage(response, errorModel);
                    future.completeExceptionally(
                      constructor.newInstance(errorModel, message, response.code(), response)
                    );
                    return;
                  }
                } catch (Exception e) {
                  logger.log(
                    Level.WARNING,
                    "Failed to deserialize error response to " + errorMapping.modelClass.getName(),
                    e
                  );
                }
              }

              // If no specific error model is mapped or conversion failed, throw generic ApiError
              ApiError error = new ApiError(
                extractErrorMessage(response, null),
                response.code(),
                response
              );
              future.completeExceptionally(error);
              return;
            }

            future.complete(response);
          }

          @Override
          public void onFailure(@NotNull Call call, @NotNull IOException e) {
            if (e instanceof SocketTimeoutException) {
              ApiError error = new ApiError("Request timed out", 408, null);
              future.completeExceptionally(error);
            } else {
              ApiError error = new ApiError(e.getMessage(), 0, null);
              future.completeExceptionally(error);
            }
          }
        }
      );
    return future;
  }
}
