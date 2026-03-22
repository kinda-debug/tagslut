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
public class TrackReleaseModel {

  @NonNull
  @JsonProperty("release_id")
  private Long releaseId;

  @NonNull
  @JsonProperty("release_name")
  private String releaseName;

  @JsonProperty("release_image_uri")
  private JsonNullable<String> releaseImageUri;

  @JsonProperty("release_image_dynamic_uri")
  private JsonNullable<String> releaseImageDynamicUri;

  @JsonIgnore
  public String getReleaseImageUri() {
    return releaseImageUri.orElse(null);
  }

  @JsonIgnore
  public String getReleaseImageDynamicUri() {
    return releaseImageDynamicUri.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class TrackReleaseModelBuilder {

    private JsonNullable<String> releaseImageUri = JsonNullable.undefined();

    @JsonProperty("release_image_uri")
    public TrackReleaseModelBuilder releaseImageUri(String value) {
      this.releaseImageUri = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> releaseImageDynamicUri = JsonNullable.undefined();

    @JsonProperty("release_image_dynamic_uri")
    public TrackReleaseModelBuilder releaseImageDynamicUri(String value) {
      this.releaseImageDynamicUri = JsonNullable.of(value);
      return this;
    }
  }
}
