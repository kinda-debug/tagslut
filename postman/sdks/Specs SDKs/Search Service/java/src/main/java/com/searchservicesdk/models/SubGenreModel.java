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
public class SubGenreModel {

  @JsonProperty("sub_genre_id")
  private JsonNullable<Long> subGenreId;

  @JsonProperty("sub_genre_name")
  private JsonNullable<String> subGenreName;

  @JsonIgnore
  public Long getSubGenreId() {
    return subGenreId.orElse(null);
  }

  @JsonIgnore
  public String getSubGenreName() {
    return subGenreName.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class SubGenreModelBuilder {

    private JsonNullable<Long> subGenreId = JsonNullable.undefined();

    @JsonProperty("sub_genre_id")
    public SubGenreModelBuilder subGenreId(Long value) {
      this.subGenreId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> subGenreName = JsonNullable.undefined();

    @JsonProperty("sub_genre_name")
    public SubGenreModelBuilder subGenreName(String value) {
      this.subGenreName = JsonNullable.of(value);
      return this;
    }
  }
}
