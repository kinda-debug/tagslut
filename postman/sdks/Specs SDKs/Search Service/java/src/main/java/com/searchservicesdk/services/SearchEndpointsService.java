package com.searchservicesdk.services;

import com.fasterxml.jackson.core.type.TypeReference;
import com.searchservicesdk.config.RequestConfig;
import com.searchservicesdk.config.SearchServiceSdkConfig;
import com.searchservicesdk.exceptions.ApiError;
import com.searchservicesdk.exceptions.HttpValidationErrorException;
import com.searchservicesdk.http.Environment;
import com.searchservicesdk.http.HttpMethod;
import com.searchservicesdk.http.ModelConverter;
import com.searchservicesdk.http.util.RequestBuilder;
import com.searchservicesdk.models.AllSearchSearchV1AllGetParameters;
import com.searchservicesdk.models.ArtistsResponse;
import com.searchservicesdk.models.ArtistsSearchSearchV1ArtistsGetParameters;
import com.searchservicesdk.models.ChartsResponse;
import com.searchservicesdk.models.ChartsSearchSearchV1ChartsGetParameters;
import com.searchservicesdk.models.HttpValidationError;
import com.searchservicesdk.models.LabelsResponse;
import com.searchservicesdk.models.LabelsSearchSearchV1LabelsGetParameters;
import com.searchservicesdk.models.MultisearchResponse;
import com.searchservicesdk.models.ReleasesResponse;
import com.searchservicesdk.models.ReleasesSearchSearchV1ReleasesGetParameters;
import com.searchservicesdk.models.TracksResponse;
import com.searchservicesdk.models.TracksSearchSearchV1TracksGetParameters;
import com.searchservicesdk.validation.ViolationAggregator;
import com.searchservicesdk.validation.exceptions.ValidationException;
import com.searchservicesdk.validation.validators.modelValidators.ReleasesSearchSearchV1ReleasesGetParametersValidator;
import com.searchservicesdk.validation.validators.modelValidators.TracksSearchSearchV1TracksGetParametersValidator;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import lombok.NonNull;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/**
 * SearchEndpointsService Service
 */
public class SearchEndpointsService extends BaseService {

  private RequestConfig tracksSearchSearchV1TracksGetConfig;
  private RequestConfig releasesSearchSearchV1ReleasesGetConfig;
  private RequestConfig artistsSearchSearchV1ArtistsGetConfig;
  private RequestConfig labelsSearchSearchV1LabelsGetConfig;
  private RequestConfig chartsSearchSearchV1ChartsGetConfig;
  private RequestConfig allSearchSearchV1AllGetConfig;

  /**
   * Constructs a new instance of SearchEndpointsService.
   *
   * @param httpClient The HTTP client to use for requests
   * @param config The SDK configuration
   */
  public SearchEndpointsService(@NonNull OkHttpClient httpClient, SearchServiceSdkConfig config) {
    super(httpClient, config);
  }

  /**
   * Sets method-level configuration for {@code tracksSearchSearchV1TracksGet}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public SearchEndpointsService setTracksSearchSearchV1TracksGetConfig(RequestConfig config) {
    this.tracksSearchSearchV1TracksGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code releasesSearchSearchV1ReleasesGet}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public SearchEndpointsService setReleasesSearchSearchV1ReleasesGetConfig(RequestConfig config) {
    this.releasesSearchSearchV1ReleasesGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code artistsSearchSearchV1ArtistsGet}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public SearchEndpointsService setArtistsSearchSearchV1ArtistsGetConfig(RequestConfig config) {
    this.artistsSearchSearchV1ArtistsGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code labelsSearchSearchV1LabelsGet}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public SearchEndpointsService setLabelsSearchSearchV1LabelsGetConfig(RequestConfig config) {
    this.labelsSearchSearchV1LabelsGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code chartsSearchSearchV1ChartsGet}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public SearchEndpointsService setChartsSearchSearchV1ChartsGetConfig(RequestConfig config) {
    this.chartsSearchSearchV1ChartsGetConfig = config;
    return this;
  }

  /**
   * Sets method-level configuration for {@code allSearchSearchV1AllGet}.
   * Method-level overrides take precedence over service-level configuration but are
   * overridden by request-level configurations.
   *
   * @param config The configuration overrides to apply at the method level
   * @return This service instance for method chaining
   */
  public SearchEndpointsService setAllSearchSearchV1AllGetConfig(RequestConfig config) {
    this.allSearchSearchV1AllGetConfig = config;
    return this;
  }

  /**
   * Tracks-Search
   *
   * @param requestParameters {@link TracksSearchSearchV1TracksGetParameters} Request Parameters Object
   * @return response of {@code TracksResponse}
   */
  public TracksResponse tracksSearchSearchV1TracksGet(
    @NonNull TracksSearchSearchV1TracksGetParameters requestParameters
  ) throws ApiError, ValidationException {
    return this.tracksSearchSearchV1TracksGet(requestParameters, null);
  }

  /**
   * Tracks-Search
   *
   * @param requestParameters {@link TracksSearchSearchV1TracksGetParameters} Request Parameters Object
   * @return response of {@code TracksResponse}
   */
  public TracksResponse tracksSearchSearchV1TracksGet(
    @NonNull TracksSearchSearchV1TracksGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError, ValidationException {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.tracksSearchSearchV1TracksGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildTracksSearchSearchV1TracksGetRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<TracksResponse>() {});
  }

  /**
   * Tracks-Search
   *
   * @param requestParameters {@link TracksSearchSearchV1TracksGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<TracksResponse>}
   */
  public CompletableFuture<TracksResponse> tracksSearchSearchV1TracksGetAsync(
    @NonNull TracksSearchSearchV1TracksGetParameters requestParameters
  ) throws ApiError, ValidationException {
    return this.tracksSearchSearchV1TracksGetAsync(requestParameters, null);
  }

  /**
   * Tracks-Search
   *
   * @param requestParameters {@link TracksSearchSearchV1TracksGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<TracksResponse>}
   */
  public CompletableFuture<TracksResponse> tracksSearchSearchV1TracksGetAsync(
    @NonNull TracksSearchSearchV1TracksGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError, ValidationException {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.tracksSearchSearchV1TracksGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildTracksSearchSearchV1TracksGetRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<TracksResponse>() {});
    });
  }

  private Request buildTracksSearchSearchV1TracksGetRequest(
    @NonNull TracksSearchSearchV1TracksGetParameters requestParameters,
    RequestConfig resolvedConfig
  ) throws ValidationException {
    new ViolationAggregator()
      .add(
        new TracksSearchSearchV1TracksGetParametersValidator("requestParameters")
          .required()
          .validate(requestParameters)
      )
      .validateAll();
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.DEFAULT),
      "search/v1/tracks"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setQueryParameter("q", requestParameters.getQ())
      .setOptionalQueryParameter("count", requestParameters.getCount())
      .setOptionalQueryParameter("preorder", requestParameters.getPreorder())
      .setOptionalQueryParameter("from_publish_date", requestParameters.getFromPublishDate())
      .setOptionalQueryParameter("to_publish_date", requestParameters.getToPublishDate())
      .setOptionalQueryParameter("from_release_date", requestParameters.getFromReleaseDate())
      .setOptionalQueryParameter("to_release_date", requestParameters.getToReleaseDate())
      .setOptionalQueryParameter("genre_id", requestParameters.getGenreId())
      .setOptionalQueryParameter("genre_name", requestParameters.getGenreName())
      .setOptionalQueryParameter("mix_name", requestParameters.getMixName())
      .setOptionalQueryParameter("from_bpm", requestParameters.getFromBpm())
      .setOptionalQueryParameter("to_bpm", requestParameters.getToBpm())
      .setOptionalQueryParameter("key_name", requestParameters.getKeyName())
      .setOptionalQueryParameter("mix_name_weight", requestParameters.getMixNameWeight())
      .setOptionalQueryParameter("label_name_weight", requestParameters.getLabelNameWeight())
      .setOptionalQueryParameter("dj_edits", requestParameters.getDjEdits())
      .setOptionalQueryParameter("ugc_remixes", requestParameters.getUgcRemixes())
      .setOptionalQueryParameter(
        "dj_edits_and_ugc_remixes",
        requestParameters.getDjEditsAndUgcRemixes()
      )
      .setOptionalQueryParameter(
        "is_available_for_streaming",
        requestParameters.getIsAvailableForStreaming()
      )
      .build();
  }

  /**
   * Releases-Search
   *
   * @param requestParameters {@link ReleasesSearchSearchV1ReleasesGetParameters} Request Parameters Object
   * @return response of {@code ReleasesResponse}
   */
  public ReleasesResponse releasesSearchSearchV1ReleasesGet(
    @NonNull ReleasesSearchSearchV1ReleasesGetParameters requestParameters
  ) throws ApiError, ValidationException {
    return this.releasesSearchSearchV1ReleasesGet(requestParameters, null);
  }

  /**
   * Releases-Search
   *
   * @param requestParameters {@link ReleasesSearchSearchV1ReleasesGetParameters} Request Parameters Object
   * @return response of {@code ReleasesResponse}
   */
  public ReleasesResponse releasesSearchSearchV1ReleasesGet(
    @NonNull ReleasesSearchSearchV1ReleasesGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError, ValidationException {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.releasesSearchSearchV1ReleasesGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildReleasesSearchSearchV1ReleasesGetRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<ReleasesResponse>() {});
  }

  /**
   * Releases-Search
   *
   * @param requestParameters {@link ReleasesSearchSearchV1ReleasesGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<ReleasesResponse>}
   */
  public CompletableFuture<ReleasesResponse> releasesSearchSearchV1ReleasesGetAsync(
    @NonNull ReleasesSearchSearchV1ReleasesGetParameters requestParameters
  ) throws ApiError, ValidationException {
    return this.releasesSearchSearchV1ReleasesGetAsync(requestParameters, null);
  }

  /**
   * Releases-Search
   *
   * @param requestParameters {@link ReleasesSearchSearchV1ReleasesGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<ReleasesResponse>}
   */
  public CompletableFuture<ReleasesResponse> releasesSearchSearchV1ReleasesGetAsync(
    @NonNull ReleasesSearchSearchV1ReleasesGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError, ValidationException {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.releasesSearchSearchV1ReleasesGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildReleasesSearchSearchV1ReleasesGetRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<ReleasesResponse>() {});
    });
  }

  private Request buildReleasesSearchSearchV1ReleasesGetRequest(
    @NonNull ReleasesSearchSearchV1ReleasesGetParameters requestParameters,
    RequestConfig resolvedConfig
  ) throws ValidationException {
    new ViolationAggregator()
      .add(
        new ReleasesSearchSearchV1ReleasesGetParametersValidator("requestParameters")
          .required()
          .validate(requestParameters)
      )
      .validateAll();
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.DEFAULT),
      "search/v1/releases"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setQueryParameter("q", requestParameters.getQ())
      .setOptionalQueryParameter("count", requestParameters.getCount())
      .setOptionalQueryParameter("preorder", requestParameters.getPreorder())
      .setOptionalQueryParameter("from_publish_date", requestParameters.getFromPublishDate())
      .setOptionalQueryParameter("to_publish_date", requestParameters.getToPublishDate())
      .setOptionalQueryParameter("from_release_date", requestParameters.getFromReleaseDate())
      .setOptionalQueryParameter("to_release_date", requestParameters.getToReleaseDate())
      .setOptionalQueryParameter("genre_id", requestParameters.getGenreId())
      .setOptionalQueryParameter("genre_name", requestParameters.getGenreName())
      .setOptionalQueryParameter("release_name_weight", requestParameters.getReleaseNameWeight())
      .setOptionalQueryParameter("label_name_weight", requestParameters.getLabelNameWeight())
      .build();
  }

  /**
   * Artists-Search
   *
   * @param requestParameters {@link ArtistsSearchSearchV1ArtistsGetParameters} Request Parameters Object
   * @return response of {@code ArtistsResponse}
   */
  public ArtistsResponse artistsSearchSearchV1ArtistsGet(
    @NonNull ArtistsSearchSearchV1ArtistsGetParameters requestParameters
  ) throws ApiError {
    return this.artistsSearchSearchV1ArtistsGet(requestParameters, null);
  }

  /**
   * Artists-Search
   *
   * @param requestParameters {@link ArtistsSearchSearchV1ArtistsGetParameters} Request Parameters Object
   * @return response of {@code ArtistsResponse}
   */
  public ArtistsResponse artistsSearchSearchV1ArtistsGet(
    @NonNull ArtistsSearchSearchV1ArtistsGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.artistsSearchSearchV1ArtistsGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildArtistsSearchSearchV1ArtistsGetRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<ArtistsResponse>() {});
  }

  /**
   * Artists-Search
   *
   * @param requestParameters {@link ArtistsSearchSearchV1ArtistsGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<ArtistsResponse>}
   */
  public CompletableFuture<ArtistsResponse> artistsSearchSearchV1ArtistsGetAsync(
    @NonNull ArtistsSearchSearchV1ArtistsGetParameters requestParameters
  ) throws ApiError {
    return this.artistsSearchSearchV1ArtistsGetAsync(requestParameters, null);
  }

  /**
   * Artists-Search
   *
   * @param requestParameters {@link ArtistsSearchSearchV1ArtistsGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<ArtistsResponse>}
   */
  public CompletableFuture<ArtistsResponse> artistsSearchSearchV1ArtistsGetAsync(
    @NonNull ArtistsSearchSearchV1ArtistsGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.artistsSearchSearchV1ArtistsGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildArtistsSearchSearchV1ArtistsGetRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<ArtistsResponse>() {});
    });
  }

  private Request buildArtistsSearchSearchV1ArtistsGetRequest(
    @NonNull ArtistsSearchSearchV1ArtistsGetParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.DEFAULT),
      "search/v1/artists"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setQueryParameter("q", requestParameters.getQ())
      .setOptionalQueryParameter("count", requestParameters.getCount())
      .setOptionalQueryParameter("genre_id", requestParameters.getGenreId())
      .build();
  }

  /**
   * Labels-Search
   *
   * @param requestParameters {@link LabelsSearchSearchV1LabelsGetParameters} Request Parameters Object
   * @return response of {@code LabelsResponse}
   */
  public LabelsResponse labelsSearchSearchV1LabelsGet(
    @NonNull LabelsSearchSearchV1LabelsGetParameters requestParameters
  ) throws ApiError {
    return this.labelsSearchSearchV1LabelsGet(requestParameters, null);
  }

  /**
   * Labels-Search
   *
   * @param requestParameters {@link LabelsSearchSearchV1LabelsGetParameters} Request Parameters Object
   * @return response of {@code LabelsResponse}
   */
  public LabelsResponse labelsSearchSearchV1LabelsGet(
    @NonNull LabelsSearchSearchV1LabelsGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.labelsSearchSearchV1LabelsGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildLabelsSearchSearchV1LabelsGetRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<LabelsResponse>() {});
  }

  /**
   * Labels-Search
   *
   * @param requestParameters {@link LabelsSearchSearchV1LabelsGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<LabelsResponse>}
   */
  public CompletableFuture<LabelsResponse> labelsSearchSearchV1LabelsGetAsync(
    @NonNull LabelsSearchSearchV1LabelsGetParameters requestParameters
  ) throws ApiError {
    return this.labelsSearchSearchV1LabelsGetAsync(requestParameters, null);
  }

  /**
   * Labels-Search
   *
   * @param requestParameters {@link LabelsSearchSearchV1LabelsGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<LabelsResponse>}
   */
  public CompletableFuture<LabelsResponse> labelsSearchSearchV1LabelsGetAsync(
    @NonNull LabelsSearchSearchV1LabelsGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.labelsSearchSearchV1LabelsGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildLabelsSearchSearchV1LabelsGetRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<LabelsResponse>() {});
    });
  }

  private Request buildLabelsSearchSearchV1LabelsGetRequest(
    @NonNull LabelsSearchSearchV1LabelsGetParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.DEFAULT),
      "search/v1/labels"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setQueryParameter("q", requestParameters.getQ())
      .setOptionalQueryParameter("count", requestParameters.getCount())
      .build();
  }

  /**
   * Charts-Search
   *
   * @param requestParameters {@link ChartsSearchSearchV1ChartsGetParameters} Request Parameters Object
   * @return response of {@code ChartsResponse}
   */
  public ChartsResponse chartsSearchSearchV1ChartsGet(
    @NonNull ChartsSearchSearchV1ChartsGetParameters requestParameters
  ) throws ApiError {
    return this.chartsSearchSearchV1ChartsGet(requestParameters, null);
  }

  /**
   * Charts-Search
   *
   * @param requestParameters {@link ChartsSearchSearchV1ChartsGetParameters} Request Parameters Object
   * @return response of {@code ChartsResponse}
   */
  public ChartsResponse chartsSearchSearchV1ChartsGet(
    @NonNull ChartsSearchSearchV1ChartsGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.chartsSearchSearchV1ChartsGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildChartsSearchSearchV1ChartsGetRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<ChartsResponse>() {});
  }

  /**
   * Charts-Search
   *
   * @param requestParameters {@link ChartsSearchSearchV1ChartsGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<ChartsResponse>}
   */
  public CompletableFuture<ChartsResponse> chartsSearchSearchV1ChartsGetAsync(
    @NonNull ChartsSearchSearchV1ChartsGetParameters requestParameters
  ) throws ApiError {
    return this.chartsSearchSearchV1ChartsGetAsync(requestParameters, null);
  }

  /**
   * Charts-Search
   *
   * @param requestParameters {@link ChartsSearchSearchV1ChartsGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<ChartsResponse>}
   */
  public CompletableFuture<ChartsResponse> chartsSearchSearchV1ChartsGetAsync(
    @NonNull ChartsSearchSearchV1ChartsGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.chartsSearchSearchV1ChartsGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request =
      this.buildChartsSearchSearchV1ChartsGetRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<ChartsResponse>() {});
    });
  }

  private Request buildChartsSearchSearchV1ChartsGetRequest(
    @NonNull ChartsSearchSearchV1ChartsGetParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.DEFAULT),
      "search/v1/charts"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setQueryParameter("q", requestParameters.getQ())
      .setOptionalQueryParameter("count", requestParameters.getCount())
      .setOptionalQueryParameter("genre_id", requestParameters.getGenreId())
      .setOptionalQueryParameter("genre_name", requestParameters.getGenreName())
      .setOptionalQueryParameter("is_approved", requestParameters.getIsApproved())
      .setOptionalQueryParameter("from_publish_date", requestParameters.getFromPublishDate())
      .setOptionalQueryParameter("to_publish_date", requestParameters.getToPublishDate())
      .build();
  }

  /**
   * All-Search
   *
   * @param requestParameters {@link AllSearchSearchV1AllGetParameters} Request Parameters Object
   * @return response of {@code MultisearchResponse}
   */
  public MultisearchResponse allSearchSearchV1AllGet(
    @NonNull AllSearchSearchV1AllGetParameters requestParameters
  ) throws ApiError {
    return this.allSearchSearchV1AllGet(requestParameters, null);
  }

  /**
   * All-Search
   *
   * @param requestParameters {@link AllSearchSearchV1AllGetParameters} Request Parameters Object
   * @return response of {@code MultisearchResponse}
   */
  public MultisearchResponse allSearchSearchV1AllGet(
    @NonNull AllSearchSearchV1AllGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.allSearchSearchV1AllGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request = this.buildAllSearchSearchV1AllGetRequest(requestParameters, resolvedConfig);
    Response response = this.execute(request, resolvedConfig);
    byte[] bodyBytes = ModelConverter.readBytes(response);
    return ModelConverter.convert(bodyBytes, new TypeReference<MultisearchResponse>() {});
  }

  /**
   * All-Search
   *
   * @param requestParameters {@link AllSearchSearchV1AllGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<MultisearchResponse>}
   */
  public CompletableFuture<MultisearchResponse> allSearchSearchV1AllGetAsync(
    @NonNull AllSearchSearchV1AllGetParameters requestParameters
  ) throws ApiError {
    return this.allSearchSearchV1AllGetAsync(requestParameters, null);
  }

  /**
   * All-Search
   *
   * @param requestParameters {@link AllSearchSearchV1AllGetParameters} Request Parameters Object
   * @return response of {@code CompletableFuture<MultisearchResponse>}
   */
  public CompletableFuture<MultisearchResponse> allSearchSearchV1AllGetAsync(
    @NonNull AllSearchSearchV1AllGetParameters requestParameters,
    RequestConfig requestConfig
  ) throws ApiError {
    RequestConfig resolvedConfig =
      this.getResolvedConfig(this.allSearchSearchV1AllGetConfig, requestConfig);
    this.addErrorMapping(422, HttpValidationError.class, HttpValidationErrorException.class);
    Request request = this.buildAllSearchSearchV1AllGetRequest(requestParameters, resolvedConfig);
    CompletableFuture<Response> futureResponse = this.executeAsync(request, resolvedConfig);
    return futureResponse.thenApplyAsync(response -> {
      byte[] bodyBytes = ModelConverter.readBytes(response);
      return ModelConverter.convert(bodyBytes, new TypeReference<MultisearchResponse>() {});
    });
  }

  private Request buildAllSearchSearchV1AllGetRequest(
    @NonNull AllSearchSearchV1AllGetParameters requestParameters,
    RequestConfig resolvedConfig
  ) {
    return new RequestBuilder(
      HttpMethod.GET,
      resolveBaseUrl(resolvedConfig, Environment.DEFAULT),
      "search/v1/all"
    )
      .setAccessTokenAuth(resolveAccessToken(resolvedConfig))
      .setQueryParameter("q", requestParameters.getQ())
      .setOptionalQueryParameter("count", requestParameters.getCount())
      .setOptionalQueryParameter("preorder", requestParameters.getPreorder())
      .setOptionalQueryParameter(
        "tracks_from_release_date",
        requestParameters.getTracksFromReleaseDate()
      )
      .setOptionalQueryParameter(
        "tracks_to_release_date",
        requestParameters.getTracksToReleaseDate()
      )
      .setOptionalQueryParameter(
        "releases_from_release_date",
        requestParameters.getReleasesFromReleaseDate()
      )
      .setOptionalQueryParameter(
        "releases_to_release_date",
        requestParameters.getReleasesToReleaseDate()
      )
      .setOptionalQueryParameter("is_approved", requestParameters.getIsApproved())
      .setOptionalQueryParameter(
        "is_available_for_streaming",
        requestParameters.getIsAvailableForStreaming()
      )
      .build();
  }
}
