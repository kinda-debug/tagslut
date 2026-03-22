package com.searchservicesdk.models;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
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
public class GenreModel {

  @JsonProperty("genre_id")
  private JsonNullable<Long> genreId;

  @JsonProperty("genre_name")
  private JsonNullable<String> genreName;

  @JsonIgnore
  public Long getGenreId() {
    return genreId.orElse(null);
  }

  @JsonIgnore
  public String getGenreName() {
    return genreName.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class GenreModelBuilder {

    private JsonNullable<Long> genreId = JsonNullable.undefined();

    @JsonProperty("genre_id")
    public GenreModelBuilder genreId(Long value) {
      this.genreId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> genreName = JsonNullable.undefined();

    @JsonProperty("genre_name")
    public GenreModelBuilder genreName(String value) {
      this.genreName = JsonNullable.of(value);
      return this;
    }
  }
}
