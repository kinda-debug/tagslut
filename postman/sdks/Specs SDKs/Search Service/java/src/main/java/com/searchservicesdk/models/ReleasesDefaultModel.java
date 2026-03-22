package com.searchservicesdk.models;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
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
public class ReleasesDefaultModel {

  @NonNull
  private Double score;

  @NonNull
  private TrackOrReleaseLabelModel label;

  @NonNull
  private ReleaseAggregatorModel aggregator;

  @NonNull
  @JsonProperty("available_worldwide")
  private Long availableWorldwide;

  @NonNull
  private Long exclusive;

  @NonNull
  @JsonProperty("publish_date")
  private String publishDate;

  @NonNull
  @JsonProperty("release_date")
  private String releaseDate;

  @NonNull
  @JsonProperty("release_id")
  private Long releaseId;

  @NonNull
  @JsonProperty("release_name")
  private String releaseName;

  @NonNull
  @JsonProperty("release_type")
  private String releaseType;

  @NonNull
  private Long status;

  @NonNull
  @JsonProperty("update_date")
  private String updateDate;

  @JsonProperty("current_status")
  private JsonNullable<List<CurrentStatusModel>> currentStatus;

  @JsonProperty("genre")
  private JsonNullable<ReleasesDefaultModelGenre> genre;

  @JsonProperty("tracks")
  private JsonNullable<List<ReleaseTrackModel>> tracks;

  @JsonProperty("key")
  private JsonNullable<List<ReleaseKeyModel>> key;

  @JsonProperty("artists")
  private JsonNullable<List<TrackOrReleaseArtistModel>> artists;

  @JsonProperty("catalog_number")
  private JsonNullable<String> catalogNumber;

  @JsonProperty("create_date")
  private JsonNullable<String> createDate;

  @JsonProperty("encoded_date")
  private JsonNullable<String> encodedDate;

  @JsonProperty("exclusive_date")
  private JsonNullable<String> exclusiveDate;

  @JsonProperty("streaming_date")
  private JsonNullable<String> streamingDate;

  @JsonProperty("preorder_date")
  private JsonNullable<String> preorderDate;

  @JsonProperty("label_manager")
  private JsonNullable<String> labelManager;

  @JsonProperty("pre_order_date")
  private JsonNullable<String> preOrderDate1;

  @JsonProperty("upc")
  private JsonNullable<String> upc;

  @JsonProperty("price")
  private JsonNullable<PriceModel> price;

  @JsonProperty("is_explicit")
  private JsonNullable<Boolean> isExplicit;

  @JsonProperty("track_count")
  private JsonNullable<Long> trackCount;

  @JsonProperty("release_image_uri")
  private JsonNullable<String> releaseImageUri;

  @JsonProperty("release_image_dynamic_uri")
  private JsonNullable<String> releaseImageDynamicUri;

  @JsonProperty("downloads")
  private JsonNullable<Long> downloads;

  @JsonProperty("is_hype")
  private JsonNullable<Boolean> isHype;

  @JsonProperty("is_pre_order")
  private JsonNullable<Boolean> isPreOrder;

  @JsonProperty("plays")
  private JsonNullable<Long> plays;

  @JsonIgnore
  public List<CurrentStatusModel> getCurrentStatus() {
    return currentStatus.orElse(null);
  }

  @JsonIgnore
  public ReleasesDefaultModelGenre getGenre() {
    return genre.orElse(null);
  }

  @JsonIgnore
  public List<ReleaseTrackModel> getTracks() {
    return tracks.orElse(null);
  }

  @JsonIgnore
  public List<ReleaseKeyModel> getKey() {
    return key.orElse(null);
  }

  @JsonIgnore
  public List<TrackOrReleaseArtistModel> getArtists() {
    return artists.orElse(null);
  }

  @JsonIgnore
  public String getCatalogNumber() {
    return catalogNumber.orElse(null);
  }

  @JsonIgnore
  public String getCreateDate() {
    return createDate.orElse(null);
  }

  @JsonIgnore
  public String getEncodedDate() {
    return encodedDate.orElse(null);
  }

  @JsonIgnore
  public String getExclusiveDate() {
    return exclusiveDate.orElse(null);
  }

  @JsonIgnore
  public String getStreamingDate() {
    return streamingDate.orElse(null);
  }

  @JsonIgnore
  public String getPreorderDate() {
    return preorderDate.orElse(null);
  }

  @JsonIgnore
  public String getLabelManager() {
    return labelManager.orElse(null);
  }

  @JsonIgnore
  public String getPreOrderDate1() {
    return preOrderDate1.orElse(null);
  }

  @JsonIgnore
  public String getUpc() {
    return upc.orElse(null);
  }

  @JsonIgnore
  public PriceModel getPrice() {
    return price.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsExplicit() {
    return isExplicit.orElse(null);
  }

  @JsonIgnore
  public Long getTrackCount() {
    return trackCount.orElse(null);
  }

  @JsonIgnore
  public String getReleaseImageUri() {
    return releaseImageUri.orElse(null);
  }

  @JsonIgnore
  public String getReleaseImageDynamicUri() {
    return releaseImageDynamicUri.orElse(null);
  }

  @JsonIgnore
  public Long getDownloads() {
    return downloads.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsHype() {
    return isHype.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsPreOrder() {
    return isPreOrder.orElse(null);
  }

  @JsonIgnore
  public Long getPlays() {
    return plays.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class ReleasesDefaultModelBuilder {

    private JsonNullable<List<CurrentStatusModel>> currentStatus = JsonNullable.undefined();

    @JsonProperty("current_status")
    public ReleasesDefaultModelBuilder currentStatus(List<CurrentStatusModel> value) {
      this.currentStatus = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<ReleasesDefaultModelGenre> genre = JsonNullable.undefined();

    @JsonProperty("genre")
    public ReleasesDefaultModelBuilder genre(ReleasesDefaultModelGenre value) {
      this.genre = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<List<ReleaseTrackModel>> tracks = JsonNullable.undefined();

    @JsonProperty("tracks")
    public ReleasesDefaultModelBuilder tracks(List<ReleaseTrackModel> value) {
      this.tracks = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<List<ReleaseKeyModel>> key = JsonNullable.undefined();

    @JsonProperty("key")
    public ReleasesDefaultModelBuilder key(List<ReleaseKeyModel> value) {
      this.key = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<List<TrackOrReleaseArtistModel>> artists = JsonNullable.undefined();

    @JsonProperty("artists")
    public ReleasesDefaultModelBuilder artists(List<TrackOrReleaseArtistModel> value) {
      this.artists = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> catalogNumber = JsonNullable.undefined();

    @JsonProperty("catalog_number")
    public ReleasesDefaultModelBuilder catalogNumber(String value) {
      this.catalogNumber = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> createDate = JsonNullable.undefined();

    @JsonProperty("create_date")
    public ReleasesDefaultModelBuilder createDate(String value) {
      this.createDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> encodedDate = JsonNullable.undefined();

    @JsonProperty("encoded_date")
    public ReleasesDefaultModelBuilder encodedDate(String value) {
      this.encodedDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> exclusiveDate = JsonNullable.undefined();

    @JsonProperty("exclusive_date")
    public ReleasesDefaultModelBuilder exclusiveDate(String value) {
      this.exclusiveDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> streamingDate = JsonNullable.undefined();

    @JsonProperty("streaming_date")
    public ReleasesDefaultModelBuilder streamingDate(String value) {
      this.streamingDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> preorderDate = JsonNullable.undefined();

    @JsonProperty("preorder_date")
    public ReleasesDefaultModelBuilder preorderDate(String value) {
      this.preorderDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> labelManager = JsonNullable.undefined();

    @JsonProperty("label_manager")
    public ReleasesDefaultModelBuilder labelManager(String value) {
      this.labelManager = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> preOrderDate1 = JsonNullable.undefined();

    @JsonProperty("pre_order_date")
    public ReleasesDefaultModelBuilder preOrderDate1(String value) {
      this.preOrderDate1 = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> upc = JsonNullable.undefined();

    @JsonProperty("upc")
    public ReleasesDefaultModelBuilder upc(String value) {
      this.upc = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<PriceModel> price = JsonNullable.undefined();

    @JsonProperty("price")
    public ReleasesDefaultModelBuilder price(PriceModel value) {
      if (value == null) {
        throw new IllegalStateException("price cannot be null");
      }
      this.price = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isExplicit = JsonNullable.undefined();

    @JsonProperty("is_explicit")
    public ReleasesDefaultModelBuilder isExplicit(Boolean value) {
      this.isExplicit = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> trackCount = JsonNullable.undefined();

    @JsonProperty("track_count")
    public ReleasesDefaultModelBuilder trackCount(Long value) {
      this.trackCount = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> releaseImageUri = JsonNullable.undefined();

    @JsonProperty("release_image_uri")
    public ReleasesDefaultModelBuilder releaseImageUri(String value) {
      this.releaseImageUri = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> releaseImageDynamicUri = JsonNullable.undefined();

    @JsonProperty("release_image_dynamic_uri")
    public ReleasesDefaultModelBuilder releaseImageDynamicUri(String value) {
      this.releaseImageDynamicUri = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> downloads = JsonNullable.undefined();

    @JsonProperty("downloads")
    public ReleasesDefaultModelBuilder downloads(Long value) {
      this.downloads = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isHype = JsonNullable.undefined();

    @JsonProperty("is_hype")
    public ReleasesDefaultModelBuilder isHype(Boolean value) {
      this.isHype = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isPreOrder = JsonNullable.undefined();

    @JsonProperty("is_pre_order")
    public ReleasesDefaultModelBuilder isPreOrder(Boolean value) {
      this.isPreOrder = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> plays = JsonNullable.undefined();

    @JsonProperty("plays")
    public ReleasesDefaultModelBuilder plays(Long value) {
      this.plays = JsonNullable.of(value);
      return this;
    }
  }
}
