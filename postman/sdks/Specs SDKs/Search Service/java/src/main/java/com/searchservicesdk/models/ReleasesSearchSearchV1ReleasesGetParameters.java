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
public class ReleasesSearchSearchV1ReleasesGetParameters {

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
   * When FALSE, the response will not include tracks in a pre-order status.
   *
   * When TRUE, the response will include tracks that are in a pre-order status
   *
   */
  @JsonProperty("preorder")
  private JsonNullable<Boolean> preorder;

  /**
   *
   * The date a track was published on Beatport.com or Beatsource.com.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("from_publish_date")
  private JsonNullable<String> fromPublishDate;

  /**
   *
   * The date a track was published on Beatport.com or Beatsource.com.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("to_publish_date")
  private JsonNullable<String> toPublishDate;

  /**
   *
   * The date a track was released to the public.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("from_release_date")
  private JsonNullable<String> fromReleaseDate;

  /**
   *
   * The date a track was released to the public.
   *
   * Format: YYYY-MM-DD
   *
   */
  @JsonProperty("to_release_date")
  private JsonNullable<String> toReleaseDate;

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

  @JsonProperty("release_name_weight")
  private JsonNullable<Long> releaseNameWeight;

  /**
   *
   * This parameter determines how much weight to put on label_name using the search query text from q.
   *
   * The higher the value the more weight is put on matching q to label_name
   *
   */
  @JsonProperty("label_name_weight")
  private JsonNullable<Long> labelNameWeight;

  @JsonIgnore
  public Long getCount() {
    return count.orElse(null);
  }

  @JsonIgnore
  public Boolean getPreorder() {
    return preorder.orElse(null);
  }

  @JsonIgnore
  public String getFromPublishDate() {
    return fromPublishDate.orElse(null);
  }

  @JsonIgnore
  public String getToPublishDate() {
    return toPublishDate.orElse(null);
  }

  @JsonIgnore
  public String getFromReleaseDate() {
    return fromReleaseDate.orElse(null);
  }

  @JsonIgnore
  public String getToReleaseDate() {
    return toReleaseDate.orElse(null);
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
  public Long getReleaseNameWeight() {
    return releaseNameWeight.orElse(null);
  }

  @JsonIgnore
  public Long getLabelNameWeight() {
    return labelNameWeight.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class ReleasesSearchSearchV1ReleasesGetParametersBuilder {

    private JsonNullable<Long> count = JsonNullable.of(20L);

    @JsonProperty("count")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder count(Long value) {
      if (value == null) {
        throw new IllegalStateException("count cannot be null");
      }
      this.count = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> preorder = JsonNullable.undefined();

    @JsonProperty("preorder")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder preorder(Boolean value) {
      if (value == null) {
        throw new IllegalStateException("preorder cannot be null");
      }
      this.preorder = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> fromPublishDate = JsonNullable.undefined();

    @JsonProperty("from_publish_date")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder fromPublishDate(String value) {
      this.fromPublishDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> toPublishDate = JsonNullable.undefined();

    @JsonProperty("to_publish_date")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder toPublishDate(String value) {
      this.toPublishDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> fromReleaseDate = JsonNullable.undefined();

    @JsonProperty("from_release_date")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder fromReleaseDate(String value) {
      this.fromReleaseDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> toReleaseDate = JsonNullable.undefined();

    @JsonProperty("to_release_date")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder toReleaseDate(String value) {
      this.toReleaseDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> genreId = JsonNullable.undefined();

    @JsonProperty("genre_id")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder genreId(String value) {
      this.genreId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> genreName = JsonNullable.undefined();

    @JsonProperty("genre_name")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder genreName(String value) {
      this.genreName = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> releaseNameWeight = JsonNullable.of(1L);

    @JsonProperty("release_name_weight")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder releaseNameWeight(Long value) {
      if (value == null) {
        throw new IllegalStateException("releaseNameWeight cannot be null");
      }
      this.releaseNameWeight = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> labelNameWeight = JsonNullable.of(1L);

    @JsonProperty("label_name_weight")
    public ReleasesSearchSearchV1ReleasesGetParametersBuilder labelNameWeight(Long value) {
      if (value == null) {
        throw new IllegalStateException("labelNameWeight cannot be null");
      }
      this.labelNameWeight = JsonNullable.of(value);
      return this;
    }
  }
}
