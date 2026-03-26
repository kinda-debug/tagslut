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
public class _5aBeatportIsrcLookupParameters {

  @JsonProperty("isrc")
  private JsonNullable<String> isrc;

  @JsonIgnore
  public String getIsrc() {
    return isrc.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class _5aBeatportIsrcLookupParametersBuilder {

    private JsonNullable<String> isrc = JsonNullable.undefined();

    @JsonProperty("isrc")
    public _5aBeatportIsrcLookupParametersBuilder isrc(String value) {
      this.isrc = JsonNullable.of(value);
      return this;
    }
  }
}
