package com.tagslutapisdk.services;

import com.fasterxml.jackson.core.type.TypeReference;
import com.tagslutapisdk.config.RequestConfig;
import com.tagslutapisdk.config.TagslutApiSdkConfig;
import com.tagslutapisdk.exceptions.ApiError;
import com.tagslutapisdk.http.Environment;
import com.tagslutapisdk.http.HttpMethod;
import com.tagslutapisdk.http.ModelConverter;
import com.tagslutapisdk.http.util.RequestBuilder;
import com.tagslutapisdk.models._5aBeatportIsrcLookupParameters;
import com.tagslutapisdk.models._5bTidalIsrcCrossCheckParameters;
import com.tagslutapisdk.models._5cSpotifyIsrcCrossCheckParameters;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import lombok.NonNull;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * IdentityVerificationService Service
 */
public class IdentityVerificationService extends BaseService {

  private RequestConfig _5aBeatportIsrcLookupConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL_1)
    .build();
  private RequestConfig _5bTidalIsrcCrossCheckConfig = RequestConfig.builder()
    .environment(Environment.API)
    .build();
  private RequestConfig _5cSpotifyIsrcCrossCheckConfig = RequestConfig.builder()
    .environment(Environment.API_1)
    .build();

  /**
   * Constructs a new instance of IdentityVerificationService.
   *
   * @param httpClient The HTTP client to use for requests
   * @param config The SDK configuration
   */
  public IdentityVerificationService(@NonNull OkHttpClient httpClient, TagslutApiSdkConfig config) {
    super(httpClient, config);
  }

  /**
   * Sets method-level configuration for {@code _5aBeatportIsrcLookup}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public IdentityVerificationService set_5aBeatportIsrcLookupConfig(RequestConfig config) {
    this._5aBeatportIsrcLookupConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code _5bTidalIsrcCrossCheck}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public IdentityVerificationService set_5bTidalIsrcCrossCheckConfig(RequestConfig config) {
    this._5bTidalIsrcCrossCheckConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code _5cSpotifyIsrcCrossCheck}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public IdentityVerificationService set_5cSpotifyIsrcCrossCheckConfig(RequestConfig config) {
    this._5cSpotifyIsrcCrossCheckConfig = config;
    return this;
  }

  /**
   * Method _5aBeatportIsrcLookup
   * GET /v4/catalog/tracks
   *
   * @return response of {@code Object}
   */
  public Object _5aBeatportIsrcLookup() throws ApiError {
    return this._5aBeatportIsrcLookup(_5aBeatportIsrcLookupParameters.builder().build());
  }

  /**
   * Method _5aBeatportIsrcLookup
   * GET /v4/catalog/tracks
   *
   * @param requestParameters {@link _5aBeatportIsrcLookupParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object _5aBeatportIsrcLookup(@NonNull _5aBeatportIsrcLookupParameters requestParameters)
    throws ApiError {
    return this._5aBeatportIsrcLookup(requestParameters, null);
  }

  /**
   * Method _5aBeatportIsrcLookup
   * GET /v4/catalog/tracks
   *
   * @param requestParameters {@link _5aBeatportIsrcLookupParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object _5aBeatportIsrcLookup(
    @NonNull _5aBeatportIsrcLookupParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._5aBeatportIsrcLookupConfig, requestConfig);
    Request request = this.build_5aBeatportIsrcLookupRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method _5aBeatportIsrcLookup
   * GET /v4/catalog/tracks
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _5aBeatportIsrcLookupAsync() throws ApiError {
    return this._5aBeatportIsrcLookupAsync(_5aBeatportIsrcLookupParameters.builder().build());
  }

  /**
   * Method _5aBeatportIsrcLookup
   * GET /v4/catalog/tracks
   *
   * @param requestParameters {@link _5aBeatportIsrcLookupParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _5aBeatportIsrcLookupAsync(
    @NonNull _5aBeatportIsrcLookupParameters requestParameters
  ) throws ApiError {
    return this._5aBeatportIsrcLookupAsync(requestParameters, null);
  }

  /**
   * Method _5aBeatportIsrcLookup
   * GET /v4/catalog/tracks
   *
   * @param requestParameters {@link _5aBeatportIsrcLookupParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _5aBeatportIsrcLookupAsync(
    @NonNull _5aBeatportIsrcLookupParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._5aBeatportIsrcLookupConfig, requestConfig);
    Request request = this.build_5aBeatportIsrcLookupRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request build_5aBeatportIsrcLookupRequest(
    @NonNull _5aBeatportIsrcLookupParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL_1),
      "v4/catalog/tracks"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setOptionalQueryParameter("isrc", requestParameters.getIsrc())
      .build();
  }

  /**
   * Method _5bTidalIsrcCrossCheck
   * GET /v1/tracks
   *
   * @return response of {@code Object}
   */
  public Object _5bTidalIsrcCrossCheck() throws ApiError {
    return this._5bTidalIsrcCrossCheck(_5bTidalIsrcCrossCheckParameters.builder().build());
  }

  /**
   * Method _5bTidalIsrcCrossCheck
   * GET /v1/tracks
   *
   * @param requestParameters {@link _5bTidalIsrcCrossCheckParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object _5bTidalIsrcCrossCheck(@NonNull _5bTidalIsrcCrossCheckParameters requestParameters)
    throws ApiError {
    return this._5bTidalIsrcCrossCheck(requestParameters, null);
  }

  /**
   * Method _5bTidalIsrcCrossCheck
   * GET /v1/tracks
   *
   * @param requestParameters {@link _5bTidalIsrcCrossCheckParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object _5bTidalIsrcCrossCheck(
    @NonNull _5bTidalIsrcCrossCheckParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._5bTidalIsrcCrossCheckConfig, requestConfig);
    Request request = this.build_5bTidalIsrcCrossCheckRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method _5bTidalIsrcCrossCheck
   * GET /v1/tracks
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _5bTidalIsrcCrossCheckAsync() throws ApiError {
    return this._5bTidalIsrcCrossCheckAsync(_5bTidalIsrcCrossCheckParameters.builder().build());
  }

  /**
   * Method _5bTidalIsrcCrossCheck
   * GET /v1/tracks
   *
   * @param requestParameters {@link _5bTidalIsrcCrossCheckParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _5bTidalIsrcCrossCheckAsync(
    @NonNull _5bTidalIsrcCrossCheckParameters requestParameters
  ) throws ApiError {
    return this._5bTidalIsrcCrossCheckAsync(requestParameters, null);
  }

  /**
   * Method _5bTidalIsrcCrossCheck
   * GET /v1/tracks
   *
   * @param requestParameters {@link _5bTidalIsrcCrossCheckParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _5bTidalIsrcCrossCheckAsync(
    @NonNull _5bTidalIsrcCrossCheckParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._5bTidalIsrcCrossCheckConfig, requestConfig);
    Request request = this.build_5bTidalIsrcCrossCheckRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request build_5bTidalIsrcCrossCheckRequest(
    @NonNull _5bTidalIsrcCrossCheckParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.API),
      "v1/tracks"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setOptionalQueryParameter("isrc", requestParameters.getIsrc())
      .setOptionalQueryParameter("countryCode", requestParameters.getCountryCode())
      .build();
  }

  /**
   * Method _5cSpotifyIsrcCrossCheck
   * GET /v1/search
   *
   * @return response of {@code Object}
   */
  public Object _5cSpotifyIsrcCrossCheck() throws ApiError {
    return this._5cSpotifyIsrcCrossCheck(_5cSpotifyIsrcCrossCheckParameters.builder().build());
  }

  /**
   * Method _5cSpotifyIsrcCrossCheck
   * GET /v1/search
   *
   * @param requestParameters {@link _5cSpotifyIsrcCrossCheckParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object _5cSpotifyIsrcCrossCheck(
    @NonNull _5cSpotifyIsrcCrossCheckParameters requestParameters
  ) throws ApiError {
    return this._5cSpotifyIsrcCrossCheck(requestParameters, null);
  }

  /**
   * Method _5cSpotifyIsrcCrossCheck
   * GET /v1/search
   *
   * @param requestParameters {@link _5cSpotifyIsrcCrossCheckParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object _5cSpotifyIsrcCrossCheck(
    @NonNull _5cSpotifyIsrcCrossCheckParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._5cSpotifyIsrcCrossCheckConfig, requestConfig);
    Request request = this.build_5cSpotifyIsrcCrossCheckRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method _5cSpotifyIsrcCrossCheck
   * GET /v1/search
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _5cSpotifyIsrcCrossCheckAsync() throws ApiError {
    return this._5cSpotifyIsrcCrossCheckAsync(_5cSpotifyIsrcCrossCheckParameters.builder().build());
  }

  /**
   * Method _5cSpotifyIsrcCrossCheck
   * GET /v1/search
   *
   * @param requestParameters {@link _5cSpotifyIsrcCrossCheckParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _5cSpotifyIsrcCrossCheckAsync(
    @NonNull _5cSpotifyIsrcCrossCheckParameters requestParameters
  ) throws ApiError {
    return this._5cSpotifyIsrcCrossCheckAsync(requestParameters, null);
  }

  /**
   * Method _5cSpotifyIsrcCrossCheck
   * GET /v1/search
   *
   * @param requestParameters {@link _5cSpotifyIsrcCrossCheckParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _5cSpotifyIsrcCrossCheckAsync(
    @NonNull _5cSpotifyIsrcCrossCheckParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._5cSpotifyIsrcCrossCheckConfig, requestConfig);
    Request request = this.build_5cSpotifyIsrcCrossCheckRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request build_5cSpotifyIsrcCrossCheckRequest(
    @NonNull _5cSpotifyIsrcCrossCheckParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.API_1),
      "v1/search"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setOptionalQueryParameter("q", requestParameters.getQ())
      .setOptionalQueryParameter("type", requestParameters.getType())
      .build();
  }
}
