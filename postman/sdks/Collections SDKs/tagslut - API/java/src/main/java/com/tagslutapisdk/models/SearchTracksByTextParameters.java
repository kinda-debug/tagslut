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
public class SearchTracksByTextParameters {

  @JsonProperty("q")
  private JsonNullable<String> q;

  @JsonProperty("count")
  private JsonNullable<String> count;

  @JsonIgnore
  public String getQ() {
    return q.orElse(null);
  }

  @JsonIgnore
  public String getCount() {
    return count.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class SearchTracksByTextParametersBuilder {

    private JsonNullable<String> q = JsonNullable.undefined();

    @JsonProperty("q")
    public SearchTracksByTextParametersBuilder q(String value) {
      this.q = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> count = JsonNullable.undefined();

    @JsonProperty("count")
    public SearchTracksByTextParametersBuilder count(String value) {
      this.count = JsonNullable.of(value);
      return this;
    }
  }
}
