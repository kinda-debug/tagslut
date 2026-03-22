package com.tagslutapisdk.services;

import com.fasterxml.jackson.core.type.TypeReference;
import com.tagslutapisdk.config.RequestConfig;
import com.tagslutapisdk.config.TagslutApiSdkConfig;
import com.tagslutapisdk.exceptions.ApiError;
import com.tagslutapisdk.http.Environment;
import com.tagslutapisdk.http.HttpMethod;
import com.tagslutapisdk.http.ModelConverter;
import com.tagslutapisdk.http.util.RequestBuilder;
import com.tagslutapisdk.models.SearchTracksByTextParameters;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import lombok.NonNull;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * SearchService Service
 */
public class SearchService extends BaseService {

  private RequestConfig searchTracksByTextConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL_1)
    .build();

  /**
   * Constructs a new instance of SearchService.
   *
   * @param httpClient The HTTP client to use for requests
   * @param config The SDK configuration
   */
  public SearchService(@NonNull OkHttpClient httpClient, TagslutApiSdkConfig config) {
    super(httpClient, config);
  }

  /**
   * Sets method-level configuration for {@code searchTracksByText}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public SearchService setSearchTracksByTextConfig(RequestConfig config) {
    this.searchTracksByTextConfig = config;
    return this;
  }

  /**
   * Method searchTracksByText
   * GET /search/v1/tracks
   *
   * @return response of {@code Object}
   */
  public Object searchTracksByText() throws ApiError {
    return this.searchTracksByText(SearchTracksByTextParameters.builder().build());
  }

  /**
   * Method searchTracksByText
   * GET /search/v1/tracks
   *
   * @param requestParameters {@link SearchTracksByTextParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object searchTracksByText(@NonNull SearchTracksByTextParameters requestParameters)
    throws ApiError {
    return this.searchTracksByText(requestParameters, null);
  }

  /**
   * Method searchTracksByText
   * GET /search/v1/tracks
   *
   * @param requestParameters {@link SearchTracksByTextParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object searchTracksByText(
    @NonNull SearchTracksByTextParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.searchTracksByTextConfig, requestConfig);
    Request request = this.buildSearchTracksByTextRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method searchTracksByText
   * GET /search/v1/tracks
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> searchTracksByTextAsync() throws ApiError {
    return this.searchTracksByTextAsync(SearchTracksByTextParameters.builder().build());
  }

  /**
   * Method searchTracksByText
   * GET /search/v1/tracks
   *
   * @param requestParameters {@link SearchTracksByTextParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> searchTracksByTextAsync(
    @NonNull SearchTracksByTextParameters requestParameters
  ) throws ApiError {
    return this.searchTracksByTextAsync(requestParameters, null);
  }

  /**
   * Method searchTracksByText
   * GET /search/v1/tracks
   *
   * @param requestParameters {@link SearchTracksByTextParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> searchTracksByTextAsync(
    @NonNull SearchTracksByTextParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.searchTracksByTextConfig, requestConfig);
    Request request = this.buildSearchTracksByTextRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildSearchTracksByTextRequest(
    @NonNull SearchTracksByTextParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL_1),
      "search/v1/tracks"
    )
      .setOptionalQueryParameter("q", requestParameters.getQ())
      .setOptionalQueryParameter("count", requestParameters.getCount())
      .build();
  }
}
