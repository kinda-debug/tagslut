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
public class ArtistsSearchSearchV1ArtistsGetParameters {

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

  @JsonIgnore
  public Long getCount() {
    return count.orElse(null);
  }

  @JsonIgnore
  public String getGenreId() {
    return genreId.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class ArtistsSearchSearchV1ArtistsGetParametersBuilder {

    private JsonNullable<Long> count = JsonNullable.of(20L);

    @JsonProperty("count")
    public ArtistsSearchSearchV1ArtistsGetParametersBuilder count(Long value) {
      if (value == null) {
        throw new IllegalStateException("count cannot be null");
      }
      this.count = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> genreId = JsonNullable.undefined();

    @JsonProperty("genre_id")
    public ArtistsSearchSearchV1ArtistsGetParametersBuilder genreId(String value) {
      this.genreId = JsonNullable.of(value);
      return this;
    }
  }
}
