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
public class ChartsSearchSearchV1ChartsGetParameters {

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
   * Returns tracks that have the genre of the ID inputed. Multiple genre IDs can be added
   * by separating them with a comma, ex: (89, 6, 14).
   *
   * For a list of available genres and their IDs, make a GET call to our API route /catalog/genres/
   *
   */
  @JsonProperty("genre_id")
  private JsonNullable<String> genreId;

  /**
   *
   * Returns tracks that have a genre which partially matches the value inputed.
   *
   * For ex: “Techno” would return tracks with a genre of “Hard Techno”, “Techno (Peak Time / Driving)”, etc.
   *
   * For a list of genres and their names, make a GET call to our API route /catalog/genres/
   *
   */
  @JsonProperty("genre_name")
  private JsonNullable<String> genreName;

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
   * The date a chart was published on Beatport.com or Beatsource.com.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("from_publish_date")
  private JsonNullable<String> fromPublishDate;

  /**
   *
   * The date a chart was published on Beatport.com or Beatsource.com.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("to_publish_date")
  private JsonNullable<String> toPublishDate;

  @JsonIgnore
  public Long getCount() {
    return count.orElse(null);
  }

  @JsonIgnore
  public String getGenreId() {
    return genreId.orElse(null);
  }

  @JsonIgnore
  public String getGenreName() {
    return genreName.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsApproved() {
    return isApproved.orElse(null);
  }

  @JsonIgnore
  public String getFromPublishDate() {
    return fromPublishDate.orElse(null);
  }

  @JsonIgnore
  public String getToPublishDate() {
    return toPublishDate.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class ChartsSearchSearchV1ChartsGetParametersBuilder {

    private JsonNullable<Long> count = JsonNullable.of(20L);

    @JsonProperty("count")
    public ChartsSearchSearchV1ChartsGetParametersBuilder count(Long value) {
      if (value == null) {
        throw new IllegalStateException("count cannot be null");
      }
      this.count = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> genreId = JsonNullable.undefined();

    @JsonProperty("genre_id")
    public ChartsSearchSearchV1ChartsGetParametersBuilder genreId(String value) {
      this.genreId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> genreName = JsonNullable.undefined();

    @JsonProperty("genre_name")
    public ChartsSearchSearchV1ChartsGetParametersBuilder genreName(String value) {
      this.genreName = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isApproved = JsonNullable.undefined();

    @JsonProperty("is_approved")
    public ChartsSearchSearchV1ChartsGetParametersBuilder isApproved(Boolean value) {
      this.isApproved = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> fromPublishDate = JsonNullable.undefined();

    @JsonProperty("from_publish_date")
    public ChartsSearchSearchV1ChartsGetParametersBuilder fromPublishDate(String value) {
      this.fromPublishDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> toPublishDate = JsonNullable.undefined();

    @JsonProperty("to_publish_date")
    public ChartsSearchSearchV1ChartsGetParametersBuilder toPublishDate(String value) {
      this.toPublishDate = JsonNullable.of(value);
      return this;
    }
  }
}
