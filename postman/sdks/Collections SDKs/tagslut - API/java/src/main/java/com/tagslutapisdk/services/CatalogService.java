package com.tagslutapisdk.services;

import com.fasterxml.jackson.core.type.TypeReference;
import com.tagslutapisdk.config.RequestConfig;
import com.tagslutapisdk.config.TagslutApiSdkConfig;
import com.tagslutapisdk.exceptions.ApiError;
import com.tagslutapisdk.http.Environment;
import com.tagslutapisdk.http.HttpMethod;
import com.tagslutapisdk.http.ModelConverter;
import com.tagslutapisdk.http.util.RequestBuilder;
import com.tagslutapisdk.models.ReleaseTracksParameters;
import com.tagslutapisdk.models.TracksByIsrcQueryParamParameters;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import lombok.NonNull;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * CatalogService Service
 */
public class CatalogService extends BaseService {

  private RequestConfig trackByIdConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL)
    .build();
  private RequestConfig tracksByIsrcQueryParamConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL_1)
    .build();
  private RequestConfig isrcStoreLookupPathBasedPhase3dConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL)
    .build();
  private RequestConfig releaseByIdConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL)
    .build();
  private RequestConfig releaseTracksConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL_1)
    .build();

  /**
   * Constructs a new instance of CatalogService.
   *
   * @param httpClient The HTTP client to use for requests
   * @param config The SDK configuration
   */
  public CatalogService(@NonNull OkHttpClient httpClient, TagslutApiSdkConfig config) {
    super(httpClient, config);
  }

  /**
   * Sets method-level configuration for {@code trackById}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public CatalogService setTrackByIdConfig(RequestConfig config) {
    this.trackByIdConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code tracksByIsrcQueryParam}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public CatalogService setTracksByIsrcQueryParamConfig(RequestConfig config) {
    this.tracksByIsrcQueryParamConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code isrcStoreLookupPathBasedPhase3d}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public CatalogService setIsrcStoreLookupPathBasedPhase3dConfig(RequestConfig config) {
    this.isrcStoreLookupPathBasedPhase3dConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code releaseById}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public CatalogService setReleaseByIdConfig(RequestConfig config) {
    this.releaseByIdConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code releaseTracks}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public CatalogService setReleaseTracksConfig(RequestConfig config) {
    this.releaseTracksConfig = config;
    return this;
  }

  /**
   * Method trackById
   * GET /v4/catalog/tracks/{beatport_test_track_id}
   *
   * @param beatportTestTrackId String
   * @return response of {@code Object}
   */
  public Object trackById(@NonNull String beatportTestTrackId) throws ApiError {
    return this.trackById(beatportTestTrackId, null);
  }

  /**
   * Method trackById
   * GET /v4/catalog/tracks/{beatport_test_track_id}
   *
   * @param beatportTestTrackId String
   * @return response of {@code Object}
   */
  public Object trackById(@NonNull String beatportTestTrackId, RequestConfig requestConfig)
    throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this.trackByIdConfig, requestConfig);
    Request request = this.buildTrackByIdRequest(beatportTestTrackId, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method trackById
   * GET /v4/catalog/tracks/{beatport_test_track_id}
   *
   * @param beatportTestTrackId String
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> trackByIdAsync(@NonNull String beatportTestTrackId)
    throws ApiError {
    return this.trackByIdAsync(beatportTestTrackId, null);
  }

  /**
   * Method trackById
   * GET /v4/catalog/tracks/{beatport_test_track_id}
   *
   * @param beatportTestTrackId String
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> trackByIdAsync(
    @NonNull String beatportTestTrackId,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this.trackByIdConfig, requestConfig);
    Request request = this.buildTrackByIdRequest(beatportTestTrackId, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildTrackByIdRequest(
    @NonNull String beatportTestTrackId,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL),
      "v4/catalog/tracks/{beatport_test_track_id}"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setPathParameter("beatport_test_track_id", beatportTestTrackId)
      .build();
  }

  /**
   * Method tracksByIsrcQueryParam
   * GET /v4/catalog/tracks
   *
   * @return response of {@code Object}
   */
  public Object tracksByIsrcQueryParam() throws ApiError {
    return this.tracksByIsrcQueryParam(TracksByIsrcQueryParamParameters.builder().build());
  }

  /**
   * Method tracksByIsrcQueryParam
   * GET /v4/catalog/tracks
   *
   * @param requestParameters {@link TracksByIsrcQueryParamParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object tracksByIsrcQueryParam(@NonNull TracksByIsrcQueryParamParameters requestParameters)
    throws ApiError {
    return this.tracksByIsrcQueryParam(requestParameters, null);
  }

  /**
   * Method tracksByIsrcQueryParam
   * GET /v4/catalog/tracks
   *
   * @param requestParameters {@link TracksByIsrcQueryParamParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object tracksByIsrcQueryParam(
    @NonNull TracksByIsrcQueryParamParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.tracksByIsrcQueryParamConfig, requestConfig);
    Request request = this.buildTracksByIsrcQueryParamRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method tracksByIsrcQueryParam
   * GET /v4/catalog/tracks
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> tracksByIsrcQueryParamAsync() throws ApiError {
    return this.tracksByIsrcQueryParamAsync(TracksByIsrcQueryParamParameters.builder().build());
  }

  /**
   * Method tracksByIsrcQueryParam
   * GET /v4/catalog/tracks
   *
   * @param requestParameters {@link TracksByIsrcQueryParamParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> tracksByIsrcQueryParamAsync(
    @NonNull TracksByIsrcQueryParamParameters requestParameters
  ) throws ApiError {
    return this.tracksByIsrcQueryParamAsync(requestParameters, null);
  }

  /**
   * Method tracksByIsrcQueryParam
   * GET /v4/catalog/tracks
   *
   * @param requestParameters {@link TracksByIsrcQueryParamParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> tracksByIsrcQueryParamAsync(
    @NonNull TracksByIsrcQueryParamParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.tracksByIsrcQueryParamConfig, requestConfig);
    Request request = this.buildTracksByIsrcQueryParamRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildTracksByIsrcQueryParamRequest(
    @NonNull TracksByIsrcQueryParamParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL_1),
      "v4/catalog/tracks"
    )
      .setOptionalQueryParameter("isrc", requestParameters.getIsrc())
      .build();
  }

  /**
   * Method isrcStoreLookupPathBasedPhase3d
   * GET /v4/catalog/tracks/store/{beatport_test_isrc}
   *
   * @param beatportTestIsrc String
   * @return response of {@code Object}
   */
  public Object isrcStoreLookupPathBasedPhase3d(@NonNull String beatportTestIsrc) throws ApiError {
    return this.isrcStoreLookupPathBasedPhase3d(beatportTestIsrc, null);
  }

  /**
   * Method isrcStoreLookupPathBasedPhase3d
   * GET /v4/catalog/tracks/store/{beatport_test_isrc}
   *
   * @param beatportTestIsrc String
   * @return response of {@code Object}
   */
  public Object isrcStoreLookupPathBasedPhase3d(
    @NonNull String beatportTestIsrc,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.isrcStoreLookupPathBasedPhase3dConfig, requestConfig);
    Request request =
      this.buildIsrcStoreLookupPathBasedPhase3dRequest(beatportTestIsrc, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method isrcStoreLookupPathBasedPhase3d
   * GET /v4/catalog/tracks/store/{beatport_test_isrc}
   *
   * @param beatportTestIsrc String
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> isrcStoreLookupPathBasedPhase3dAsync(
    @NonNull String beatportTestIsrc
  ) throws ApiError {
    return this.isrcStoreLookupPathBasedPhase3dAsync(beatportTestIsrc, null);
  }

  /**
   * Method isrcStoreLookupPathBasedPhase3d
   * GET /v4/catalog/tracks/store/{beatport_test_isrc}
   *
   * @param beatportTestIsrc String
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> isrcStoreLookupPathBasedPhase3dAsync(
    @NonNull String beatportTestIsrc,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.isrcStoreLookupPathBasedPhase3dConfig, requestConfig);
    Request request =
      this.buildIsrcStoreLookupPathBasedPhase3dRequest(beatportTestIsrc, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildIsrcStoreLookupPathBasedPhase3dRequest(
    @NonNull String beatportTestIsrc,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL),
      "v4/catalog/tracks/store/{beatport_test_isrc}"
    )
      .setBasicAuth(resolveBasicAuthConfig(resolvedConfig))
      .setPathParameter("beatport_test_isrc", beatportTestIsrc)
      .build();
  }

  /**
   * Method releaseById
   * GET /v4/catalog/releases/{beatport_test_release_id}
   *
   * @param beatportTestReleaseId String
   * @return response of {@code Object}
   */
  public Object releaseById(@NonNull String beatportTestReleaseId) throws ApiError {
    return this.releaseById(beatportTestReleaseId, null);
  }

  /**
   * Method releaseById
   * GET /v4/catalog/releases/{beatport_test_release_id}
   *
   * @param beatportTestReleaseId String
   * @return response of {@code Object}
   */
  public Object releaseById(@NonNull String beatportTestReleaseId, RequestConfig requestConfig)
    throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this.releaseByIdConfig, requestConfig);
    Request request = this.buildReleaseByIdRequest(beatportTestReleaseId, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method releaseById
   * GET /v4/catalog/releases/{beatport_test_release_id}
   *
   * @param beatportTestReleaseId String
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> releaseByIdAsync(@NonNull String beatportTestReleaseId)
    throws ApiError {
    return this.releaseByIdAsync(beatportTestReleaseId, null);
  }

  /**
   * Method releaseById
   * GET /v4/catalog/releases/{beatport_test_release_id}
   *
   * @param beatportTestReleaseId String
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> releaseByIdAsync(
    @NonNull String beatportTestReleaseId,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this.releaseByIdConfig, requestConfig);
    Request request = this.buildReleaseByIdRequest(beatportTestReleaseId, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildReleaseByIdRequest(
    @NonNull String beatportTestReleaseId,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL),
      "v4/catalog/releases/{beatport_test_release_id}"
    )
      .setPathParameter("beatport_test_release_id", beatportTestReleaseId)
      .build();
  }

  /**
   * Method releaseTracks
   * GET /v4/catalog/releases/{beatport_test_release_id}/tracks
   *
   * @param beatportTestReleaseId String
   * @param requestParameters {@link ReleaseTracksParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object releaseTracks(
    @NonNull String beatportTestReleaseId,
    @NonNull ReleaseTracksParameters requestParameters
  ) throws ApiError {
    return this.releaseTracks(beatportTestReleaseId, requestParameters, null);
  }

  /**
   * Method releaseTracks
   * GET /v4/catalog/releases/{beatport_test_release_id}/tracks
   *
   * @param beatportTestReleaseId String
   * @param requestParameters {@link ReleaseTracksParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object releaseTracks(
    @NonNull String beatportTestReleaseId,
    @NonNull ReleaseTracksParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this.releaseTracksConfig, requestConfig);
    Request request =
      this.buildReleaseTracksRequest(beatportTestReleaseId, requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method releaseTracks
   * GET /v4/catalog/releases/{beatport_test_release_id}/tracks
   *
   * @param beatportTestReleaseId String
   * @param requestParameters {@link ReleaseTracksParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> releaseTracksAsync(
    @NonNull String beatportTestReleaseId,
    @NonNull ReleaseTracksParameters requestParameters
  ) throws ApiError {
    return this.releaseTracksAsync(beatportTestReleaseId, requestParameters, null);
  }

  /**
   * Method releaseTracks
   * GET /v4/catalog/releases/{beatport_test_release_id}/tracks
   *
   * @param beatportTestReleaseId String
   * @param requestParameters {@link ReleaseTracksParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> releaseTracksAsync(
    @NonNull String beatportTestReleaseId,
    @NonNull ReleaseTracksParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this.releaseTracksConfig, requestConfig);
    Request request =
      this.buildReleaseTracksRequest(beatportTestReleaseId, requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request buildReleaseTracksRequest(
    @NonNull String beatportTestReleaseId,
    @NonNull ReleaseTracksParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.BASE_URL_1),
      "v4/catalog/releases/{beatport_test_release_id}/tracks"
    )
      .setPathParameter("beatport_test_release_id", beatportTestReleaseId)
      .setOptionalQueryParameter("per_page", requestParameters.getPerPage())
      .build();
  }
}
