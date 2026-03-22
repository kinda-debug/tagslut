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
public class ReleaseTrackModel {

  @JsonProperty("track_id")
  private JsonNullable<Long> trackId;

  @JsonProperty("track_name")
  private JsonNullable<String> trackName;

  @JsonIgnore
  public Long getTrackId() {
    return trackId.orElse(null);
  }

  @JsonIgnore
  public String getTrackName() {
    return trackName.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class ReleaseTrackModelBuilder {

    private JsonNullable<Long> trackId = JsonNullable.undefined();

    @JsonProperty("track_id")
    public ReleaseTrackModelBuilder trackId(Long value) {
      this.trackId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> trackName = JsonNullable.undefined();

    @JsonProperty("track_name")
    public ReleaseTrackModelBuilder trackName(String value) {
      this.trackName = JsonNullable.of(value);
      return this;
    }
  }
}
