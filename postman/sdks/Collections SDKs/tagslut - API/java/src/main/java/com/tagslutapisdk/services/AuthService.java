package com.tagslutapisdk.services;

import com.fasterxml.jackson.core.type.TypeReference;
import com.tagslutapisdk.config.RequestConfig;
import com.tagslutapisdk.config.TagslutApiSdkConfig;
import com.tagslutapisdk.exceptions.ApiError;
import com.tagslutapisdk.http.Environment;
import com.tagslutapisdk.http.HttpMethod;
import com.tagslutapisdk.http.ModelConverter;
import com.tagslutapisdk.http.util.RequestBuilder;
import com.tagslutapisdk.models.GetTokenClientCredentialsRequest;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import lombok.NonNull;
import okhttp3.FormBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * AuthService Service
 */
public class AuthService extends BaseService {

  private RequestConfig getTokenClientCredentialsConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL)
    .build();
  private RequestConfig introspectTokenConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL)
    .build();

  /**
   * Constructs a new instance of AuthService.
   *
   * @param httpClient The HTTP client to use for requests
   * @param config The SDK configuration
   */
  public AuthService(@NonNull OkHttpClient httpClient, TagslutApiSdkConfig config) {
    super(httpClient, config);
  }

  /**
   * Sets method-level configuration for {@code getTokenClientCredentials}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public AuthService setGetTokenClientCredentialsConfig(RequestConfig config) {
    this.getTokenClientCredentialsConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code introspectToken}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public AuthService setIntrospectTokenConfig(RequestConfig config) {
    this.introspectTokenConfig = config;
    return this;
  }

  /**
   * Method getTokenClientCredentials
   * POST /v4/auth/o/token
   *
   * @param getTokenClientCredentialsRequest {@link GetTokenClientCredentialsRequest} Request Body
   * @return response of {@code Object}
   */
  public Object getTokenClientCredentials(
    @NonNull GetTokenClientCredentialsRequest getTokenClientCredentialsRequest
  ) throws ApiError {
    return this.getTokenClientCredentials(getTokenClientCredentialsRequest, null);
  }

  /**
   * Method getTokenClientCredentials
   * POST /v4/auth/o/token
   *
   * @param getTokenClientCredentialsRequest {@link GetTokenClientCredentialsRequest} Request Body
   * @return response of {@code Object}
   */
  public Object getTokenClientCredentials(
    @NonNull GetTokenClientCredentialsRequest getTokenClientCredentialsRequest,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.getTokenClientCredentialsConfig, requestConfig);
    Request request =
      this.buildGetTokenClientCredentialsRequest(getTokenClientCredentialsRequest, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method getTokenClientCredentials
   * POST /v4/auth/o/token
   *
   * @param getTokenClientCredentialsRequest {@link GetTokenClientCredentialsRequest} Request Body
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> getTokenClientCredentialsAsync(
    @NonNull GetTokenClientCredentialsRequest getTokenClientCredentialsRequest
  ) throws ApiError {
    return this.getTokenClientCredentialsAsync(getTokenClientCredentialsRequest, null);
  }

  /**
   * Method getTokenClientCredentials
   * POST /v4/auth/o/token
   *
   * @param getTokenClientCredentialsRequest {@link GetTokenClientCredentialsRequest} Request Body
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> getTokenClientCredentialsAsync(
    @NonNull GetTokenClientCredentialsRequest getTokenClientCredentialsRequest,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.getTokenClientCredentialsConfig, requestConfig);
    Request request =
      this.buildGetTokenClientCredentialsRequest(getTokenClientCredentialsRequest, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildGetTokenClientCredentialsRequest(
    @NonNull GetTokenClientCredentialsRequest getTokenClientCredentialsRequest,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.POST,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL),
      "v4/auth/o/token"
    )
      .setBody(
        new FormBody.Builder()
          .add("grant_type", getTokenClientCredentialsRequest.getGrantType())
          .add("client_id", getTokenClientCredentialsRequest.getClientId())
          .add("client_secret", getTokenClientCredentialsRequest.getClientSecret())
          .build()
      )
      .build();
  }

  /**
   * Method introspectToken
   * GET /v4/auth/o/introspect
   *
   * @return response of {@code Object}
   */
  public Object introspectToken() throws ApiError {
    return this.introspectToken(null);
  }

  /**
   * Method introspectToken
   * GET /v4/auth/o/introspect
   *
   * @return response of {@code Object}
   */
  public Object introspectToken(RequestConfig requestConfig) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.introspectTokenConfig, requestConfig);
    Request request = this.buildIntrospectTokenRequest(resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method introspectToken
   * GET /v4/auth/o/introspect
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> introspectTokenAsync() throws ApiError {
    return this.introspectTokenAsync(null);
  }

  /**
   * Method introspectToken
   * GET /v4/auth/o/introspect
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> introspectTokenAsync(RequestConfig requestConfig)
    throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.introspectTokenConfig, requestConfig);
    Request request = this.buildIntrospectTokenRequest(resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildIntrospectTokenRequest(RequestConfig resolvedConfig) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL),
      "v4/auth/o/introspect"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .build();
  }
}
