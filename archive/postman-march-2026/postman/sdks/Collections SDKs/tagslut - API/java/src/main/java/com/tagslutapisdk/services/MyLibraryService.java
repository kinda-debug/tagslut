package com.tagslutapisdk.services;

import com.fasterxml.jackson.core.type.TypeReference;
import com.tagslutapisdk.config.RequestConfig;
import com.tagslutapisdk.config.TagslutApiSdkConfig;
import com.tagslutapisdk.exceptions.ApiError;
import com.tagslutapisdk.http.Environment;
import com.tagslutapisdk.http.HttpMethod;
import com.tagslutapisdk.http.ModelConverter;
import com.tagslutapisdk.http.util.RequestBuilder;
import com.tagslutapisdk.models.MyBeatportTracksParameters;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import lombok.NonNull;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * MyLibraryService Service
 */
public class MyLibraryService extends BaseService {

  private RequestConfig myBeatportTracksConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL_1)
    .build();
  private RequestConfig myAccountConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL)
    .build();

  /**
   * Constructs a new instance of MyLibraryService.
   *
   * @param httpClient The HTTP client to use for requests
   * @param config The SDK configuration
   */
  public MyLibraryService(@NonNull OkHttpClient httpClient, TagslutApiSdkConfig config) {
    super(httpClient, config);
  }

  /**
   * Sets method-level configuration for {@code myBeatportTracks}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public MyLibraryService setMyBeatportTracksConfig(RequestConfig config) {
    this.myBeatportTracksConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code myAccount}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public MyLibraryService setMyAccountConfig(RequestConfig config) {
    this.myAccountConfig = config;
    return this;
  }

  /**
   * Method myBeatportTracks
   * GET /v4/my/beatport/tracks
   *
   * @return response of {@code Object}
   */
  public Object myBeatportTracks() throws ApiError {
    return this.myBeatportTracks(MyBeatportTracksParameters.builder().build());
  }

  /**
   * Method myBeatportTracks
   * GET /v4/my/beatport/tracks
   *
   * @param requestParameters {@link MyBeatportTracksParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object myBeatportTracks(@NonNull MyBeatportTracksParameters requestParameters)
    throws ApiError {
    return this.myBeatportTracks(requestParameters, null);
  }

  /**
   * Method myBeatportTracks
   * GET /v4/my/beatport/tracks
   *
   * @param requestParameters {@link MyBeatportTracksParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object myBeatportTracks(
    @NonNull MyBeatportTracksParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.myBeatportTracksConfig, requestConfig);
    Request request = this.buildMyBeatportTracksRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method myBeatportTracks
   * GET /v4/my/beatport/tracks
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> myBeatportTracksAsync() throws ApiError {
    return this.myBeatportTracksAsync(MyBeatportTracksParameters.builder().build());
  }

  /**
   * Method myBeatportTracks
   * GET /v4/my/beatport/tracks
   *
   * @param requestParameters {@link MyBeatportTracksParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> myBeatportTracksAsync(
    @NonNull MyBeatportTracksParameters requestParameters
  ) throws ApiError {
    return this.myBeatportTracksAsync(requestParameters, null);
  }

  /**
   * Method myBeatportTracks
   * GET /v4/my/beatport/tracks
   *
   * @param requestParameters {@link MyBeatportTracksParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> myBeatportTracksAsync(
    @NonNull MyBeatportTracksParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.myBeatportTracksConfig, requestConfig);
    Request request = this.buildMyBeatportTracksRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildMyBeatportTracksRequest(
    @NonNull MyBeatportTracksParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL_1),
      "v4/my/beatport/tracks"
    )
      .setOptionalQueryParameter("page", requestParameters.getPage())
      .setOptionalQueryParameter("per_page", requestParameters.getPerPage())
      .build();
  }

  /**
   * Method myAccount
   * GET /v4/my/account
   *
   * @return response of {@code Object}
   */
  public Object myAccount() throws ApiError {
    return this.myAccount(null);
  }

  /**
   * Method myAccount
   * GET /v4/my/account
   *
   * @return response of {@code Object}
   */
  public Object myAccount(RequestConfig requestConfig) throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this.myAccountConfig, requestConfig);
    Request request = this.buildMyAccountRequest(resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method myAccount
   * GET /v4/my/account
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> myAccountAsync() throws ApiError {
    return this.myAccountAsync(null);
  }

  /**
   * Method myAccount
   * GET /v4/my/account
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> myAccountAsync(RequestConfig requestConfig) throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this.myAccountConfig, requestConfig);
    Request request = this.buildMyAccountRequest(resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildMyAccountRequest(RequestConfig resolvedConfig) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL),
      "v4/my/account"
    ).build();
  }
}
