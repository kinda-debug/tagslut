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

@Data
@Builder
@With
@ToString
@EqualsAndHashCode
@Jacksonized
public class ArtistsResponse {

  /**
   * List of artist models.
   */
  @NonNull
  private List<ArtistsDefaultModel> data;

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
  public static class ArtistsResponseBuilder {

    private JsonNullable<Object> debug = JsonNullable.undefined();

    @JsonProperty("debug")
    public ArtistsResponseBuilder debug(Object value) {
      this.debug = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Object> explain = JsonNullable.undefined();

    @JsonProperty("explain")
    public ArtistsResponseBuilder explain(Object value) {
      this.explain = JsonNullable.of(value);
      return this;
    }
  }
}
