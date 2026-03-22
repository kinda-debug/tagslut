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
public class TracksDefaultModel {

  @NonNull
  private Double score;

  @NonNull
  @JsonProperty("add_date")
  private String addDate;

  @NonNull
  private List<TrackOrReleaseArtistModel> artists;

  @NonNull
  @JsonProperty("available_worldwide")
  private Long availableWorldwide;

  @NonNull
  @JsonProperty("change_date")
  private String changeDate;

  @NonNull
  @JsonProperty("current_status")
  private CurrentStatusModel currentStatus;

  @NonNull
  private Long enabled;

  @NonNull
  @JsonProperty("encode_status")
  private String encodeStatus;

  @NonNull
  @JsonProperty("exclusive_period")
  private Long exclusivePeriod;

  @NonNull
  @JsonProperty("genre_enabled")
  private Long genreEnabled;

  @NonNull
  @JsonProperty("is_available_for_streaming")
  private Long isAvailableForStreaming;

  @NonNull
  @JsonProperty("is_classic")
  private Long isClassic;

  @NonNull
  private TrackOrReleaseLabelModel label;

  @NonNull
  @JsonProperty("label_manager")
  private String labelManager;

  @NonNull
  @JsonProperty("mix_name")
  private String mixName;

  @NonNull
  @JsonProperty("publish_date")
  private String publishDate;

  @NonNull
  @JsonProperty("publish_status")
  private String publishStatus;

  @NonNull
  private TrackReleaseModel release;

  @NonNull
  @JsonProperty("release_date")
  private String releaseDate;

  @NonNull
  @JsonProperty("sale_type")
  private String saleType;

  @NonNull
  private TrackSuggestModel suggest;

  @NonNull
  @JsonProperty("supplier_id")
  private Long supplierId;

  @NonNull
  @JsonProperty("track_id")
  private Long trackId;

  @NonNull
  @JsonProperty("track_name")
  private String trackName;

  @NonNull
  @JsonProperty("track_number")
  private Long trackNumber;

  @NonNull
  @JsonProperty("update_date")
  private String updateDate;

  @NonNull
  @JsonProperty("was_ever_exclusive")
  private Long wasEverExclusive;

  @JsonProperty("bpm")
  private JsonNullable<Long> bpm;

  @JsonProperty("catalog_number")
  private JsonNullable<String> catalogNumber;

  @JsonProperty("chord_type_id")
  private JsonNullable<Long> chordTypeId;

  @JsonProperty("exclusive_date")
  private JsonNullable<String> exclusiveDate;

  @JsonProperty("free_download_end_date")
  private JsonNullable<String> freeDownloadEndDate;

  @JsonProperty("free_download_start_date")
  private JsonNullable<String> freeDownloadStartDate;

  @JsonProperty("guid")
  private JsonNullable<String> guid;

  @JsonProperty("isrc")
  private JsonNullable<String> isrc;

  @JsonProperty("key_id")
  private JsonNullable<Long> keyId;

  @JsonProperty("key_name")
  private JsonNullable<String> keyName;

  @JsonProperty("length")
  private JsonNullable<Long> length;

  @JsonProperty("pre_order_date")
  private JsonNullable<String> preOrderDate;

  @JsonProperty("streaming_date")
  private JsonNullable<String> streamingDate;

  @JsonProperty("downloads")
  private JsonNullable<Long> downloads;

  @JsonProperty("plays")
  private JsonNullable<Long> plays;

  @JsonProperty("price")
  private JsonNullable<PriceModel> price;

  @JsonProperty("is_explicit")
  private JsonNullable<Boolean> isExplicit;

  @JsonProperty("is_available_for_alacarte")
  private JsonNullable<Boolean> isAvailableForAlacarte;

  @JsonProperty("is_dj_edit")
  private JsonNullable<Boolean> isDjEdit;

  @JsonProperty("is_ugc_remix")
  private JsonNullable<Boolean> isUgcRemix;

  @JsonProperty("is_pre_order")
  private JsonNullable<Boolean> isPreOrder;

  @JsonProperty("track_image_uri")
  private JsonNullable<String> trackImageUri;

  @JsonProperty("track_image_dynamic_uri")
  private JsonNullable<String> trackImageDynamicUri;

  @JsonProperty("genre")
  private JsonNullable<TracksDefaultModelGenre> genre;

  @JsonProperty("sub_genre")
  private JsonNullable<SubGenreModel> subGenre;

  @JsonIgnore
  public Long getBpm() {
    return bpm.orElse(null);
  }

  @JsonIgnore
  public String getCatalogNumber() {
    return catalogNumber.orElse(null);
  }

  @JsonIgnore
  public Long getChordTypeId() {
    return chordTypeId.orElse(null);
  }

  @JsonIgnore
  public String getExclusiveDate() {
    return exclusiveDate.orElse(null);
  }

  @JsonIgnore
  public String getFreeDownloadEndDate() {
    return freeDownloadEndDate.orElse(null);
  }

  @JsonIgnore
  public String getFreeDownloadStartDate() {
    return freeDownloadStartDate.orElse(null);
  }

  @JsonIgnore
  public String getGuid() {
    return guid.orElse(null);
  }

  @JsonIgnore
  public String getIsrc() {
    return isrc.orElse(null);
  }

  @JsonIgnore
  public Long getKeyId() {
    return keyId.orElse(null);
  }

  @JsonIgnore
  public String getKeyName() {
    return keyName.orElse(null);
  }

  @JsonIgnore
  public Long getLength() {
    return length.orElse(null);
  }

  @JsonIgnore
  public String getPreOrderDate() {
    return preOrderDate.orElse(null);
  }

  @JsonIgnore
  public String getStreamingDate() {
    return streamingDate.orElse(null);
  }

  @JsonIgnore
  public Long getDownloads() {
    return downloads.orElse(null);
  }

  @JsonIgnore
  public Long getPlays() {
    return plays.orElse(null);
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
  public Boolean getIsAvailableForAlacarte() {
    return isAvailableForAlacarte.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsDjEdit() {
    return isDjEdit.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsUgcRemix() {
    return isUgcRemix.orElse(null);
  }

  @JsonIgnore
  public Boolean getIsPreOrder() {
    return isPreOrder.orElse(null);
  }

  @JsonIgnore
  public String getTrackImageUri() {
    return trackImageUri.orElse(null);
  }

  @JsonIgnore
  public String getTrackImageDynamicUri() {
    return trackImageDynamicUri.orElse(null);
  }

  @JsonIgnore
  public TracksDefaultModelGenre getGenre() {
    return genre.orElse(null);
  }

  @JsonIgnore
  public SubGenreModel getSubGenre() {
    return subGenre.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class TracksDefaultModelBuilder {

    private JsonNullable<Long> bpm = JsonNullable.undefined();

    @JsonProperty("bpm")
    public TracksDefaultModelBuilder bpm(Long value) {
      this.bpm = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> catalogNumber = JsonNullable.undefined();

    @JsonProperty("catalog_number")
    public TracksDefaultModelBuilder catalogNumber(String value) {
      this.catalogNumber = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> chordTypeId = JsonNullable.undefined();

    @JsonProperty("chord_type_id")
    public TracksDefaultModelBuilder chordTypeId(Long value) {
      this.chordTypeId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> exclusiveDate = JsonNullable.undefined();

    @JsonProperty("exclusive_date")
    public TracksDefaultModelBuilder exclusiveDate(String value) {
      this.exclusiveDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> freeDownloadEndDate = JsonNullable.undefined();

    @JsonProperty("free_download_end_date")
    public TracksDefaultModelBuilder freeDownloadEndDate(String value) {
      this.freeDownloadEndDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> freeDownloadStartDate = JsonNullable.undefined();

    @JsonProperty("free_download_start_date")
    public TracksDefaultModelBuilder freeDownloadStartDate(String value) {
      this.freeDownloadStartDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> guid = JsonNullable.undefined();

    @JsonProperty("guid")
    public TracksDefaultModelBuilder guid(String value) {
      this.guid = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> isrc = JsonNullable.undefined();

    @JsonProperty("isrc")
    public TracksDefaultModelBuilder isrc(String value) {
      this.isrc = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> keyId = JsonNullable.undefined();

    @JsonProperty("key_id")
    public TracksDefaultModelBuilder keyId(Long value) {
      this.keyId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> keyName = JsonNullable.undefined();

    @JsonProperty("key_name")
    public TracksDefaultModelBuilder keyName(String value) {
      this.keyName = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> length = JsonNullable.undefined();

    @JsonProperty("length")
    public TracksDefaultModelBuilder length(Long value) {
      this.length = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> preOrderDate = JsonNullable.undefined();

    @JsonProperty("pre_order_date")
    public TracksDefaultModelBuilder preOrderDate(String value) {
      this.preOrderDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> streamingDate = JsonNullable.undefined();

    @JsonProperty("streaming_date")
    public TracksDefaultModelBuilder streamingDate(String value) {
      this.streamingDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> downloads = JsonNullable.undefined();

    @JsonProperty("downloads")
    public TracksDefaultModelBuilder downloads(Long value) {
      this.downloads = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> plays = JsonNullable.undefined();

    @JsonProperty("plays")
    public TracksDefaultModelBuilder plays(Long value) {
      this.plays = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<PriceModel> price = JsonNullable.undefined();

    @JsonProperty("price")
    public TracksDefaultModelBuilder price(PriceModel value) {
      this.price = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isExplicit = JsonNullable.undefined();

    @JsonProperty("is_explicit")
    public TracksDefaultModelBuilder isExplicit(Boolean value) {
      this.isExplicit = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isAvailableForAlacarte = JsonNullable.undefined();

    @JsonProperty("is_available_for_alacarte")
    public TracksDefaultModelBuilder isAvailableForAlacarte(Boolean value) {
      this.isAvailableForAlacarte = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isDjEdit = JsonNullable.undefined();

    @JsonProperty("is_dj_edit")
    public TracksDefaultModelBuilder isDjEdit(Boolean value) {
      this.isDjEdit = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isUgcRemix = JsonNullable.undefined();

    @JsonProperty("is_ugc_remix")
    public TracksDefaultModelBuilder isUgcRemix(Boolean value) {
      this.isUgcRemix = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Boolean> isPreOrder = JsonNullable.undefined();

    @JsonProperty("is_pre_order")
    public TracksDefaultModelBuilder isPreOrder(Boolean value) {
      this.isPreOrder = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> trackImageUri = JsonNullable.undefined();

    @JsonProperty("track_image_uri")
    public TracksDefaultModelBuilder trackImageUri(String value) {
      this.trackImageUri = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> trackImageDynamicUri = JsonNullable.undefined();

    @JsonProperty("track_image_dynamic_uri")
    public TracksDefaultModelBuilder trackImageDynamicUri(String value) {
      this.trackImageDynamicUri = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<TracksDefaultModelGenre> genre = JsonNullable.undefined();

    @JsonProperty("genre")
    public TracksDefaultModelBuilder genre(TracksDefaultModelGenre value) {
      this.genre = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<SubGenreModel> subGenre = JsonNullable.undefined();

    @JsonProperty("sub_genre")
    public TracksDefaultModelBuilder subGenre(SubGenreModel value) {
      this.subGenre = JsonNullable.of(value);
      return this;
    }
  }
}
