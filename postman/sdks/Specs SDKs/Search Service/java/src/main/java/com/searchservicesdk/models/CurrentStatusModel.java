package com.searchservicesdk.models;

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
public class CurrentStatusModel {

  @JsonProperty("current_status_id")
  private JsonNullable<Long> currentStatusId;

  @JsonProperty("current_status_name")
  private JsonNullable<String> currentStatusName;

  @JsonIgnore
  public Long getCurrentStatusId() {
    return currentStatusId.orElse(null);
  }

  @JsonIgnore
  public String getCurrentStatusName() {
    return currentStatusName.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class CurrentStatusModelBuilder {

    private JsonNullable<Long> currentStatusId = JsonNullable.undefined();

    @JsonProperty("current_status_id")
    public CurrentStatusModelBuilder currentStatusId(Long value) {
      this.currentStatusId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> currentStatusName = JsonNullable.undefined();

    @JsonProperty("current_status_name")
    public CurrentStatusModelBuilder currentStatusName(String value) {
      this.currentStatusName = JsonNullable.of(value);
      return this;
    }
  }
}
