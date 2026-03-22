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
public class LabelsSearchSearchV1LabelsGetParameters {

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

  @JsonIgnore
  public Long getCount() {
    return count.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class LabelsSearchSearchV1LabelsGetParametersBuilder {

    private JsonNullable<Long> count = JsonNullable.of(20L);

    @JsonProperty("count")
    public LabelsSearchSearchV1LabelsGetParametersBuilder count(Long value) {
      if (value == null) {
        throw new IllegalStateException("count cannot be null");
      }
      this.count = JsonNullable.of(value);
      return this;
    }
  }
}
