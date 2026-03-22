package com.searchservicesdk.models;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NonNull;
import lombok.ToString;
import lombok.With;
import lombok.extern.jackson.Jacksonized;
import org.openapitools.jackson.nullable.JsonNullable;

@Data
@Builder
@With
@ToString
@EqualsAndHashCode
@Jacksonized
public class AllSearchSearchV1AllGetParameters {

  /**
   * Search query text
   */
  @NonNull
  private String q;

  /**
   * The number of results returned in the response
   */
  @JsonProperty("count")
  private JsonNullable<Long> count;

  /**
   *
   * When FALSE, the response will not include tracks or releases in a pre-order status.
   *
   * When TRUE, the response will include tracks and releases that are in a pre-order status
   *
   */
  @JsonProperty("preorder")
  private JsonNullable<Boolean> preorder;

  /**
   *
   * The date a track was released to the public.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("tracks_from_release_date")
  private JsonNullable<String> tracksFromReleaseDate;

  /**
   *
   * The date a track was released to the public.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("tracks_to_release_date")
  private JsonNullable<String> tracksToReleaseDate;

  /**
   *
   * The date a release was released to the public.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("releases_from_release_date")
  private JsonNullable<String> releasesFromReleaseDate;

  /**
   *
   * The date a release was released to the public.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("releases_to_release_date")
  private JsonNullable<String> releasesToReleaseDate;

  /**
   *
   * When TRUE, the response will only include charts that have been approved.
   *
   * When FALSE, the response will include all charts.
   *
   * It is recommended to leave this set to TRUE
   *
   */
  @JsonProperty("is_approved")
  private JsonNullable<Boolean> isApproved;

  /**
   *
   * By default the response will return both streamable and non-streamable tracks.
   *
   * **Note**: This is dependent on your app scope, if your scope inherently does not allow
   * non-streamable tracks then only streamable tracks will be returned always.
   *
   * When FALSE, the response will return only tracks that are not available for streaming.
   *
   * When TRUE, the response will return only tracks that are available for streaming.
   *
   */
  @JsonProperty("is_available_for_streaming")
  private JsonNullable<Boolean> isAvailableForStreaming;

  @JsonIgnore
  public Long getCount() {
    return count.orElse(null);
  }

  @JsonIgnore
  public Boolean getPreorder() {
    return preorder.orElse(null);
  }

  @JsonIgnore
  public String getTracksFromReleaseDate() {
    return tracksFromReleaseDate.orElse(null);
  }

  @JsonIgnore
  public String getTracksToReleaseDate() {
    return tracksToReleaseDate.orElse(null);
  }

  @JsonIgnore
  public String getReleasesFromReleaseDate() {
    return releasesFromReleaseDate.orElse(null);
  }

  @JsonIgnore
  public String getReleasesToReleaseDate() {
    return releasesToReleaseDate.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsApproved() {
    return isApproved.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsAvailableForStreaming() {
    return isAvailableForStreaming.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class AllSearchSearchV1AllGetParametersBuilder {

    private JsonNullable<Long> count = JsonNullable.of(20L);

    @JsonProperty("count")
    public AllSearchSearchV1AllGetParametersBuilder count(Long value) {
      if (value == null) {
        throw new IllegalStateException("count cannot be null");
      }
      this.count = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> preorder = JsonNullable.undefined();

    @JsonProperty("preorder")
    public AllSearchSearchV1AllGetParametersBuilder preorder(Boolean value) {
      if (value == null) {
        throw new IllegalStateException("preorder cannot be null");
      }
      this.preorder = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> tracksFromReleaseDate = JsonNullable.undefined();

    @JsonProperty("tracks_from_release_date")
    public AllSearchSearchV1AllGetParametersBuilder tracksFromReleaseDate(String value) {
      this.tracksFromReleaseDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> tracksToReleaseDate = JsonNullable.undefined();

    @JsonProperty("tracks_to_release_date")
    public AllSearchSearchV1AllGetParametersBuilder tracksToReleaseDate(String value) {
      this.tracksToReleaseDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> releasesFromReleaseDate = JsonNullable.undefined();

    @JsonProperty("releases_from_release_date")
    public AllSearchSearchV1AllGetParametersBuilder releasesFromReleaseDate(String value) {
      this.releasesFromReleaseDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> releasesToReleaseDate = JsonNullable.undefined();

    @JsonProperty("releases_to_release_date")
    public AllSearchSearchV1AllGetParametersBuilder releasesToReleaseDate(String value) {
      this.releasesToReleaseDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isApproved = JsonNullable.undefined();

    @JsonProperty("is_approved")
    public AllSearchSearchV1AllGetParametersBuilder isApproved(Boolean value) {
      this.isApproved = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isAvailableForStreaming = JsonNullable.undefined();

    @JsonProperty("is_available_for_streaming")
    public AllSearchSearchV1AllGetParametersBuilder isAvailableForStreaming(Boolean value) {
      this.isAvailableForStreaming = JsonNullable.of(value);
      return this;
    }
  }
}
