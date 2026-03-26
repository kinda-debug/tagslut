package com.tagslutapisdk.services;

import com.fasterxml.jackson.core.type.TypeReference;
import com.tagslutapisdk.config.RequestConfig;
import com.tagslutapisdk.config.TagslutApiSdkConfig;
import com.tagslutapisdk.exceptions.ApiError;
import com.tagslutapisdk.http.Environment;
import com.tagslutapisdk.http.HttpMethod;
import com.tagslutapisdk.http.ModelConverter;
import com.tagslutapisdk.http.util.RequestBuilder;
import com.tagslutapisdk.models._6aResolveTidalAlbumToIsrcParameters;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import lombok.NonNull;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * ValidationRunService Service
 */
public class ValidationRunService extends BaseService {

  private RequestConfig _6aResolveTidalAlbumToIsrcConfig = RequestConfig.builder()
    .environment(Environment.API)
    .build();
  private RequestConfig _6bTrackByIdValidationConfig = RequestConfig.builder()
    .environment(Environment.BASE_URL)
    .build();
  private RequestConfig _6cRunNotesConfig = RequestConfig.builder()
    .environment(Environment.EXAMPLE)
    .build();

  /**
   * Constructs a new instance of ValidationRunService.
   *
   * @param httpClient The HTTP client to use for requests
   * @param config The SDK configuration
   */
  public ValidationRunService(@NonNull OkHttpClient httpClient, TagslutApiSdkConfig config) {
    super(httpClient, config);
  }

  /**
   * Sets method-level configuration for {@code _6aResolveTidalAlbumToIsrc}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public ValidationRunService set_6aResolveTidalAlbumToIsrcConfig(RequestConfig config) {
    this._6aResolveTidalAlbumToIsrcConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code _6bTrackByIdValidation}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public ValidationRunService set_6bTrackByIdValidationConfig(RequestConfig config) {
    this._6bTrackByIdValidationConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code _6cRunNotes}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public ValidationRunService set_6cRunNotesConfig(RequestConfig config) {
    this._6cRunNotesConfig = config;
    return this;
  }

  /**
   * Method _6aResolveTidalAlbumToIsrc
   * GET /v1/albums/507881809/tracks
   *
   * @return response of {@code Object}
   */
  public Object _6aResolveTidalAlbumToIsrc() throws ApiError {
    return this._6aResolveTidalAlbumToIsrc(_6aResolveTidalAlbumToIsrcParameters.builder().build());
  }

  /**
   * Method _6aResolveTidalAlbumToIsrc
   * GET /v1/albums/507881809/tracks
   *
   * @param requestParameters {@link _6aResolveTidalAlbumToIsrcParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object _6aResolveTidalAlbumToIsrc(
    @NonNull _6aResolveTidalAlbumToIsrcParameters requestParameters
  ) throws ApiError {
    return this._6aResolveTidalAlbumToIsrc(requestParameters, null);
  }

  /**
   * Method _6aResolveTidalAlbumToIsrc
   * GET /v1/albums/507881809/tracks
   *
   * @param requestParameters {@link _6aResolveTidalAlbumToIsrcParameters} Request Parameters Object
   * @return response of {@code Object}
   */
  public Object _6aResolveTidalAlbumToIsrc(
    @NonNull _6aResolveTidalAlbumToIsrcParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._6aResolveTidalAlbumToIsrcConfig, requestConfig);
    Request request =
      this.build_6aResolveTidalAlbumToIsrcRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method _6aResolveTidalAlbumToIsrc
   * GET /v1/albums/507881809/tracks
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _6aResolveTidalAlbumToIsrcAsync() throws ApiError {
    return this._6aResolveTidalAlbumToIsrcAsync(
        _6aResolveTidalAlbumToIsrcParameters.builder().build()
      );
  }

  /**
   * Method _6aResolveTidalAlbumToIsrc
   * GET /v1/albums/507881809/tracks
   *
   * @param requestParameters {@link _6aResolveTidalAlbumToIsrcParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _6aResolveTidalAlbumToIsrcAsync(
    @NonNull _6aResolveTidalAlbumToIsrcParameters requestParameters
  ) throws ApiError {
    return this._6aResolveTidalAlbumToIsrcAsync(requestParameters, null);
  }

  /**
   * Method _6aResolveTidalAlbumToIsrc
   * GET /v1/albums/507881809/tracks
   *
   * @param requestParameters {@link _6aResolveTidalAlbumToIsrcParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _6aResolveTidalAlbumToIsrcAsync(
    @NonNull _6aResolveTidalAlbumToIsrcParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._6aResolveTidalAlbumToIsrcConfig, requestConfig);
    Request request =
      this.build_6aResolveTidalAlbumToIsrcRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request build_6aResolveTidalAlbumToIsrcRequest(
    @NonNull _6aResolveTidalAlbumToIsrcParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.API),
      "v1/albums/507881809/tracks"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setOptionalQueryParameter("countryCode", requestParameters.getCountryCode())
      .build();
  }

  /**
   * Method _6bTrackByIdValidation
   * GET /v4/catalog/tracks/{beatport_test_track_id}
   *
   * @param beatportTestTrackId String
   * @return response of {@code Object}
   */
  public Object _6bTrackByIdValidation(@NonNull String beatportTestTrackId) throws ApiError {
    return this._6bTrackByIdValidation(beatportTestTrackId, null);
  }

  /**
   * Method _6bTrackByIdValidation
   * GET /v4/catalog/tracks/{beatport_test_track_id}
   *
   * @param beatportTestTrackId String
   * @return response of {@code Object}
   */
  public Object _6bTrackByIdValidation(
    @NonNull String beatportTestTrackId,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._6bTrackByIdValidationConfig, requestConfig);
    Request request = this.build_6bTrackByIdValidationRequest(beatportTestTrackId, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method _6bTrackByIdValidation
   * GET /v4/catalog/tracks/{beatport_test_track_id}
   *
   * @param beatportTestTrackId String
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _6bTrackByIdValidationAsync(@NonNull String beatportTestTrackId)
    throws ApiError {
    return this._6bTrackByIdValidationAsync(beatportTestTrackId, null);
  }

  /**
   * Method _6bTrackByIdValidation
   * GET /v4/catalog/tracks/{beatport_test_track_id}
   *
   * @param beatportTestTrackId String
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _6bTrackByIdValidationAsync(
    @NonNull String beatportTestTrackId,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this._6bTrackByIdValidationConfig, requestConfig);
    Request request = this.build_6bTrackByIdValidationRequest(beatportTestTrackId, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request build_6bTrackByIdValidationRequest(
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
   * Method _6cRunNotes
   * GET /
   *
   * @return response of {@code Object}
   */
  public Object _6cRunNotes() throws ApiError {
    return this._6cRunNotes(null);
  }

  /**
   * Method _6cRunNotes
   * GET /
   *
   * @return response of {@code Object}
   */
  public Object _6cRunNotes(RequestConfig requestConfig) throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this._6cRunNotesConfig, requestConfig);
    Request request = this.build_6cRunNotesRequest(resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
  }

  /**
   * Method _6cRunNotes
   * GET /
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _6cRunNotesAsync() throws ApiError {
    return this._6cRunNotesAsync(null);
  }

  /**
   * Method _6cRunNotes
   * GET /
   *
   * @return response of {@code CompletableFuture<Object>}
   */
  public CompletableFuture<Object> _6cRunNotesAsync(RequestConfig requestConfig) throws ApiError {
    RequestConfig resolvedConfig = this.getResolvedConfig(this._6cRunNotesConfig, requestConfig);
    Request request = this.build_6cRunNotesRequest(resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<Object>() {});
    });
  }

  private Request build_6cRunNotesRequest(RequestConfig resolvedConfig) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.EXAMPLE),
      ""
    ).build();
  }
}
