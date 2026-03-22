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
public class ReleaseKeyModel {

  @JsonProperty("key_id")
  private JsonNullable<Long> keyId;

  @JsonProperty("key_name")
  private JsonNullable<String> keyName;

  @JsonIgnore
  public Long getKeyId() {
    return keyId.orElse(null);
  }

  @JsonIgnore
  public String getKeyName() {
    return keyName.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class ReleaseKeyModelBuilder {

    private JsonNullable<Long> keyId = JsonNullable.undefined();

    @JsonProperty("key_id")
    public ReleaseKeyModelBuilder keyId(Long value) {
      this.keyId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> keyName = JsonNullable.undefined();

    @JsonProperty("key_name")
    public ReleaseKeyModelBuilder keyName(String value) {
      this.keyName = JsonNullable.of(value);
      return this;
    }
  }
}
