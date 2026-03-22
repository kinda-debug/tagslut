package com.tagslutapisdk.models;

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
public class _6aResolveTidalAlbumToIsrcParameters {

  @JsonProperty("countryCode")
  private JsonNullable<String> countryCode;

  @JsonIgnore
  public String getCountryCode() {
    return countryCode.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class _6aResolveTidalAlbumToIsrcParametersBuilder {

    private JsonNullable<String> countryCode = JsonNullable.undefined();

    @JsonProperty("countryCode")
    public _6aResolveTidalAlbumToIsrcParametersBuilder countryCode(String value) {
      this.countryCode = JsonNullable.of(value);
      return this;
    }
  }
}
