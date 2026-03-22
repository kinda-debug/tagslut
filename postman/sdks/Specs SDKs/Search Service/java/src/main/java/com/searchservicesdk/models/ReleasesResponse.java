package com.searchservicesdk.models;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NonNull;
import lombok.ToString;
import lombok.With;
import lombok.extern.jackson.Jacksonized;
import org.openapitools.jackson.nullable.JsonNullable;

/**
 * Response model for the `releases` endpoint.
 */
@Data
@Builder
@With
@ToString
@EqualsAndHashCode
@Jacksonized
public class ReleasesResponse {

  /**
   * List of release models.
   */
  @NonNull
  private List<ReleasesDefaultModel> data;

  @JsonProperty("debug")
  private JsonNullable<Object> debug;

  @JsonProperty("explain")
  private JsonNullable<Object> explain;

  @JsonIgnore
  public Object getDebug() {
    return debug.orElse(null);
  }

  @JsonIgnore
  public Object getExplain() {
    return explain.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class ReleasesResponseBuilder {

    private JsonNullable<Object> debug = JsonNullable.undefined();

    @JsonProperty("debug")
    public ReleasesResponseBuilder debug(Object value) {
      this.debug = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Object> explain = JsonNullable.undefined();

    @JsonProperty("explain")
    public ReleasesResponseBuilder explain(Object value) {
      this.explain = JsonNullable.of(value);
      return this;
    }
  }
}
