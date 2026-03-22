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
public class LabelsDefaultModel {

  @NonNull
  private Double score;

  @NonNull
  @JsonProperty("label_id")
  private Long labelId;

  @NonNull
  @JsonProperty("label_name")
  private String labelName;

  @NonNull
  @JsonProperty("update_date")
  private String updateDate;

  @NonNull
  @JsonProperty("create_date")
  private String createDate;

  @NonNull
  @JsonProperty("is_included_in_rightsflow")
  private Long isIncludedInRightsflow;

  @NonNull
  private Long enabled;

  @NonNull
  @JsonProperty("is_available_for_hype")
  private Long isAvailableForHype;

  @NonNull
  @JsonProperty("is_available_for_streaming")
  private Long isAvailableForStreaming;

  @JsonProperty("plays")
  private JsonNullable<Long> plays;

  @JsonProperty("downloads")
  private JsonNullable<Long> downloads;

  @JsonProperty("label_image_uri")
  private JsonNullable<String> labelImageUri;

  @JsonProperty("label_image_dynamic_uri")
  private JsonNullable<String> labelImageDynamicUri;

  @JsonIgnore
  public Long getPlays() {
    return plays.orElse(null);
  }

  @JsonIgnore
  public Long getDownloads() {
    return downloads.orElse(null);
  }

  @JsonIgnore
  public String getLabelImageUri() {
    return labelImageUri.orElse(null);
  }

  @JsonIgnore
  public String getLabelImageDynamicUri() {
    return labelImageDynamicUri.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class LabelsDefaultModelBuilder {

    private JsonNullable<Long> plays = JsonNullable.undefined();

    @JsonProperty("plays")
    public LabelsDefaultModelBuilder plays(Long value) {
      this.plays = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> downloads = JsonNullable.undefined();

    @JsonProperty("downloads")
    public LabelsDefaultModelBuilder downloads(Long value) {
      this.downloads = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> labelImageUri = JsonNullable.undefined();

    @JsonProperty("label_image_uri")
    public LabelsDefaultModelBuilder labelImageUri(String value) {
      this.labelImageUri = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> labelImageDynamicUri = JsonNullable.undefined();

    @JsonProperty("label_image_dynamic_uri")
    public LabelsDefaultModelBuilder labelImageDynamicUri(String value) {
      this.labelImageDynamicUri = JsonNullable.of(value);
      return this;
    }
  }
}
