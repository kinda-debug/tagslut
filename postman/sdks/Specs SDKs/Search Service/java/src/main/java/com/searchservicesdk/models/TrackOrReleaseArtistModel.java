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
public class TrackOrReleaseArtistModel {

  @JsonProperty("artist_id")
  private JsonNullable<Long> artistId;

  @JsonProperty("artist_name")
  private JsonNullable<String> artistName;

  @JsonProperty("artist_type_name")
  private JsonNullable<String> artistTypeName;

  @JsonIgnore
  public Long getArtistId() {
    return artistId.orElse(null);
  }

  @JsonIgnore
  public String getArtistName() {
    return artistName.orElse(null);
  }

  @JsonIgnore
  public String getArtistTypeName() {
    return artistTypeName.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class TrackOrReleaseArtistModelBuilder {

    private JsonNullable<Long> artistId = JsonNullable.undefined();

    @JsonProperty("artist_id")
    public TrackOrReleaseArtistModelBuilder artistId(Long value) {
      this.artistId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> artistName = JsonNullable.undefined();

    @JsonProperty("artist_name")
    public TrackOrReleaseArtistModelBuilder artistName(String value) {
      this.artistName = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> artistTypeName = JsonNullable.undefined();

    @JsonProperty("artist_type_name")
    public TrackOrReleaseArtistModelBuilder artistTypeName(String value) {
      this.artistTypeName = JsonNullable.of(value);
      return this;
    }
  }
}
