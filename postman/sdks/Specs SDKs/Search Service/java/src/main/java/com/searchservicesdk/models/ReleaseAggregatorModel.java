package com.searchservicesdk.models;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NonNull;
import lombok.ToString;
import lombok.With;
import lombok.extern.jackson.Jacksonized;

@Data
@Builder
@With
@ToString
@EqualsAndHashCode
@Jacksonized
public class ReleaseAggregatorModel {

  @NonNull
  @JsonProperty("aggregator_id")
  private Long aggregatorId;

  @NonNull
  @JsonProperty("aggregator_name")
  private String aggregatorName;
}
