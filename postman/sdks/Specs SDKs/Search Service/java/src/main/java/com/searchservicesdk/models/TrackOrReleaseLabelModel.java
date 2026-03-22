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
public class TrackOrReleaseLabelModel {

  @NonNull
  private Long enabled;

  @NonNull
  @JsonProperty("label_id")
  private Long labelId;

  @NonNull
  @JsonProperty("label_name")
  private String labelName;
}
