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
public class ChartsDefaultModel {

  @NonNull
  private Double score;

  @NonNull
  @JsonProperty("chart_id")
  private Long chartId;

  @NonNull
  @JsonProperty("chart_name")
  private String chartName;

  @NonNull
  @JsonProperty("create_date")
  private String createDate;

  @NonNull
  @JsonProperty("is_approved")
  private Long isApproved;

  @NonNull
  @JsonProperty("update_date")
  private String updateDate;

  @NonNull
  private Long enabled;

  @NonNull
  @JsonProperty("is_indexed")
  private Long isIndexed;

  @NonNull
  @JsonProperty("is_published")
  private Long isPublished;

  @JsonProperty("artist_id")
  private JsonNullable<Long> artistId;

  @JsonProperty("artist_name")
  private JsonNullable<String> artistName;

  @JsonProperty("person_id")
  private JsonNullable<Long> personId;

  @JsonProperty("publish_date")
  private JsonNullable<String> publishDate;

  @JsonProperty("item_type_id")
  private JsonNullable<Long> itemTypeId;

  @JsonProperty("person_username")
  private JsonNullable<String> personUsername;

  @JsonProperty("track_count")
  private JsonNullable<Long> trackCount;

  @JsonProperty("chart_image_uri")
  private JsonNullable<String> chartImageUri;

  @JsonProperty("chart_image_dynamic_uri")
  private JsonNullable<String> chartImageDynamicUri;

  @JsonProperty("genres")
  private JsonNullable<List<GenreModel>> genres;

  @JsonIgnore
  public Long getArtistId() {
    return artistId.orElse(null);
  }

  @JsonIgnore
  public String getArtistName() {
    return artistName.orElse(null);
  }

  @JsonIgnore
  public Long getPersonId() {
    return personId.orElse(null);
  }

  @JsonIgnore
  public String getPublishDate() {
    return publishDate.orElse(null);
  }

  @JsonIgnore
  public Long getItemTypeId() {
    return itemTypeId.orElse(null);
  }

  @JsonIgnore
  public String getPersonUsername() {
    return personUsername.orElse(null);
  }

  @JsonIgnore
  public Long getTrackCount() {
    return trackCount.orElse(null);
  }

  @JsonIgnore
  public String getChartImageUri() {
    return chartImageUri.orElse(null);
  }

  @JsonIgnore
  public String getChartImageDynamicUri() {
    return chartImageDynamicUri.orElse(null);
  }

  @JsonIgnore
  public List<GenreModel> getGenres() {
    return genres.orElse(null);
  }

  // Overwrite lombok builder methods
  public static class ChartsDefaultModelBuilder {

    private JsonNullable<Long> artistId = JsonNullable.undefined();

    @JsonProperty("artist_id")
    public ChartsDefaultModelBuilder artistId(Long value) {
      this.artistId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> artistName = JsonNullable.undefined();

    @JsonProperty("artist_name")
    public ChartsDefaultModelBuilder artistName(String value) {
      this.artistName = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> personId = JsonNullable.undefined();

    @JsonProperty("person_id")
    public ChartsDefaultModelBuilder personId(Long value) {
      this.personId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> publishDate = JsonNullable.undefined();

    @JsonProperty("publish_date")
    public ChartsDefaultModelBuilder publishDate(String value) {
      this.publishDate = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> itemTypeId = JsonNullable.undefined();

    @JsonProperty("item_type_id")
    public ChartsDefaultModelBuilder itemTypeId(Long value) {
      this.itemTypeId = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> personUsername = JsonNullable.undefined();

    @JsonProperty("person_username")
    public ChartsDefaultModelBuilder personUsername(String value) {
      this.personUsername = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<Long> trackCount = JsonNullable.undefined();

    @JsonProperty("track_count")
    public ChartsDefaultModelBuilder trackCount(Long value) {
      this.trackCount = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> chartImageUri = JsonNullable.undefined();

    @JsonProperty("chart_image_uri")
    public ChartsDefaultModelBuilder chartImageUri(String value) {
      this.chartImageUri = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<String> chartImageDynamicUri = JsonNullable.undefined();

    @JsonProperty("chart_image_dynamic_uri")
    public ChartsDefaultModelBuilder chartImageDynamicUri(String value) {
      this.chartImageDynamicUri = JsonNullable.of(value);
      return this;
    }

    private JsonNullable<List<GenreModel>> genres = JsonNullable.undefined();

    @JsonProperty("genres")
    public ChartsDefaultModelBuilder genres(List<GenreModel> value) {
      this.genres = JsonNullable.of(value);
      return this;
    }
  }
}
