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
public class _5bTidalIsrcCrossCheckParameters {

  @JsonProperty("isrc")
  private JsonNullable<String> isrc;

  @JsonProperty("countryCode")
  private JsonNullable<String> countryCode;

  @JsonIgnore
  public String getIsrc() {
    return isrc.orElse(null);
  }

  @JsonIgnore
  public String getCountryCode() {
    return countryCode.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class _5bTidalIsrcCrossCheckParametersBuilder {

    private JsonNullable<String> isrc = JsonNullable.undefined();

    @JsonProperty("isrc")
    public _5bTidalIsrcCrossCheckParametersBuilder isrc(String value) {
      this.isrc = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> countryCode = JsonNullable.undefined();

    @JsonProperty("countryCode")
    public _5bTidalIsrcCrossCheckParametersBuilder countryCode(String value) {
      this.countryCode = JsonNullable.of(value);
      return this;
    }
  }
}
