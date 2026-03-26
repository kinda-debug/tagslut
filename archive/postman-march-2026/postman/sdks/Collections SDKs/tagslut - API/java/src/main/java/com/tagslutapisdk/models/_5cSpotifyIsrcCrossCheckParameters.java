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
public class _5cSpotifyIsrcCrossCheckParameters {

  @JsonProperty("q")
  private JsonNullable<String> q;

  @JsonProperty("type")
  private JsonNullable<String> type;

  @JsonIgnore
  public String getQ() {
    return q.orElse(null);
  }

  @JsonIgnore
  public String getType() {
    return type.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class _5cSpotifyIsrcCrossCheckParametersBuilder {

    private JsonNullable<String> q = JsonNullable.undefined();

    @JsonProperty("q")
    public _5cSpotifyIsrcCrossCheckParametersBuilder q(String value) {
      this.q = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> type = JsonNullable.undefined();

    @JsonProperty("type")
    public _5cSpotifyIsrcCrossCheckParametersBuilder type(String value) {
      this.type = JsonNullable.of(value);
      return this;
    }
  }
}
