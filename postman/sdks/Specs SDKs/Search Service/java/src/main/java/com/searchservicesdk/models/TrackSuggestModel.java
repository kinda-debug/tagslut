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
public class TrackSuggestModel {

  @NonNull
  private String input;

  @JsonProperty("weight")
  private JsonNullable<Long> weight;

  @JsonIgnore
  public Long getWeight() {
    return weight.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class TrackSuggestModelBuilder {

    private JsonNullable<Long> weight = JsonNullable.undefined();

    @JsonProperty("weight")
    public TrackSuggestModelBuilder weight(Long value) {
      this.weight = JsonNullable.of(value);
      return this;
    }
  }
}
